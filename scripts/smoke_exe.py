"""Exercise a built Windows binary, including its native Tk runtime and LAN endpoint."""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, unquote, quote
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request

parser = argparse.ArgumentParser()
parser.add_argument('executable', type=Path)
args = parser.parse_args()
binary = args.executable.resolve(strict=True)
with tempfile.TemporaryDirectory(prefix='landrop-smoke-') as temporary:
    root = Path(temporary)
    payload = os.urandom(5 * 1024**2 + 93)
    shared = root / '安装包传输测试.apk'
    shared.write_bytes(payload)
    runtime = root / 'state'
    launch_record = root / 'launch-url.txt'
    helper = root / 'capture.py'
    helper.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(sys.argv[2], 'utf-8')\n", 'utf-8')
    environment = {**os.environ, 'BROWSER': f'"{sys.executable}" "{helper}" "{launch_record}" %s'}
    process = subprocess.Popen([str(binary), '--port', '0', '--state-dir', str(runtime), '--share', str(shared)], env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    admin = None
    try:
        deadline = time.monotonic() + 25
        while not (runtime / 'runtime.json').exists() or not launch_record.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Packaged application did not start.')
            time.sleep(.1)
        info = json.loads((runtime / 'runtime.json').read_text('utf-8'))
        base = 'http://127.0.0.1:' + str(info['port'])
        admin = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def post(client, url, data):
            request = Request(url, data=json.dumps(data).encode(), headers={'X-LanDrop': '1', 'Content-Type': 'application/json'})
            with client.open(request, timeout=8) as response:
                return json.load(response)

        launch_url = launch_record.read_text('utf-8')
        assert launch_url.startswith(base + '/desktop/') and '#' not in launch_url
        with admin.open(Request(launch_url, headers={'Cookie': 'landrop=expired-previous-session'})) as response:
            assert response.url == base + '/desktop'
            assert b'data-client="desktop"' in response.read()
        with admin.open(base + '/api/state') as response:
            state = json.load(response)
        assert state['files'][0]['name'] == shared.name
        with admin.open(base + '/api/qr') as response:
            assert b'<svg' in response.read()
        with admin.open(base + '/') as response:
            assert 'LanDrop' in response.read().decode()
        with admin.open(base + '/assets/app.js') as response:
            assert response.status == 200
        pair = urlsplit(state['pairUrl'])
        phone_base = f'{pair.scheme}://{pair.netloc}' if state['addresses'] else base
        phone = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        post(phone, phone_base + '/api/session', {'role': 'phone', 'token': pair.fragment.removeprefix('pair=')})
        with phone.open(phone_base + '/download/' + state['files'][0]['id'], timeout=8) as response:
            assert hashlib.sha256(response.read()).digest() == hashlib.sha256(payload).digest()
        upload = Request(phone_base + '/api/upload?name=' + quote('手机上传测试.bin'), data=payload, headers={'X-LanDrop': '1', 'Content-Type': 'application/octet-stream'})
        with phone.open(upload, timeout=10) as response:
            assert response.status == 201
        saved = runtime / '收到的文件' / '手机上传测试.bin'
        assert hashlib.sha256(saved.read_bytes()).digest() == hashlib.sha256(payload).digest()
        another = root / '再次启动添加的文件.txt'
        another.write_text('test', 'utf-8')
        duplicate = subprocess.run([str(binary), '--state-dir', str(runtime), str(another)], env=environment, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert duplicate.returncode == 0
        assert json.loads((runtime / 'runtime.json').read_text('utf-8'))['pid'] == info['pid']
        reopened_url = launch_record.read_text('utf-8')
        assert reopened_url != launch_url
        fresh_browser = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with fresh_browser.open(reopened_url) as response:
            assert response.url == base + '/desktop'
        with fresh_browser.open(base + '/api/state') as response:
            assert json.load(response)['role'] == 'admin'
        with admin.open(base + '/api/state') as response:
            assert any(item['name'] == another.name for item in json.load(response)['files'])
        print('PASS: native runtime, startup, existing-instance reuse, drag-to-exe sharing, frontend, real SVG QR, LAN download/upload (SHA-256, 5 MB each).')
        post(admin, base + '/api/admin/shutdown', {})
        process.wait(timeout=10)
        print('PASS: application exited cleanly.')
        launch_record.unlink()
        process = subprocess.Popen([str(binary), '--port', '0', '--state-dir', str(runtime)], env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 25
        while not launch_record.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Application did not restart.')
            time.sleep(.1)
        restart_url = launch_record.read_text('utf-8')
        restart_base = 'http://' + urlsplit(restart_url).netloc
        restarted = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with restarted.open(restart_url) as response:
            assert response.url == restart_base + '/desktop'
        with restarted.open(restart_base + '/api/state') as response:
            restored = json.load(response)
            assert restored['role'] == 'admin'
            assert len(restored['files']) == 2
        post(restarted, restart_base + '/api/admin/shutdown', {})
        process.wait(timeout=10)
        print('PASS: cold launch, stale cookie recovery, repeated launch, full restart and saved shares. Launch URLs were captured; no browser UI was automated.')
    finally:
        if process.poll() is None:
            # Exercise the same orderly exit used by the installer. No kill fallback.
            subprocess.run([str(binary), '--headless', '--prepare-upgrade', '--state-dir', str(runtime)], timeout=40, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            process.wait(timeout=10)
