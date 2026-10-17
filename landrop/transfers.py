from __future__ import annotations

import os
import re
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .errors import AppError
from .files import safe_name, trusted_path

MAX_UPLOAD = 8 * 1024**3


@dataclass
class Upload:
    id: str
    owner: str
    name: str
    size: int
    shared: bool
    phase: str = 'queued'
    received: int = 0
    saved_name: str = ''
    error: str = ''
    created: float = field(default_factory=time.monotonic)
    cancelled: threading.Event = field(default_factory=threading.Event)

    def snapshot(self):
        return {'id': self.id, 'name': self.name, 'size': self.size, 'shared': self.shared, 'phase': self.phase, 'received': self.received, 'savedName': self.saved_name, 'error': self.error}


class UploadService:
    def __init__(self, state):
        self.state = state
        self.lock = state.lock
        self.items: dict[str, Upload] = {}

    @staticmethod
    def owner(session: dict) -> str:
        return 'computer' if session['role'] == 'admin' else session['id']

    def _item(self, identifier: str, session: dict) -> Upload:
        item = self.items.get(identifier)
        if item is None or item.owner != self.owner(session):
            raise AppError('找不到这个发送任务。请检查电脑上的文件列表。', 404, 'upload-not-found')
        return item

    def create(self, session: dict, identifier: str, name: str, size: int) -> dict:
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise AppError('发送任务编号不正确。')
        if type(size) is not int or not 0 <= size <= MAX_UPLOAD:
            raise AppError('单个文件最大支持 8 GB。', 413, 'upload-too-large')
        if not isinstance(name, str):
            raise AppError('文件名不正确。')
        name = safe_name(name)
        with self.lock:
            if session['role'] == 'admin' and self.state.settings.problem:
                raise AppError(self.state.warning + '请先恢复设置。', 409, 'settings-protected')
            old = self.items.get(identifier)
            if old:
                if old.owner != self.owner(session):
                    raise AppError('发送任务编号冲突，请重新选择文件。', 409, 'upload-conflict')
                if old.name != name or old.size != size:
                    raise AppError('发送任务内容与之前不一致。', 409, 'upload-conflict')
                return old.snapshot()
            now = time.monotonic()
            self.items = {key: item for key, item in self.items.items() if now - item.created < (600 if item.phase == 'queued' else 3600) or item.phase in {'receiving', 'saving'}}
            done = sorted((item for item in self.items.values() if item.phase in {'completed', 'failed', 'cancelled'}), key=lambda item: item.created)
            for item in done[:-200]:
                self.items.pop(item.id, None)
            active = [item for item in self.items.values() if item.phase in {'queued', 'receiving', 'saving'}]
            if len(active) >= 12 or sum(item.owner == self.owner(session) for item in active) >= 4:
                raise AppError('正在发送的文件较多，请等当前文件完成。', 429, 'upload-limit')
            destination = trusted_path(self.state.outbox if session['role'] == 'admin' else self.state.inbox)
            if shutil.disk_usage(destination).free < size + 64 * 1024**2:
                raise AppError('电脑剩余空间不足，无法接收这个文件。', 507, 'disk-full')
            item = Upload(identifier, self.owner(session), name, size, session['role'] == 'admin')
            self.items[identifier] = item
            return item.snapshot()

    def status(self, identifier: str, session: dict) -> dict:
        with self.lock:
            return self._item(identifier, session).snapshot()

    def cancel(self, identifier: str, session: dict) -> dict:
        with self.lock:
            item = self._item(identifier, session)
            if item.phase not in {'completed', 'failed'}:
                item.cancelled.set()
                item.phase = 'cancelled'
            return item.snapshot()

    def cancel_all(self):
        with self.lock:
            for item in self.items.values():
                if item.phase in {'queued', 'receiving', 'saving'}:
                    item.cancelled.set()
                    item.phase = 'cancelled'

    def cancel_owner(self, owner: str | None):
        with self.lock:
            for item in self.items.values():
                if item.owner != 'computer' and (owner is None or item.owner == owner) and item.phase in {'queued', 'receiving', 'saving'}:
                    item.cancelled.set()
                    item.phase = 'cancelled'

    def active_count(self) -> int:
        with self.lock:
            return sum(item.phase in {'queued', 'receiving', 'saving'} for item in self.items.values())

    def _check(self, item: Upload, session: dict):
        if self.state.stopping.is_set() or item.cancelled.is_set():
            raise AppError('已取消发送。', 409, 'upload-cancelled')
        if self.state.session(session['_token']) is None:
            raise AppError('连接已断开，请重新连接后发送。', 401, 'session-expired')

    def ensure_active(self, identifier: str, session: dict):
        with self.lock:
            self._check(self._item(identifier, session), session)

    def receive(self, identifier: str, session: dict, reader, size: int) -> dict:
        with self.lock:
            item = self._item(identifier, session)
            if size != item.size:
                raise AppError('文件大小与发送任务不一致。', 409, 'upload-conflict')
            if item.phase != 'queued':
                raise AppError('发送任务已经开始或结束，请先检查发送结果。', 409, 'upload-conflict')
            self._check(item, session)
            item.phase = 'receiving'
        temporary: Path | None = None
        final: Path | None = None
        try:
            destination = trusted_path(self.state.outbox if item.shared else self.state.inbox)
            temporary = trusted_path(self.state.partial_dir) / f'{secrets.token_hex(16)}.part'
            with temporary.open('xb') as target:
                remaining = size
                while remaining:
                    self._check(item, session)
                    block = reader.read(min(1024 * 1024, remaining))
                    if not block:
                        raise AppError('传输中断，文件未保存。', 400, 'upload-interrupted')
                    self._check(item, session)
                    target.write(block)
                    remaining -= len(block)
                    with self.lock:
                        item.received = size - remaining
                target.flush()
                os.fsync(target.fileno())
            with self.lock:
                # Revocation, cancellation and final commit share the same lock.
                self._check(item, session)
                trusted_path(destination)
                trusted_path(self.state.partial_dir)
                item.phase = 'saving'
                suffix = Path(item.name).suffix
                stem = item.name[:-len(suffix)] if suffix else item.name
                index = 0
                while True:
                    final = destination / (item.name if index == 0 else f'{stem} ({index}){suffix}')
                    try:
                        with final.open('xb'):
                            pass
                        break
                    except FileExistsError:
                        index += 1
                try:
                    os.replace(temporary, final)
                    if item.shared:
                        self.state.add_files([str(final)], refresh=False)
                except Exception:
                    final.unlink(missing_ok=True)
                    raise
                item.saved_name = final.name
                item.received = size
                item.phase = 'completed'
                if not item.shared:
                    self.state.record(final.name, size, 'received', session['name'])
                return item.snapshot()
        except Exception as error:
            with self.lock:
                if item.phase != 'cancelled':
                    item.phase = 'cancelled' if isinstance(error, AppError) and error.code in {'session-expired', 'upload-cancelled'} else 'failed'
                item.error = str(error) if isinstance(error, AppError) else '文件未能保存，请检查空间和目录权限。'
            raise
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
