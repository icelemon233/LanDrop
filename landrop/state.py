from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
from pathlib import Path

from . import __version__
from .errors import AppError
from .files import trusted_path, file_id, safe_name
from .sessions import SessionManager
from .settings import SettingsStore
from .transfers import UploadService

INSTALLERS = {'.apk', '.aab', '.apks', '.xapk'}


def addresses() -> list[str]:
    found: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('192.0.2.1', 9))  # Route lookup; no packet is sent.
            found.add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        found.update(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    candidates = [ip for ip in found if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback]
    return sorted(candidates, key=lambda ip: (not ip.startswith('192.168.'), not ip.startswith('10.'), ip))


class State:
    def __init__(self, data_dir: Path, test_mode: bool = False):
        self.test_mode = test_mode
        data_dir = data_dir.resolve()
        self.data_dir = data_dir
        self.inbox = data_dir / '收到的文件'
        self.outbox = data_dir / '待发送文件'
        self.partial_dir = data_dir / '.partial-transfers'
        for directory in (data_dir, self.inbox, self.outbox, self.partial_dir):
            directory.mkdir(parents=True, exist_ok=True)
            trusted_path(directory)
        self.lock = threading.RLock()
        self.config_path = data_dir / 'settings.json'
        self.settings = SettingsStore(self.config_path)
        self.catalog: dict[str, dict] = {}
        self.folder_errors: dict[str, str] = {}
        self.auth = SessionManager(self.lock)
        self.transfers: list[dict] = []
        self.ips = addresses()
        self.selected_ip = self.ips[0] if self.ips else '127.0.0.1'
        self.port = 0
        self.name = self.config.get('preferences', {}).get('computerName', socket.gethostname())
        self.stopping = threading.Event()
        self.scan_requested = threading.Event()
        self.scanning: set[str] = set()
        self.scan_busy = False
        self.uploads = UploadService(self)
        self.active_downloads = 0
        self.rescan_lock = threading.Lock()
        self.rescan(include_folders=False)
        self.request_scan()

    def request_scan(self):
        with self.lock:
            self.scanning = {item['id'] for item in self.config['folders']}
        self.scan_requested.set()

    def cleanup_owned_partials(self):
        # The composition root calls this only after acquiring the instance lock.
        trusted_path(self.partial_dir)
        for partial in self.partial_dir.glob('*.part'):
            if re.fullmatch(r'[a-f0-9]{32}\.part', partial.name) and not partial.is_symlink() and partial.is_file():
                partial.unlink(missing_ok=True)

    @property
    def config(self):
        return self.settings.snapshot()

    @property
    def warning(self):
        return self.settings.message

    @property
    def admin_token(self):
        return self.auth.admin_token

    @property
    def pair_token(self):
        return self.auth.pair_token

    @property
    def desktop_tickets(self):
        return self.auth.desktop_tickets

    def recover_settings(self):
        with self.lock:
            backup = self.settings.recover()
        self.rescan()
        return backup

    def set_name(self, name: str):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64:
            raise AppError('电脑名称需要 1 到 64 个字符。')
        with self.lock:
            candidate = self.config
            candidate.setdefault('preferences', {})['computerName'] = name.strip()
            self.settings.commit(candidate)
            self.name = name.strip()

    def set_window_preference(self, key, value):
        allowed = {'windowCloseBehavior': ('tray', 'exit'), 'windowTheme': ('auto', 'light', 'dark'), 'trayNoticeSeen': (True, False)}
        if key not in allowed or value not in allowed[key] or (key == 'trayNoticeSeen' and type(value) is not bool):
            raise AppError('窗口设置无效。')
        with self.lock:
            candidate = self.config
            preferences = candidate.setdefault('preferences', {})
            if preferences.get(key) == value:
                return
            preferences[key] = value
            self.settings.commit(candidate)

    def add_files(self, paths: list[str], refresh: bool = True):
        validated = []
        for raw in paths:
            try:
                path = Path(raw).expanduser().resolve(strict=True)
            except OSError:
                raise AppError('文件不存在或无法读取，请重新选择。', 404)
            if not path.is_file():
                raise AppError('请选择文件。')
            if path.is_relative_to(self.partial_dir):
                raise AppError('未完成传输的临时文件不能共享。', 409, 'temporary-file')
            validated.append(path)
        with self.lock:
            candidate = self.config
            known = {str(item['path']) for item in candidate['files']}
            for path in validated:
                if str(path) not in known:
                    candidate['files'].append({'path': str(path)})
                    known.add(str(path))
                if str(path) in candidate['excluded']:
                    candidate['excluded'].remove(str(path))
            self.settings.commit(candidate)
            for path in validated:
                info = path.stat()
                self.catalog[file_id(path)] = {'id': file_id(path), 'name': path.name, 'size': info.st_size, 'modified': info.st_mtime, 'modified_ns': info.st_mtime_ns, 'extension': path.suffix.lower(), 'source': '手动添加', 'folder': None, 'path': str(path)}
        if refresh:
            self.request_scan()

    def add_folder(self, raw: str):
        try:
            path = Path(raw).expanduser().resolve(strict=True)
        except OSError:
            raise AppError('找不到这个文件夹，请检查路径后重试。', 404)
        if not path.is_dir():
            raise AppError('请选择文件夹。')
        with self.lock:
            candidate = self.config
            if not any(item['path'] == str(path) for item in candidate['folders']):
                candidate['folders'].append({'id': file_id(path), 'path': str(path)})
            candidate['excluded'] = [item for item in candidate['excluded'] if not Path(item).is_relative_to(path)]
            self.settings.commit(candidate)
        self.request_scan()

    def remove_file(self, identifier: str):
        with self.lock:
            entry = self.catalog.get(identifier)
            if entry is None:
                raise AppError('这个文件已经不在共享列表中。', 404)
            candidate = self.config
            candidate['files'] = [item for item in candidate['files'] if item['path'] != entry['path']]
            if entry['path'] not in candidate['excluded']:
                candidate['excluded'].append(entry['path'])
            self.settings.commit(candidate)
            self.catalog.pop(identifier, None)
        self.request_scan()

    def remove_folder(self, identifier: str):
        with self.lock:
            candidate = self.config
            candidate['folders'] = [item for item in candidate['folders'] if item['id'] != identifier]
            self.settings.commit(candidate)
            self.catalog = {key: item for key, item in self.catalog.items() if item['folder'] != identifier}
        self.request_scan()

    def rescan(self, include_folders: bool = True):
        # A scan may walk a build directory; never hold the session lock while walking.
        with self.rescan_lock:
            with self.lock:
                config = self.config
                revision = self.settings.revision
                self.scan_busy = True
            catalog: dict[str, dict] = {}
            errors: dict[str, str] = {}
            excluded = set(config['excluded'])

            def include(path: Path, source: str, folder: str | None = None):
                try:
                    if str(path) in excluded or path.is_symlink() or path.is_junction() or not path.is_file():
                        return
                    trusted_path(path)
                    info = path.stat()
                    if folder and time.time() - info.st_mtime < 2:
                        return  # Let an APK finish being written before publishing it.
                    identifier = file_id(path)
                    if folder and identifier in catalog:
                        return
                    catalog[identifier] = {
                        'id': file_id(path), 'name': path.name, 'size': info.st_size,
                        'modified': info.st_mtime, 'modified_ns': info.st_mtime_ns, 'extension': path.suffix.lower(),
                        'source': source, 'folder': folder, 'path': str(path),
                    }
                except (OSError, AppError):
                    return

            for item in config['files']:
                try:
                    include(Path(item['path']), '手动添加')
                except (KeyError, TypeError):
                    continue
            for folder in (config['folders'] if include_folders else []):
                root = Path(folder['path'])
                identifier = folder['id']
                if not root.is_dir():
                    errors[identifier] = '文件夹不可用，请检查路径或移动硬盘。'
                    continue
                try:
                    trusted_path(root)
                except (OSError, AppError):
                    errors[identifier] = '共享路径已变成目录链接，请移除后重新选择。'
                    continue
                visited = 0
                directories = 0
                started = time.monotonic()
                try:
                    def on_error(_error):
                        errors[identifier] = '部分目录无法读取。'

                    for parent, dirs, files in os.walk(root, followlinks=False, onerror=on_error):
                        directories += 1
                        if self.stopping.is_set():
                            break
                        if directories > 5000 or time.monotonic() - started > 5:
                            errors[identifier] = '目录检查超过范围，请选择更具体的安装包输出文件夹。'
                            break
                        dirs[:] = [name for name in dirs if not name.startswith('.') and name not in {'node_modules', '__pycache__'} and not (Path(parent) / name).is_symlink() and not (Path(parent) / name).is_junction()]
                        for name in files:
                            visited += 1
                            if visited > 30000:
                                errors[identifier] = '文件过多，请选择更具体的安装包输出目录。'
                                break
                            if not name.startswith('.') and Path(name).suffix.lower() in INSTALLERS:
                                include(Path(parent) / name, root.name, identifier)
                        if visited > 30000:
                            break
                except OSError:
                    errors[identifier] = '文件夹暂时无法读取。'
            with self.lock:
                if self.settings.revision == revision:
                    self.catalog = catalog
                    self.folder_errors = errors
                    if include_folders:
                        self.scanning.clear()
                else:
                    self.scan_requested.set()
                self.scan_busy = False

    def scan_loop(self):
        while not self.stopping.is_set():
            self.scan_requested.wait(4)
            self.scan_requested.clear()
            if self.stopping.is_set():
                break
            self.rescan()

    @property
    def pair_url(self) -> str:
        return f'http://{self.selected_ip}:{self.port}/#pair={self.pair_token}'

    @property
    def admin_url(self) -> str:
        return self.auth.issue_desktop_url(self.port)

    def consume_desktop_ticket(self, ticket: str) -> bool:
        return self.auth.consume_ticket(ticket)

    def create_session(self, role: str, user_agent: str, peer: str) -> str:
        return self.auth.create(role, user_agent, peer)

    def session(self, token: str) -> dict | None:
        return self.auth.get(token)

    def reset_pairs(self):
        self.auth.reset_phones()

    def record(self, name: str, size: int, direction: str, device: str):
        with self.lock:
            self.transfers.insert(0, {'id': secrets.token_hex(8), 'name': name, 'size': size, 'direction': direction, 'device': device, 'time': time.time()})
            del self.transfers[100:]

    def snapshot(self, session: dict) -> dict:
        with self.lock:
            files = [{key: value for key, value in item.items() if key not in {'path', 'modified_ns'}} for item in self.catalog.values()]
            files.sort(key=lambda item: item['modified'], reverse=True)
            result = {'role': session['role'], 'computer': self.name, 'files': files, 'warning': self.warning, 'version': __version__, 'testMode': self.test_mode}
            if session['role'] == 'admin':
                result.update({
                    'pairUrl': self.pair_url, 'addresses': self.ips, 'address': self.selected_ip,
                    'port': self.port, 'inboxPath': str(self.inbox),
                    'received': self.inbox_files(),
                    'settingsStatus': {'protected': bool(self.settings.problem), 'reason': self.settings.problem},
                    'activeTransfers': self.uploads.active_count() + self.active_downloads,
                    'scanning': self.scan_busy or bool(self.scanning),
                    'folders': [{**item, 'name': Path(item['path']).name, 'status': 'checking' if item['id'] in self.scanning else 'ready', 'error': self.folder_errors.get(item['id'], ''), 'count': sum(Path(entry['path']).is_relative_to(Path(item['path'])) and entry['extension'] in INSTALLERS for entry in self.catalog.values())} for item in self.config['folders']],
                    'devices': self.auth.devices(),
                    'history': self.transfers.copy(),
                })
            return result

    def inbox_files(self) -> list[dict]:
        result = []
        try:
            trusted_path(self.inbox)
        except (OSError, AppError):
            return result
        for path in self.inbox.iterdir():
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
                trusted_path(path)
                source = '疑似旧版临时文件，内容未确认' if re.fullmatch(r'\.landrop-[a-f0-9]{32}\.part', path.name) else '手机上传'
                result.append({'id': file_id(path), 'name': path.name, 'size': stat.st_size, 'modified': stat.st_mtime, 'extension': path.suffix.lower(), 'source': source, 'folder': None})
            except (OSError, AppError):
                continue
        return sorted(result, key=lambda item: item['modified'], reverse=True)

    def resolve_download(self, identifier: str, received: bool = False) -> Path:
        if received:
            trusted_path(self.inbox)
            for path in self.inbox.iterdir():
                if file_id(path) == identifier and path.is_file() and not path.is_symlink():
                    return trusted_path(path)
        else:
            with self.lock:
                entry = self.catalog.get(identifier)
                if entry:
                    path = Path(entry['path'])
                    if path.is_file() and not path.is_symlink() and not path.is_junction():
                        # Block newly introduced junctions inside an automatic shared root.
                        if entry['folder']:
                            folder = next((item for item in self.config['folders'] if item['id'] == entry['folder']), None)
                            if folder is None or not path.resolve().is_relative_to(Path(folder['path'])):
                                raise AppError('文件路径已经变更，请重新添加。', 403)
                        return trusted_path(path)
        raise AppError('文件已移动或取消共享，请刷新列表。', 404)

    def file_identity(self, identifier: str) -> tuple[int, int] | None:
        with self.lock:
            entry = self.catalog.get(identifier)
            return (entry['size'], entry['modified_ns']) if entry else None
