from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from landrop.server import Server
from landrop.state import State, safe_name, AppError


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = State(self.root / 'data')
        self.server = Server(('127.0.0.1', 0), self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.admin = self.pair('admin', self.state.admin_token)
        self.phone = self.pair('phone', self.state.pair_token)

    def tearDown(self):
        self.state.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def call(self, path, method='GET', body=None, cookie=None, headers=None):
        request_headers = {'X-LanDrop': '1'}
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            request_headers['Content-Type'] = 'application/json'
        if cookie:
            request_headers['Cookie'] = cookie
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.state.port, timeout=5)
        connection.request(method, path, body, request_headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def pair(self, role, token):
        status, headers, _ = self.call('/api/session', 'POST', {'role': role, 'token': token}, headers={'User-Agent': 'Android Test Browser'})
        self.assertEqual(status, 200)
        return headers['Set-Cookie'].split(';')[0]

    def make_shared(self, name='测试 app.apk', payload=b'APK content'):
        file = self.root / name
        file.write_bytes(payload)
        self.state.add_files([str(file)])
        return file, next(iter(self.state.catalog))

    def test_unpaired_cannot_list_or_download(self):
        _, identifier = self.make_shared()
        self.assertEqual(self.call('/api/state')[0], 401)
        self.assertEqual(self.call('/download/' + identifier)[0], 401)

    def test_cancel_interrupts_a_paused_upload_without_waiting_for_timeout(self):
        identifier = 'a' * 32
        self.assertEqual(self.call('/api/uploads', 'POST', {'id': identifier, 'name': 'paused.apk', 'size': 1048576}, cookie=self.phone)[0], 201)
        connection = socket.create_connection(('127.0.0.1', self.state.port))
        try:
            header = f'POST /api/upload?id={identifier} HTTP/1.1\r\nHost: 127.0.0.1:{self.state.port}\r\nCookie: {self.phone}\r\nX-LanDrop: 1\r\nContent-Length: 1048576\r\n\r\n'
            connection.sendall(header.encode() + b'partial')
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not list(self.state.partial_dir.iterdir()):
                time.sleep(.01)
            self.assertTrue(list(self.state.partial_dir.iterdir()))
            status, _, body = self.call(f'/api/uploads/{identifier}/cancel', 'POST', {}, cookie=self.phone)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['phase'], 'cancelled')
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and list(self.state.partial_dir.iterdir()):
                time.sleep(.01)
            self.assertEqual(list(self.state.partial_dir.iterdir()), [])
            self.assertEqual(list(self.state.inbox.iterdir()), [])
        finally:
            connection.close()

    def test_head_reports_actual_error_reason(self):
        _, identifier = self.make_shared()
        status, headers, body = self.call('/download/' + identifier, method='HEAD')
        self.assertEqual(status, 401)
        self.assertEqual(body, b'')
        self.assertTrue(headers['X-LanDrop-Error'])

    def test_lan_budget_does_not_consume_local_admin_slots(self):
        for _ in range(16):
            self.assertTrue(self.server.lan_slots.acquire(False))
        try:
            self.assertEqual(self.call('/api/state', cookie=self.admin)[0], 200)
        finally:
            for _ in range(16):
                self.server.lan_slots.release()

    def test_phone_snapshot_does_not_expose_local_paths_or_pairing_secret(self):
        file, _ = self.make_shared()
        status, _, body = self.call('/api/state', cookie=self.phone)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['role'], 'phone')
        self.assertNotIn('pairUrl', data)
        self.assertNotIn(str(file), body.decode())
        self.assertNotIn(self.state.admin_token, body.decode())

    def test_qr_is_real_svg_and_requires_admin(self):
        self.assertEqual(self.call('/api/qr', cookie=self.phone)[0], 403)
        status, headers, body = self.call('/api/qr', cookie=self.admin)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/svg+xml')
        self.assertIn(b'<svg', body)
        self.assertIn(b'<path', body)

    def test_desktop_launch_logs_in_before_loading_interface(self):
        from urllib.parse import urlsplit
        launch = urlsplit(self.state.admin_url)
        self.assertFalse(launch.fragment)
        status, headers, _ = self.call(launch.path, cookie='landrop=old-session')
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/desktop')
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';')[0]
        snapshot = json.loads(self.call('/api/state', cookie=cookie)[2])
        self.assertEqual(snapshot['role'], 'admin')
        self.assertIn('pairUrl', snapshot)
        status, _, html = self.call('/desktop', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b'data-client="desktop"', html)

    def test_desktop_ticket_is_single_use_and_requires_credential_to_issue(self):
        status, _, body = self.call('/api/desktop-launch', 'POST', {'token': self.state.admin_token})
        self.assertEqual(status, 200)
        from urllib.parse import urlsplit
        path = urlsplit(json.loads(body)['url']).path
        self.assertEqual(self.call(path)[0], 303)
        self.assertEqual(self.call(path)[0], 401)
        self.assertEqual(self.call('/api/desktop-launch', 'POST', {'token': 'stale'})[0], 401)
        self.assertEqual(self.call('/api/desktop-launch', 'POST', {}, self.phone)[0], 401)

    def test_expired_desktop_ticket_cannot_grant_access(self):
        from urllib.parse import urlsplit
        path = urlsplit(self.state.admin_url).path
        self.state.desktop_tickets[path.rsplit('/', 1)[1]] = time.monotonic() - 1
        status, headers, body = self.call(path)
        self.assertEqual(status, 401)
        self.assertNotIn('Set-Cookie', headers)
        self.assertIn(b'data-client="desktop"', body)

    def test_head_does_not_consume_desktop_ticket(self):
        from urllib.parse import urlsplit
        path = urlsplit(self.state.admin_url).path
        self.assertEqual(self.call(path, 'HEAD')[0], 405)
        self.assertEqual(self.call(path)[0], 303)

    def test_admin_login_errors_do_not_tell_computer_to_scan_qr(self):
        status, _, body = self.call('/api/session', 'POST', {'role': 'admin', 'token': 'old'})
        self.assertEqual(status, 401)
        self.assertNotIn('二维码', json.loads(body)['error'])

    def test_lan_peer_cannot_redeem_desktop_ticket_even_if_known(self):
        if not self.state.ips:
            self.skipTest('No IPv4 LAN interface')
        remote = Server(('0.0.0.0', 0), self.state)
        running = threading.Thread(target=remote.serve_forever, daemon=True)
        running.start()
        try:
            connection = http.client.HTTPConnection(self.state.ips[0], self.state.port, timeout=3)
            from urllib.parse import urlsplit
            connection.request('GET', urlsplit(self.state.admin_url).path)
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            connection.close()
        finally:
            remote.shutdown()
            remote.server_close()
            self.state.port = self.server.server_port

    def test_file_download_matches_sha256_and_preserves_unicode_filename(self):
        payload = os.urandom(3 * 1024**2 + 53)
        file, identifier = self.make_shared(payload=payload)
        status, headers, body = self.call('/download/' + identifier, cookie=self.phone)
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(body).digest(), hashlib.sha256(payload).digest())
        self.assertIn(quote(file.name, safe=''), headers['Content-Disposition'])
        self.assertEqual(self.state.transfers[0]['size'], len(payload))

    def test_byte_ranges_and_head(self):
        _, identifier = self.make_shared(payload=b'0123456789')
        route = '/download/' + identifier
        status, headers, body = self.call(route, cookie=self.phone, headers={'Range': 'bytes=2-5'})
        self.assertEqual((status, body), (206, b'2345'))
        self.assertEqual(headers['Content-Range'], 'bytes 2-5/10')
        self.assertEqual(self.call(route, cookie=self.phone, headers={'Range': 'bytes=-3'})[2], b'789')
        self.assertEqual(self.call(route, cookie=self.phone, headers={'Range': 'bytes=8-'})[2], b'89')
        self.assertEqual(self.call(route, cookie=self.phone, headers={'Range': 'bytes=100-'})[0], 416)
        self.assertEqual(self.call(route, cookie=self.phone, headers={'Range': 'bytes=1-2,4-5'})[0], 416)
        self.assertEqual(self.call(route, cookie=self.phone, headers={'Range': 'bytes=-0'})[0], 416)
        count = len(self.state.transfers)
        status, headers, body = self.call(route, 'HEAD', cookie=self.phone)
        self.assertEqual((status, body, headers['Content-Length']), (200, b'', '10'))
        self.assertEqual(len(self.state.transfers), count)

    def test_stale_range_validator_returns_full_current_file(self):
        _, identifier = self.make_shared(payload=b'new build')
        status, _, body = self.call('/download/' + identifier, cookie=self.phone, headers={'Range': 'bytes=3-', 'If-Range': '"old-build"'})
        self.assertEqual((status, body), (200, b'new build'))

    def test_phone_upload_matches_sha256_and_does_not_publish_to_other_phones(self):
        payload = os.urandom(2 * 1024**2 + 19)
        status, _, body = self.call('/api/upload?name=' + quote('手机照片.jpg'), 'POST', payload, self.phone)
        self.assertEqual(status, 201)
        name = json.loads(body)['name']
        self.assertEqual(hashlib.sha256((self.state.inbox / name).read_bytes()).digest(), hashlib.sha256(payload).digest())
        self.assertEqual(self.state.catalog, {})
        self.assertEqual(self.call('/api/inbox', cookie=self.phone)[0], 403)
        inbox = json.loads(self.call('/api/inbox', cookie=self.admin)[2])['files']
        self.assertEqual(inbox[0]['name'], name)
        self.assertEqual(self.call('/download/' + inbox[0]['id'] + '?received=1', cookie=self.phone)[0], 403)

    def test_duplicate_upload_does_not_overwrite(self):
        for payload in (b'first', b'second'):
            self.assertEqual(self.call('/api/upload?name=app.apk', 'POST', payload, self.phone)[0], 201)
        self.assertEqual((self.state.inbox / 'app.apk').read_bytes(), b'first')
        self.assertEqual((self.state.inbox / 'app (1).apk').read_bytes(), b'second')

    def test_desktop_drag_upload_becomes_downloadable(self):
        status, _, _ = self.call('/api/upload?name=app.apk', 'POST', b'new apk', self.admin)
        self.assertEqual(status, 201)
        identifier = next(iter(self.state.catalog))
        self.assertEqual(self.call('/download/' + identifier, cookie=self.phone)[2], b'new apk')

    def test_empty_file_and_large_upload_limit(self):
        self.assertEqual(self.call('/api/upload?name=empty.txt', 'POST', b'', self.phone)[0], 201)
        self.assertEqual((self.state.inbox / 'empty.txt').stat().st_size, 0)
        self.assertEqual(self.call('/api/upload?name=big.apk', 'POST', b'', self.phone, {'Content-Length': str(8 * 1024**3 + 1)})[0], 413)

    def test_upload_path_traversal_rejected(self):
        for name in ['../secret', 'a/b.apk', 'a\\b.apk', '..', '']:
            self.assertEqual(self.call('/api/upload?name=' + quote(name), 'POST', b'x', self.phone)[0], 400)
        self.assertFalse((self.root / 'secret').exists())

    def test_partial_upload_cleans_temporary_file(self):
        connection = socket.create_connection(('127.0.0.1', self.state.port), timeout=2)
        headers = f'POST /api/upload?name=interrupted.apk HTTP/1.1\r\nHost: 127.0.0.1:{self.state.port}\r\nX-LanDrop: 1\r\nCookie: {self.phone}\r\nContent-Length: 3000000\r\n\r\n'
        connection.sendall(headers.encode() + b'partial')
        connection.shutdown(socket.SHUT_WR)
        try:
            connection.recv(2048)
        finally:
            connection.close()
        for _ in range(100):
            if not list(self.state.inbox.iterdir()):
                break
            time.sleep(.01)
        self.assertEqual(list(self.state.inbox.iterdir()), [])

    def test_removing_share_keeps_original_file(self):
        file, identifier = self.make_shared()
        self.assertEqual(self.call('/api/admin/remove-file', 'POST', {'id': identifier}, self.admin)[0], 200)
        self.assertTrue(file.exists())
        self.assertEqual(self.call('/download/' + identifier, cookie=self.phone)[0], 404)

    def test_folder_scanning_finds_new_builds_and_skips_other_files(self):
        folder = self.root / 'project' / 'outputs'
        folder.mkdir(parents=True)
        self.state.add_folder(str(folder))
        apk = folder / 'app-release.apk'
        apk.write_bytes(b'new build')
        os.utime(apk, (time.time() - 10, time.time() - 10))
        (folder / 'secret.txt').write_text('do not share')
        hidden = folder / '.private'
        hidden.mkdir()
        (hidden / 'private.apk').write_bytes(b'secret')
        self.state.rescan()
        self.assertEqual([item['name'] for item in self.state.catalog.values()], ['app-release.apk'])
        self.state.remove_folder(self.state.config['folders'][0]['id'])
        self.assertTrue(apk.exists())
        self.assertEqual(self.state.catalog, {})

    def test_settings_remember_shared_files(self):
        self.make_shared()
        restored = State(self.state.data_dir)
        self.assertEqual(len(restored.catalog), 1)

    def test_phone_cannot_manage_files_or_connections(self):
        for action in ['remove-file', 'add-folder', 'add-files', 'reset-pairs', 'shutdown', 'pick-files', 'window-close-behavior', 'window-theme']:
            self.assertEqual(self.call('/api/admin/' + action, 'POST', {}, self.phone)[0], 403)

    def test_forbidden_json_body_can_arrive_after_headers(self):
        connection = socket.create_connection(('127.0.0.1', self.state.port), timeout=3)
        headers = f'POST /api/admin/reset-pairs HTTP/1.1\r\nHost: 127.0.0.1:{self.state.port}\r\nX-LanDrop: 1\r\nCookie: {self.phone}\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n'
        connection.sendall(headers.encode())
        time.sleep(.05)
        connection.sendall(b'{}')
        response = http.client.HTTPResponse(connection)
        response.begin()
        self.assertEqual(response.status, 403)
        self.assertIn('电脑', json.loads(response.read())['error'])
        response.close()
        connection.close()

    def test_reset_revokes_old_phone_and_qr_but_preserves_admin(self):
        old = self.state.pair_token
        self.assertEqual(self.call('/api/admin/reset-pairs', 'POST', {}, self.admin)[0], 200)
        self.assertEqual(self.call('/api/state', cookie=self.phone)[0], 401)
        self.assertEqual(self.call('/api/state', cookie=self.admin)[0], 200)
        self.assertEqual(self.call('/api/session', 'POST', {'role': 'phone', 'token': old})[0], 401)
        self.pair('phone', self.state.pair_token)

    def test_cross_origin_and_dns_rebinding_are_rejected(self):
        self.assertEqual(self.call('/api/admin/reset-pairs', 'POST', {}, self.admin, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.call('/api/state', cookie=self.admin, headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.call('/api/admin/reset-pairs', 'POST', {}, self.admin, {'X-LanDrop': ''})[0], 403)

    def test_static_path_traversal_rejected(self):
        for path in ['/assets/../../main.py', '/assets/%2e%2e/main.py', '/settings.json', '/data', '/download/../../main.py']:
            self.assertIn(self.call(path, cookie=self.phone)[0], [400, 404])

    def test_pairing_failures_rate_limited(self):
        for _ in range(10):
            self.assertEqual(self.call('/api/session', 'POST', {'role': 'phone', 'token': 'wrong'})[0], 401)
        self.assertEqual(self.call('/api/session', 'POST', {'role': 'phone', 'token': 'wrong'})[0], 429)

    def test_reserved_windows_filename_is_safe(self):
        self.assertEqual(safe_name('CON.apk'), '_CON.apk')
        self.assertEqual(safe_name('notes:today.txt'), 'notes_today.txt')
        self.assertEqual(len(safe_name('a' * 200 + '.apk')), 180)

    def test_corrupt_settings_start_with_visible_warning(self):
        for invalid in ['[]', '{"version":1,"files":[],"folders":[{}],"excluded":[]}', 'not json']:
            self.state.config_path.write_text(invalid, 'utf-8')
            restored = State(self.state.data_dir)
            self.assertTrue(restored.warning)
            self.assertEqual(restored.catalog, {})

    def test_nonexistent_folder_reports_actionable_error(self):
        status, _, body = self.call('/api/admin/add-folder', 'POST', {'path': str(self.root / 'missing')}, self.admin)
        self.assertEqual(status, 404)
        self.assertIn('找不到这个文件夹', json.loads(body)['error'])

    def test_revoke_during_upload_does_not_commit_file(self):
        connection = socket.create_connection(('127.0.0.1', self.state.port), timeout=2)
        headers = f'POST /api/upload?name=revoked.apk HTTP/1.1\r\nHost: 127.0.0.1:{self.state.port}\r\nX-LanDrop: 1\r\nCookie: {self.phone}\r\nContent-Length: 200\r\n\r\n'
        connection.sendall(headers.encode() + b'a' * 100)
        deadline = time.monotonic() + 2
        while not list(self.state.partial_dir.glob('*.part')) and time.monotonic() < deadline:
            time.sleep(.01)
        self.state.reset_pairs()
        connection.sendall(b'b' * 100)
        try:
            self.assertIn(b'401', connection.recv(2048).split(b'\r\n')[0])
        finally:
            connection.close()
        self.assertFalse((self.state.inbox / 'revoked.apk').exists())


if __name__ == '__main__':
    unittest.main()
