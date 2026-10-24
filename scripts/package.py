from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from source_manifest import runtime_manifest

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Build the Windows portable executable.')
parser.add_argument('--mode', choices=['onefile', 'onedir'], default='onefile')
parser.add_argument('--output', type=Path, default=root / 'dist')
args = parser.parse_args()
if not (root / 'landrop/web/assets/app.js').is_file():
    raise SystemExit('Run pnpm build before packaging.')
version = json.loads((root / 'landrop/version.json').read_text('utf-8'))['version']
project = json.loads((root / 'project.json').read_text('utf-8'))
source = runtime_manifest(root)
parts = tuple(int(part) for part in version.split('.')) + (0,)
metadata = f'''VSVersionInfo(ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable('080404B0', [StringStruct('CompanyName',{project['developer']!r}), StringStruct('FileDescription','LanDrop · 局域网文件传输'), StringStruct('FileVersion','{version}'), StringStruct('InternalName',{project['projectName']!r}), StringStruct('LegalCopyright',{project['developer']!r}), StringStruct('OriginalFilename','LanDrop.exe'), StringStruct('ProductName','LanDrop'), StringStruct('ProductVersion','{version}')])]), VarFileInfo([VarStruct('Translation',[2052,1200])])])'''
metadata_path = root / 'build/version.txt'
metadata_path.parent.mkdir(parents=True, exist_ok=True)
metadata_path.write_text(metadata, 'utf-8')
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
    '--' + args.mode, '--name', 'LanDrop', '--noupx',
    '--distpath', str(args.output.resolve()), '--workpath', str(root / 'build' / args.mode),
    '--specpath', str(root / 'build'),
    '--icon', str(root / 'resources/app.ico'),
    '--version-file', str(metadata_path),
    '--add-data', str(root / 'landrop/web') + ';landrop/web',
    '--add-data', str(root / 'landrop/version.json') + ';landrop',
    '--add-data', str(root / 'landrop/ui_theme.json') + ';landrop',
    '--add-data', str(root / 'resources/app.ico') + ';resources',
    '--hidden-import', 'qrcode.image.svg',
    '--hidden-import', 'webview.platforms.winforms',
    '--hidden-import', 'webview.platforms.edgechromium',
    '--collect-all', 'webview',
    '--collect-all', 'pythonnet',
    '--collect-all', 'clr_loader',
    '--exclude-module', 'unittest',
    str(root / 'main.py'),
], check=True, cwd=root)
if runtime_manifest(root) != source:
    raise SystemExit('Source changed during the build. Rebuild before delivery.')
(root / 'build/build-manifest.json').write_text(json.dumps({'version': version, 'runtimeSources': source}, indent=2), 'utf-8')
