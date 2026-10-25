"""Verify the packaged application's normal-exit protocol through an isolated Inno build."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from landrop.runtime import RuntimeStore

parser = argparse.ArgumentParser()
parser.add_argument('--qa-root', type=Path, required=True)
parser.add_argument('--foreground', action='store_true', help='Exercise foreground/backend exit confirmation as well as direct silent maintenance')
args = parser.parse_args()
qa = args.qa_root.resolve(strict=True)
if qa.parent != root / '.local' or not qa.name.startswith('inno-qa-'):
    raise SystemExit('Use an isolated installer QA root inside .local/.')
setup = qa / 'LanDrop-setup-qa.exe'
manifest = json.loads(Path(str(setup) + '.build.json').read_text('utf-8-sig'))
if Path(manifest['qaRoot']).resolve() != qa:
    raise SystemExit('Never run this check with a production installer.')
application = qa / 'running-app'
state = qa / 'data'
marker = state / 'running-maintenance-preserve.txt'
marker.write_text('preserve existing received files and settings', 'utf-8')
exe = application / 'LanDrop.exe'
silent = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART']
install = silent + ['/CURRENTUSER', f'/DIR={application}', '/TASKS=']
process: subprocess.Popen | None = None

def execute(file: Path, options: list[str], success: bool = True) -> None:
    result = subprocess.run([str(file), *options], timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
    assert (result.returncode == 0) == success, (file.name, result.returncode, success)

def launch() -> subprocess.Popen:
    launched = subprocess.Popen([str(exe), '--headless', '--no-browser', '--port', '0', '--state-dir', str(state)], creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        assert launched.poll() is None, 'Packaged QA app exited during startup'
        if RuntimeStore(state / 'runtime.json').read():
            return launched
        time.sleep(0.1)
    raise AssertionError('Packaged QA app did not become ready')

try:
    execute(setup, install + [f'/LOG={qa / "running-install.log"}'])
    process = launch()
    execute(setup, install + [f'/LOG={qa / "running-refused.log"}'], success=False)
    assert process.poll() is None, 'Silent install closed a running application without /CLOSEAPP'
    execute(setup, install + ['/CLOSEAPP', f'/LOG={qa / "running-upgrade.log"}'])
    assert process.wait(timeout=15) == 0, 'Normal upgrade did not wait for the packaged app'
    if args.foreground:
        process = launch()
        foreground = ['/CURRENTUSER', '/NORESTART', '/CINNAAUTO', '/CINNAQAEXIT', f'/DIR={application}', '/TASKS=']
        execute(setup, foreground + ['/CINNAQACLOSEAPP=refuse', f'/LOG={qa / "foreground-refused.log"}'], success=False)
        assert process.poll() is None, 'Foreground refusal closed the running application'
        execute(setup, foreground + ['/CINNAQACLOSEAPP=accept', f'/LOG={qa / "foreground-upgrade.log"}'])
        assert process.wait(timeout=15) == 0, 'Background transaction did not wait for foreground-authorized normal exit'
    process = launch()
    uninstaller = application / 'unins000.exe'
    execute(uninstaller, silent + [f'/LOG={qa / "running-uninstall-refused.log"}'], success=False)
    assert process.poll() is None, 'Silent uninstall closed the app without /CLOSEAPP'
    execute(uninstaller, silent + ['/CLOSEAPP', f'/LOG={qa / "running-uninstall.log"}'])
    assert process.wait(timeout=15) == 0, 'Normal uninstall did not wait for the packaged app'
    assert marker.read_text('utf-8') == 'preserve existing received files and settings'
    print('PASS packaged LanDrop: running install/uninstall refusal, explicit normal exit, worker wait and data preservation' + ('; foreground/backend consent and refusal' if args.foreground else ''))
finally:
    if process is not None and process.poll() is None:
        execute(root / 'dist/LanDrop.exe', ['--headless', '--prepare-upgrade', '--state-dir', str(state)])
        process.wait(timeout=20)
