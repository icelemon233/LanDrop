"""Exercise the independent Windows window, session, lifecycle and LAN endpoint."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from landrop.runtime import RuntimeStore

parser = argparse.ArgumentParser()
parser.add_argument('executable', type=Path)
parser.add_argument('--report', type=Path)
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
    helper.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text('unexpected external browser', 'utf-8')\n", 'utf-8')
    environment = {**os.environ, 'BROWSER': f'"{sys.executable}" "{helper}" "{launch_record}" %s'}
    process = subprocess.Popen([str(binary), '--port', '0', '--state-dir', str(runtime), '--test-data', '--share', str(shared)], env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    admin = None
    try:
        deadline = time.monotonic() + 50
        while not (runtime / 'runtime.json').exists() or not (runtime / 'desktop-observation.json').exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Packaged application did not start.')
            time.sleep(.1)
        info = json.loads((runtime / 'runtime.json').read_text('utf-8'))
        base = 'http://127.0.0.1:' + str(info['port'])
        observation = json.loads((runtime / 'desktop-observation.json').read_text('utf-8'))
        assert observation['role'] == 'admin' and observation['phase'] == 'connected' and not observation['overflow']
        assert not launch_record.exists(), 'The application opened an external browser'
        admin = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def post(client, url, data):
            request = Request(url, data=json.dumps(data).encode(), headers={'X-LanDrop': '1', 'Content-Type': 'application/json'})
            with client.open(request, timeout=8) as response:
                return json.load(response)

        credential = RuntimeStore(runtime / 'runtime.json').read()
        launch_url = post(admin, base + '/api/desktop-launch', {'token': credential.secret})['url']
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
        phone = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
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
        duplicate = subprocess.run([str(binary), '--state-dir', str(runtime), '--test-data', str(another)], env=environment, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert duplicate.returncode == 0
        assert json.loads((runtime / 'runtime.json').read_text('utf-8'))['pid'] == info['pid']
        assert not launch_record.exists(), 'Reopening the application launched a browser'
        with admin.open(base + '/api/health') as response:
            health = json.load(response)
            assert health['desktopMode'] == 'window' and health['windowReady']
        with admin.open(base + '/api/state') as response:
            assert any(item['name'] == another.name for item in json.load(response)['files'])
        print('PASS: independent window, authenticated embedded UI, existing-window activation without a browser, drag-to-exe sharing, real SVG QR, LAN download/upload (SHA-256, 5 MB each).')
        post(admin, base + '/api/admin/window-theme', {'mode': 'light'})
        post(admin, base + '/api/admin/window-close-behavior', {'behavior': 'exit'})
        post(admin, base + '/api/admin/shutdown', {})
        process.wait(timeout=10)
        print('PASS: application exited cleanly.')
        (runtime / 'desktop-observation.json').unlink()
        process = subprocess.Popen([str(binary), '--port', '0', '--state-dir', str(runtime), '--test-data'], env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 50
        while not (runtime / 'desktop-observation.json').exists():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Application did not restart.')
            time.sleep(.1)
        restart_info = RuntimeStore(runtime / 'runtime.json').read()
        restart_base = f'http://127.0.0.1:{restart_info.port}'
        restarted = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        restart_url = post(restarted, restart_base + '/api/desktop-launch', {'token': restart_info.secret})['url']
        with restarted.open(restart_url) as response:
            assert response.url == restart_base + '/desktop'
        with restarted.open(restart_base + '/api/state') as response:
            restored = json.load(response)
            assert restored['role'] == 'admin'
            assert len(restored['files']) == 2
            assert restored['desktop']['closeBehavior'] == 'exit'
        post(restarted, restart_base + '/api/admin/shutdown', {})
        process.wait(timeout=10)
        assert not launch_record.exists()
        restart_observation = json.loads((runtime / 'desktop-observation.json').read_text('utf-8'))
        assert restart_observation['role'] == 'admin' and restart_observation['phase'] == 'connected'
        assert restart_observation['theme'] == 'light'
        assert restart_observation['native']['captionTheme'] == 'light'
        assert restart_observation['native']['captionHeight'] == round(40 * restart_observation['native']['dpi'] / 96)
        print('PASS: cold launch, stale cookie recovery, repeated launch, full restart and saved shares. No external browser was launched.')
        print('PASS: saved close behavior and light appearance restored in the native caption and WebView after a new port was selected.')
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({'payloadSha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'passed': ['independent Windows window', 'embedded admin session', 'reuse without browser launch', 'native shutdown and restart', 'LAN 5 MB bidirectional SHA-256', 'preserved shares', 'saved close behavior and appearance across ports'], 'firstWindow': observation, 'restartedWindow': restart_observation, 'externalBrowserLaunched': False}, indent=2), 'utf-8')
    finally:
        if process.poll() is None:
            # Exercise the same orderly exit used by the installer. No kill fallback.
            subprocess.run([str(binary), '--headless', '--prepare-upgrade', '--state-dir', str(runtime)], timeout=40, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            process.wait(timeout=10)
