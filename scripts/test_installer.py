"""Exercise only a uniquely named QA installer in this task's work directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import winreg
import pefile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from landrop.runtime import RuntimeStore
from landrop.launcher import local_client, post
from landrop import __version__
parser = argparse.ArgumentParser()
parser.add_argument('--setup', type=Path, required=True)
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--install-dir', type=Path, required=True)
parser.add_argument('--qa-id', required=True)
parser.add_argument('--legacy', type=Path)
args = parser.parse_args()
for path in (args.setup, args.state, args.install_dir):
    if not path.resolve().is_relative_to(root.parent):
        raise SystemExit('Installer QA paths must remain under work/.')
key = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\LanDrop.Cinna.QA.' + args.qa_id
flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def execute(command, expected=0):
    result = subprocess.run([str(item) for item in command], timeout=70, creationflags=flags)
    assert result.returncode == expected, (command[0], result.returncode, expected)

def launch(exe, legacy=False):
    process = subprocess.Popen([str(exe), '--headless', '--no-browser', '--port', '0', '--state-dir', str(args.state)], creationflags=flags)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('QA app exited before startup')
        info = RuntimeStore(args.state / 'runtime.json').read()
        if info:
            return process, info
        time.sleep(.1)
    raise RuntimeError('QA startup timed out')

def registry():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as handle:
        return {name: winreg.QueryValueEx(handle, name)[0] for name in ('DisplayVersion', 'InstallLocation', 'DisplayName', 'Publisher', 'DisplayIcon')}

exe = args.install_dir / '隔空传.exe'
setup = args.setup.resolve(strict=True)
try:
    registry()
except FileNotFoundError:
    pass
else:
    raise SystemExit('QA registration already exists; inspect it before retrying.')
args.state.mkdir(parents=True, exist_ok=True)
received = args.state / '收到的文件'
received.mkdir(exist_ok=True)
keep = received / '保留文件.txt'
keep.write_bytes(b'preserve received data')
source = args.state.parent / 'shared.apk'
source.write_bytes(b'synthetic installer QA')

if args.legacy:
    old, _ = launch(args.legacy, True)
    execute([setup, '/S', '/D=' + str(args.install_dir)], 10)
    assert old.poll() is None and not exe.exists()
    execute([setup, '/S', '/CLOSEAPP', '/D=' + str(args.install_dir)])
    old.wait(timeout=15)
else:
    execute([setup, '/S', '/D=' + str(args.install_dir)])
assert registry()['DisplayVersion'] == __version__
assert registry()['InstallLocation'] == str(args.install_dir)
project=json.loads((root/'project.json').read_text('utf-8'))
assert registry()['Publisher']==project['developer']
assert registry()['DisplayIcon']==str(args.install_dir/'app.ico')+',0'
assert (args.install_dir/'app.ico').read_bytes()==(root/'resources/app.ico').read_bytes()
def icon_resources(path):
    image=pefile.PE(data=path.read_bytes())
    group=next(item for item in image.DIRECTORY_ENTRY_RESOURCE.entries if item.id==3)
    return sorted(hashlib.sha256(image.get_data(entry.directory.entries[0].data.struct.OffsetToData,entry.directory.entries[0].data.struct.Size)).hexdigest() for entry in group.directory.entries)
assert icon_resources(exe)==icon_resources(args.install_dir/'Uninstall.exe')
assert icon_resources(exe)==icon_resources(setup)
shortcut_command = ['powershell', '-NoProfile', '-File', root / 'scripts/check_shortcuts.ps1', '-InstallRoot', args.install_dir, '-QaId', args.qa_id, '-StateDirectory', args.state]
execute(shortcut_command)
original_hash = hashlib.sha256(exe.read_bytes()).hexdigest()
untracked = args.install_dir / 'KeepMe.txt'
untracked.write_bytes(b'not installed by application')
process, info = launch(exe)
client = local_client()
base = f'http://127.0.0.1:{info.port}'
post(client, base, '/api/session', {'role': 'admin', 'token': info.secret})
post(client, base, '/api/admin/add-files', {'paths': [str(source)]})
settings = (args.state / 'settings.json').read_bytes()
execute([setup, '/S', '/D=' + str(args.install_dir)], 10)
assert process.poll() is None
assert hashlib.sha256(exe.read_bytes()).hexdigest() == original_hash
execute([setup, '/S', '/CLOSEAPP', '/D=' + str(args.install_dir)])
process.wait(timeout=15)
assert (args.state / 'settings.json').read_bytes() == settings
assert untracked.read_bytes() == b'not installed by application'
process, info = launch(exe)
execute([args.install_dir / 'Uninstall.exe', '/S', '_?=' + str(args.install_dir)], 10)
assert process.poll() is None
execute([args.install_dir / 'Uninstall.exe', '/S', '/CLOSEAPP', '_?=' + str(args.install_dir)])
process.wait(timeout=15)
# _?= deliberately disables NSIS's temporary uninstaller copy. Its caller
# must remove that now-exited test uninstaller; normal interactive removal
# uses the automatic temporary copy instead.
(args.install_dir / 'Uninstall.exe').unlink(missing_ok=True)
assert not exe.exists()
assert not (args.install_dir/'app.ico').exists()
assert keep.read_bytes() == b'preserve received data'
assert (args.state / 'settings.json').read_bytes() == settings
assert source.exists() and untracked.exists()
execute(shortcut_command + ['-Removed'])
try:
    registry()
except FileNotFoundError:
    pass
else:
    raise AssertionError('Uninstall registry entry remains')
report = {'passed': ['per-user installation', 'running silent installation refused', 'normal app and bootloader exit', 'in-place reinstallation', 'running silent uninstallation refused', 'uninstall registration removed', 'shared settings preserved', 'received files preserved', 'untracked install file preserved','Cinna publisher','desktop and Start menu icon references','matching app, installer and uninstaller image resources'], 'legacyMigration': bool(args.legacy), 'payloadSha256': original_hash}
(args.state.parent / 'installer-validation.json').write_text(json.dumps(report, indent=2), 'utf-8')
print(json.dumps(report, ensure_ascii=True, indent=2))
