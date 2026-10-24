from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import time
from pathlib import Path

from .errors import AppError

MAX_SETTINGS = 8 * 1024**2


def empty_settings() -> dict:
    return {'version': 1, 'files': [], 'folders': [], 'excluded': [], 'preferences': {}}


def validate_settings(value: object) -> dict:
    if not isinstance(value, dict) or type(value.get('version')) is not int:
        raise ValueError('invalid-format')
    if value['version'] != 1:
        raise ValueError('unsupported-version')
    def path_text(raw):
        return isinstance(raw, str) and 0 < len(raw) <= 32767 and '\x00' not in raw and Path(raw).is_absolute()
    for key in ('files', 'folders', 'excluded'):
        if not isinstance(value.get(key), list) or len(value[key]) > 10000:
            raise ValueError('invalid-list')
    if not all(isinstance(item, dict) and path_text(item.get('path')) for item in value['files']):
        raise ValueError('invalid-files')
    if not all(isinstance(item, dict) and path_text(item.get('path')) and isinstance(item.get('id'), str) and re.fullmatch(r'[a-f0-9]{24}', item['id']) for item in value['folders']):
        raise ValueError('invalid-folders')
    if not all(path_text(raw) for raw in value['excluded']):
        raise ValueError('invalid-excluded')
    prefs = value.get('preferences', {})
    if not isinstance(prefs, dict) or ('computerName' in prefs and (not isinstance(prefs['computerName'], str) or not 1 <= len(prefs['computerName'].strip()) <= 64)):
        raise ValueError('invalid-preferences')
    if ('windowCloseBehavior' in prefs and prefs['windowCloseBehavior'] not in ('tray', 'exit')) or ('windowTheme' in prefs and prefs['windowTheme'] not in ('auto', 'light', 'dark')) or ('trayNoticeSeen' in prefs and type(prefs['trayNoticeSeen']) is not bool):
        raise ValueError('invalid-preferences')
    return copy.deepcopy(value)


class SettingsStore:
    """Commit first, publish second. Unknown or unreadable user settings are protected."""
    def __init__(self, path: Path):
        self.path = path
        self.value = empty_settings()
        self.revision = 0
        self.problem = ''
        self.message = ''
        self.fingerprint: str | None = None
        try:
            raw = self._read()
            self.fingerprint = hashlib.sha256(raw).hexdigest()
            self.value = validate_settings(json.loads(raw))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as error:
            self.problem = 'newer-version' if isinstance(error, ValueError) and str(error) == 'unsupported-version' else 'unreadable'
            self.message = '设置格式与当前版本不兼容，原文件已保留。' if self.problem == 'newer-version' else '共享设置无法读取，原文件已保留。'

    def _read(self) -> bytes:
        if self.path.stat().st_size > MAX_SETTINGS:
            raise ValueError('settings-too-large')
        return self.path.read_bytes()

    def snapshot(self) -> dict:
        return copy.deepcopy(self.value)

    def commit(self, candidate: dict):
        if self.problem:
            raise AppError(self.message + '请先恢复设置后再修改共享列表。', 409, 'settings-protected')
        candidate = validate_settings(candidate)
        payload = json.dumps(candidate, ensure_ascii=False, indent=2).encode('utf-8')
        if len(payload) > MAX_SETTINGS:
            raise AppError('共享设置超过 8 MB，请减少共享条目。', 413, 'settings-too-large')
        temporary: Path | None = None
        try:
            current = None
            if self.path.exists():
                with self.path.open('rb') as original:
                    current = hashlib.file_digest(original, 'sha256').hexdigest()
            if current != self.fingerprint:
                self.problem = 'external-change'
                self.message = '设置已被其他程序修改，请重新打开LanDrop后再保存。'
                raise AppError(self.message, 409, 'settings-protected')
            with tempfile.NamedTemporaryFile(prefix='.settings-', suffix='.tmp', dir=self.path.parent, delete=False) as file:
                temporary = Path(file.name)
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise AppError('共享设置未能保存，请检查目录权限或磁盘空间后重试。', 507, 'settings-save-failed') from error
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        self.value = candidate
        self.fingerprint = hashlib.sha256(payload).hexdigest()
        self.revision += 1

    def recover(self) -> Path | None:
        if not self.problem:
            return None
        backup = self.path.with_name(f'settings-backup-{time.strftime("%Y%m%d-%H%M%S")}-{secrets.token_hex(3)}.json')
        try:
            shutil.copy2(self.path, backup)
            with backup.open('rb') as copied, self.path.open('rb') as original:
                if hashlib.file_digest(copied, 'sha256').digest() != hashlib.file_digest(original, 'sha256').digest():
                    raise OSError('backup mismatch')
        except OSError as error:
            raise AppError('原设置未能备份，已停止恢复。请检查目录权限后重试。', 507, 'settings-backup-failed') from error
        old_problem, old_message = self.problem, self.message
        self.problem = self.message = ''
        with self.path.open('rb') as original:
            self.fingerprint = hashlib.file_digest(original, 'sha256').hexdigest()
        try:
            self.commit(empty_settings())
        except Exception:
            self.problem, self.message = old_problem, old_message
            raise
        return backup
