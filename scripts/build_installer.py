"""Build the branded Inno Setup installer from the verified portable payload."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from source_manifest import runtime_manifest

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--compiler', type=Path, help='Pinned Inno Setup 7.1.0 ISCC.exe')
parser.add_argument('--output', type=Path)
parser.add_argument('--qa-root', type=Path, help='Fresh .local/inno-qa-<GUID> directory')
parser.add_argument('--webview-bootstrapper', type=Path)
args = parser.parse_args()
version = json.loads((root / 'landrop/version.json').read_text('utf-8'))['version']
manifest = json.loads((root / 'build/build-manifest.json').read_text('utf-8'))
if manifest['version'] != version or manifest['runtimeSources'] != runtime_manifest(root):
    raise SystemExit('The application sources changed. Rebuild LanDrop.exe before packaging.')
payload = root / 'build/inno-payload'
payload.mkdir(parents=True, exist_ok=True)
for source, name in (
    (root / 'dist/LanDrop.exe', 'LanDrop.exe'),
    (root / 'resources/app.ico', 'app.ico'),
    (root / 'docs/使用说明.txt', '使用说明.txt'),
    (root / 'THIRD_PARTY_NOTICES.txt', 'THIRD_PARTY_NOTICES.txt'),
):
    shutil.copy2(source, payload / name)
output = args.output or (args.qa_root / 'LanDrop-inno-qa.exe' if args.qa_root else root / f'dist/LanDrop-v{version}-windows-x64-setup.exe')
command = ['pwsh', '-NoProfile', '-File', str(root / 'installer/inno/build.ps1'),
           '-PayloadDirectory', str(payload), '-Version', version, '-OutputFile', str(output.resolve())]
for name, value in (('-CompilerPath', args.compiler), ('-QaRoot', args.qa_root), ('-WebViewBootstrapper', args.webview_bootstrapper)):
    if value:
        command.extend((name, str(value.resolve())))
subprocess.run(command, check=True, cwd=root)
