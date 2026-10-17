from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import logging
import mimetypes
import os
import re
import secrets
import select
import shutil
import socket
import threading
import time
from email.utils import formatdate
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import qrcode
import qrcode.image.svg

from .state import AppError, State, safe_name
from . import __version__
from .files import open_shared
from .transfers import MAX_UPLOAD

WEB = Path(__file__).parent / 'web'


class UploadReader:
    def __init__(self, reader, connection, check):
        self.reader, self.connection, self.check = reader, connection, check

    def read(self, size: int):
        deadline = time.monotonic() + 120
        while True:
            self.check()
            ready, _, _ = select.select([self.connection], [], [], .2)
            if ready:
                return self.reader.read(size)
            if time.monotonic() > deadline:
                raise socket.timeout('Upload idle timeout')


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != 'nt'
    request_queue_size = 32

    def __init__(self, address, state: State, desktop=None):
        self.state = state
        self.desktop = desktop
        self.local_slots = threading.BoundedSemaphore(16)
        self.lan_slots = threading.BoundedSemaphore(16)
        self.connections: set = set()
        self.connection_sessions: dict = {}
        self.connection_uploads: dict = {}
        self.connection_condition = threading.Condition()
        self.failed_pairs: dict[str, list[float]] = {}
        self.failure_lock = threading.Lock()
        super().__init__(address, Handler)
        state.port = self.server_port

    def server_bind(self):
        if os.name == 'nt':
            # SO_REUSEADDR on Windows can route requests to another live app.
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def process_request(self, request, client_address):
        slots = self.local_slots if ipaddress.ip_address(client_address[0]).is_loopback else self.lan_slots
        if not slots.acquire(blocking=False):
            request.close()
            return
        with self.connection_condition:
            self.connections.add(request)
        try:
            super().process_request(request, client_address)
        except BaseException:
            slots.release()
            with self.connection_condition:
                self.connections.discard(request)
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            slots = self.local_slots if ipaddress.ip_address(client_address[0]).is_loopback else self.lan_slots
            slots.release()
            with self.connection_condition:
                self.connections.discard(request)
                self.connection_sessions.pop(request, None)
                self.connection_uploads.pop(request, None)
                self.connection_condition.notify_all()

    @staticmethod
    def abort_sockets(connections):
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def abort_upload(self, identifier: str):
        with self.connection_condition:
            connections = [connection for connection, value in self.connection_uploads.items() if value == identifier]
        self.abort_sockets(connections)

    def disconnect_phones(self, identifier: str | None = None):
        with self.connection_condition:
            connections = [connection for connection, value in self.connection_sessions.items() if value['role'] == 'phone' and (identifier is None or value['id'] == identifier)]
        self.state.uploads.cancel_owner(identifier)
        self.abort_sockets(connections)

    def close_gracefully(self) -> bool:
        self.state.stopping.set()
        self.state.scan_requested.set()
        self.state.uploads.cancel_all()
        self.shutdown()
        with self.connection_condition:
            sockets = list(self.connections)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        with self.connection_condition:
            cleaned = self.connection_condition.wait_for(lambda: not self.connections, timeout=5)
        self.server_close()
        return cleaned


class Handler(BaseHTTPRequestHandler):
    server: Server
    protocol_version = 'HTTP/1.1'
    server_version = 'LanDrop/' + __version__
    sys_version = ''
    rbufsize = 0  # Body reads must not hide bytes from cancellable socket polling.

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_args):
        pass  # Pairing credentials and filenames never enter an access log.

    @property
    def state(self) -> State:
        return self.server.state

    @property
    def local(self) -> bool:
        return ipaddress.ip_address(self.client_address[0]).is_loopback

    def send_common(self, status: int, content_type: str, length: int, extra: dict | None = None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.close_connection = True
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            if key.lower() != 'connection':
                self.send_header(key, value)
        self.end_headers()

    def output(self, payload: bytes, content_type: str = 'application/json; charset=utf-8', status: int = 200, extra: dict | None = None):
        self.send_common(status, content_type, len(payload), extra)
        if self.command != 'HEAD':
            self.wfile.write(payload)

    def json(self, payload: dict, status: int = 200, extra: dict | None = None):
        self.output(json.dumps(payload, ensure_ascii=False).encode(), status=status, extra=extra)

    def session(self, admin: bool = False) -> dict:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            raise AppError('请重新扫描电脑上的二维码。', 401)
        token = cookies.get('landrop')
        session = self.state.session(token.value) if token else None
        if not session:
            raise AppError('连接已失效，请重新扫描电脑上的二维码。', 401)
        if session['role'] == 'admin' and not self.local:
            raise AppError('管理界面只能在这台电脑上打开。', 403)
        if admin and session['role'] != 'admin':
            raise AppError('这项操作只能在电脑上进行。', 403)
        session['_token'] = token.value
        with self.server.connection_condition:
            self.server.connection_sessions[self.connection] = session
        return session

    def read_json(self) -> dict:
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise AppError('请求格式不正确。', 415)
        length = self.content_length(65536)
        try:
            payload = self.cached_json if self.cached_json is not None else self.read_exact(length)
            value = json.loads(payload)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise AppError('请求内容不正确。')

    def read_exact(self, length: int) -> bytes:
        result = bytearray()
        while len(result) < length:
            block = self.rfile.read(length - len(result))
            if not block:
                raise AppError('请求内容未完整发送。', 400, 'request-interrupted')
            result.extend(block)
        return bytes(result)

    def content_length(self, maximum: int) -> int:
        if self.headers.get('Transfer-Encoding'):
            raise AppError('请使用浏览器选择文件后上传。', 411)
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise AppError('文件大小不正确。')
        if length < 0:
            raise AppError('请求缺少文件大小。', 411)
        if length > maximum:
            raise AppError('单个文件最大支持 8 GB。' if maximum == MAX_UPLOAD else '请求内容过大。', 413)
        return length

    def verify_request(self):
        if self.state.stopping.is_set() and urlsplit(self.path).path != '/api/health':
            raise AppError('LanDrop正在退出，请稍后重新打开程序。', 503, 'service-stopping')
        peer = ipaddress.ip_address(self.client_address[0])
        if not peer.is_private and not peer.is_loopback:
            raise AppError('仅支持局域网连接。', 403)
        host = self.headers.get('Host', '')
        allowed = {f'{ip}:{self.server.server_port}' for ip in [*self.state.ips, '127.0.0.1', 'localhost']}
        if host not in allowed:
            raise AppError('请使用电脑显示的连接地址。', 403)
        if self.command == 'POST':
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{host}':
                raise AppError('请求来源不正确。', 403)
            if self.headers.get('X-LanDrop') != '1':
                raise AppError('请通过LanDrop界面进行操作。', 403)

    def dispatch(self):
        self.cached_json: bytes | None = None
        self.cached_upload: bytes | None = None
        try:
            # Consume bounded JSON bodies before returning an authorization error.
            # Closing a Windows socket while a separately sent body is unread can
            # reset the connection and discard the 401/403 response.
            if self.command == 'POST' and urlsplit(self.path).path != '/api/upload' and self.headers.get('Content-Type', '').split(';')[0] == 'application/json':
                self.cached_json = self.read_exact(self.content_length(65536))
            elif self.command == 'POST' and urlsplit(self.path).path == '/api/upload':
                size = self.content_length(MAX_UPLOAD)
                if size <= 65536:
                    self.cached_upload = self.read_exact(size)
            self.verify_request()
            if self.command == 'POST':
                self.post()
            else:
                self.get()
        except AppError as error:
            self.close_connection = True
            try:
                self.json({'error': str(error), 'code': error.code}, error.status, {'X-LanDrop-Error': quote(str(error), safe=''), 'X-LanDrop-Code': error.code})
            except OSError:
                pass  # Cancellation may have already closed the transfer socket.
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
            self.close_connection = True
        except (OSError, ValueError, TypeError, KeyError) as error:
            logging.exception('Request failed')
            self.close_connection = True
            try:
                self.json({'error': '操作失败，请检查文件是否存在、磁盘空间是否足够，然后再试。'}, 500, {'Connection': 'close'})
            except OSError:
                pass

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch

    def get(self):
        route = urlsplit(self.path)
        path = route.path
        if path == '/api/health':
            return self.json({'app': 'landrop', 'version': __version__, 'phase': 'stopping' if self.state.stopping.is_set() else 'running', **({'pid': os.getpid()} if self.local else {})})
        if path.startswith('/desktop/'):
            if not self.local:
                raise AppError('电脑端入口只能在运行程序的这台电脑上打开。', 403)
            if self.command == 'HEAD':
                return self.output(b'', status=405, extra={'Allow': 'GET'})
            # Establish the cookie before rendering any JavaScript or fetching app state.
            # The launcher ticket is single-use, local-only and short-lived.
            if self.state.consume_desktop_ticket(path.removeprefix('/desktop/')):
                session_token = self.state.create_session('admin', self.headers.get('User-Agent', ''), self.client_address[0])
                return self.output(b'', status=303, extra={
                    'Location': '/desktop',
                    'Set-Cookie': f'landrop={session_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400',
                })
            try:
                self.session(admin=True)
                return self.output(b'', status=303, extra={'Location': '/desktop'})
            except AppError:
                return self.output((WEB / 'index.html').read_bytes().replace(b'<body>', b'<body data-client="desktop">'), 'text/html; charset=utf-8', status=401)
        if path == '/desktop':
            if not self.local:
                raise AppError('电脑端入口只能在运行程序的这台电脑上打开。', 403)
            return self.output((WEB / 'index.html').read_bytes().replace(b'<body>', b'<body data-client="desktop">'), 'text/html; charset=utf-8')
        if path == '/api/state':
            return self.json(self.state.snapshot(self.session()))
        if path == '/api/inbox':
            self.session(admin=True)
            return self.json({'files': self.state.inbox_files()})
        if re.fullmatch(r'/api/uploads/[a-f0-9]{32}', path):
            return self.json(self.state.uploads.status(path.rsplit('/', 1)[1], self.session()))
        if path == '/api/qr':
            self.session(admin=True)
            code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
            code.add_data(self.state.pair_url)
            code.make(fit=True)
            image = code.make_image(image_factory=qrcode.image.svg.SvgPathImage)
            buffer = io.BytesIO()
            image.save(buffer)
            return self.output(buffer.getvalue(), 'image/svg+xml')
        if path.startswith('/download/'):
            session = self.session()
            received = parse_qs(route.query).get('received') == ['1']
            if received and session['role'] != 'admin':
                raise AppError('收到的文件只能在电脑上查看。', 403)
            return self.download(path.removeprefix('/download/'), session, received)
        static = {'/': (WEB / 'index.html', 'text/html; charset=utf-8'), '/index.html': (WEB / 'index.html', 'text/html; charset=utf-8')}
        if path.startswith('/assets/') and re.fullmatch(r'/assets/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_.-]+', path):
            asset = WEB / 'assets' / path.removeprefix('/assets/')
            if asset.suffix in {'.js', '.css', '.svg', '.png', '.webp'} and asset.is_file() and not asset.is_symlink() and asset.resolve().is_relative_to((WEB / 'assets').resolve()):
                content_type = {'js': 'text/javascript', 'css': 'text/css', 'svg': 'image/svg+xml'}.get(asset.suffix[1:], mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
                return self.output(asset.read_bytes(), content_type)
        if path in static:
            asset, content_type = static[path]
            return self.output(asset.read_bytes(), content_type)
        raise AppError('找不到这个页面。', 404)

    def post(self):
        route = urlsplit(self.path)
        path = route.path
        if path == '/api/desktop-launch':
            body = self.read_json()
            token = body.get('token')
            if not self.local or not isinstance(token, str) or not secrets.compare_digest(token, self.state.admin_token):
                raise AppError('电脑端启动凭据已失效，请退出旧程序后重新打开。', 401)
            return self.json({'url': self.state.admin_url})
        if path == '/api/session':
            body = self.read_json()
            role, token = body.get('role'), body.get('token')
            if role not in {'admin', 'phone'} or not isinstance(token, str):
                raise AppError('连接信息不正确。')
            peer = self.client_address[0]
            with self.server.failure_lock:
                now = time.time()
                attempts = [stamp for stamp in self.server.failed_pairs.get(peer, []) if now - stamp < 60]
                self.server.failed_pairs[peer] = attempts
                if len(attempts) >= 10:
                    raise AppError('连接尝试过于频繁，请一分钟后重试。', 429)
            expected = self.state.admin_token if role == 'admin' else self.state.pair_token
            if (role == 'admin' and not self.local) or not secrets.compare_digest(token, expected):
                with self.server.failure_lock:
                    self.server.failed_pairs[peer].append(time.time())
                raise AppError('电脑端登录已失效，请重新打开LanDrop程序。' if role == 'admin' else '二维码已失效，请扫描电脑上新的二维码。', 401)
            session_token = self.state.create_session(role, self.headers.get('User-Agent', ''), peer)
            return self.json({'ok': True}, extra={'Set-Cookie': f'landrop={session_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400'})
        if path == '/api/upload':
            return self.upload(parse_qs(route.query), self.session())
        if path == '/api/uploads':
            session = self.session()
            body = self.read_json()
            return self.json(self.state.uploads.create(session, body.get('id'), body.get('name'), body.get('size')), 201)
        if re.fullmatch(r'/api/uploads/[a-f0-9]{32}/cancel', path):
            session = self.session()
            self.read_json()
            identifier = path.split('/')[-2]
            result = self.state.uploads.cancel(identifier, session)
            if result['phase'] == 'cancelled':
                self.server.abort_upload(identifier)
            return self.json(result)
        if not path.startswith('/api/admin/'):
            raise AppError('找不到这个操作。', 404)
        self.session(admin=True)
        body = self.read_json()
        action = path.removeprefix('/api/admin/')
        desktop = self.server.desktop
        if action in {'pick-files', 'pick-folder', 'open-inbox'}:
            if desktop is None:
                raise AppError('当前没有系统选择窗口，请拖入文件或输入文件夹路径。', 409, 'desktop-unavailable')
            result = desktop.call({'pick-files': 'files', 'pick-folder': 'folder', 'open-inbox': 'open-inbox'}[action])
            if action == 'pick-files' and result:
                self.state.add_files(result)
            elif action == 'pick-folder' and result:
                self.state.add_folder(result)
        elif action == 'add-files':
            paths = body.get('paths')
            if not isinstance(paths, list) or not paths or len(paths) > 100 or not all(isinstance(item, str) for item in paths):
                raise AppError('请选择 1 到 100 个要共享的文件。')
            self.state.add_files(paths)
        elif action == 'add-folder':
            raw = body.get('path')
            if not isinstance(raw, str) or not raw.strip():
                raise AppError('请输入安装包输出文件夹的路径。')
            self.state.add_folder(raw.strip().strip('"'))
        elif action == 'remove-file':
            self.state.remove_file(str(body.get('id', '')))
        elif action == 'remove-folder':
            self.state.remove_folder(str(body.get('id', '')))
        elif action == 'reset-pairs':
            self.state.reset_pairs()
            self.server.disconnect_phones()
        elif action == 'address':
            address = body.get('address')
            if address not in self.state.ips:
                raise AppError('这个网络地址不可用。')
            self.state.selected_ip = address
        elif action == 'revoke-device':
            identifier = str(body.get('id', ''))
            self.state.auth.revoke(identifier)
            self.server.disconnect_phones(identifier)
        elif action == 'recover-settings':
            backup = self.state.recover_settings()
            return self.json({'ok': True, 'backup': backup.name if backup else None})
        elif action == 'computer-name':
            self.state.set_name(body.get('name'))
        elif action == 'refresh':
            self.state.request_scan()
        elif action == 'shutdown':
            if desktop:
                desktop.ensure_can_shutdown()
            self.json({'ok': True})
            self.state.stopping.set()
            self.state.uploads.cancel_all()
            if desktop:
                desktop.call('shutdown')
            else:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        else:
            raise AppError('找不到这个操作。', 404)
        return self.json({'ok': True})

    def upload(self, query: dict, session: dict):
        self.connection.settimeout(120)
        size = self.content_length(MAX_UPLOAD)
        identifier = query.get('id', [''])[0]
        if not identifier:
            identifier = secrets.token_hex(16)
            self.state.uploads.create(session, identifier, query.get('name', [''])[0], size)
        # Register before receive; a cancellation racing with registration is
        # also checked under the upload service lock before reading any bytes.
        with self.server.connection_condition:
            self.server.connection_uploads[self.connection] = identifier
        reader = io.BytesIO(self.cached_upload) if self.cached_upload is not None else UploadReader(self.rfile, self.connection, lambda: self.state.uploads.ensure_active(identifier, session))
        result = self.state.uploads.receive(identifier, session, reader, size)
        return self.json({'ok': True, 'name': result['savedName'], **result}, 201)


    def download(self, identifier: str, session: dict, received: bool):
        self.connection.settimeout(120)
        with self.state.lock:
            path = self.state.resolve_download(identifier, received)
            identity = None if received else self.state.file_identity(identifier)
        with open_shared(path, identity) as source:
            stat = os.fstat(source.fileno())
            size = stat.st_size
            etag = '"' + hashlib.sha256(f'{identifier}:{stat.st_mtime_ns}:{size}'.encode()).hexdigest()[:24] + '"'
            start, end, status = 0, size - 1, 200
            request_range = self.headers.get('Range')
            if request_range and self.headers.get('If-Range', etag) == etag:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', request_range)
                if not match or not any(match.groups()) or size == 0:
                    return self.output(b'', status=416, extra={'Content-Range': f'bytes */{size}'})
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), size - 1) if right else size - 1
                else:
                    count = int(right)
                    if count == 0:
                        return self.output(b'', status=416, extra={'Content-Range': f'bytes */{size}'})
                    start = max(0, size - count)
                if start >= size or start > end:
                    return self.output(b'', status=416, extra={'Content-Range': f'bytes */{size}'})
                status = 206
            length = max(0, end - start + 1)
            extras = {
                'Content-Disposition': f"attachment; filename=\"download{path.suffix if re.fullmatch(r'\.[A-Za-z0-9]+', path.suffix) else ''}\"; filename*=UTF-8''{quote(path.name, safe='')}",
                'Accept-Ranges': 'bytes', 'ETag': etag, 'Last-Modified': formatdate(stat.st_mtime, usegmt=True),
            }
            if status == 206:
                extras['Content-Range'] = f'bytes {start}-{end}/{size}'
            self.send_common(status, 'application/octet-stream', length, extras)
            if self.command == 'HEAD':
                return
            source.seek(start)
            remaining = length
            with self.state.lock:
                self.state.active_downloads += 1
            try:
                while remaining:
                    if self.state.stopping.is_set() or self.state.session(session['_token']) is None or (not received and identifier not in self.state.catalog):
                        self.close_connection = True
                        return
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        self.close_connection = True
                        return
                    self.wfile.write(block)
                    remaining -= len(block)
                if session['role'] == 'phone' and not received:
                    self.state.record(path.name, length, 'sent', session['name'])
            finally:
                with self.state.lock:
                    self.state.active_downloads -= 1
