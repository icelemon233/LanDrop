"""Collect user-facing release files with an allowlisted, hashed source snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
import subprocess
from pathlib import Path

from source_manifest import runtime_manifest

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--installer-report', type=Path, required=True)
parser.add_argument('--upgrade-report', type=Path, required=True)
parser.add_argument('--packaged-report', type=Path, required=True)
parser.add_argument('--window-report', type=Path, required=True)
parser.add_argument('--installed-report', type=Path, required=True)
parser.add_argument('--backend-tests', type=int, required=True)
parser.add_argument('--frontend-tests', type=int, default=8)
args = parser.parse_args()
version = json.loads((root / 'landrop/version.json').read_text('utf-8'))['version']
build = json.loads((root / 'build/build-manifest.json').read_text('utf-8'))
if build['version'] != version or build['runtimeSources'] != runtime_manifest(root):
    raise SystemExit('Packaged runtime does not match the current source. Rebuild first.')
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)

project=json.loads((root/'project.json').read_text('utf-8'))
brand=json.loads((root/'resources/brand/manifest.json').read_text('utf-8'))
for name,digest in brand['files'].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
        raise SystemExit('Brand export does not match its manifest: '+name)
with zipfile.ZipFile(out/'图标素材.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as images:
    for name in brand['files']:
        images.write(root/name,name)
    for name in ('source','identityReference','styleReference'):
        images.write(root/project['brand'][name],project['brand'][name])
    images.write(root/'resources/brand/manifest.json','brand-manifest.json')
    images.write(root/'project.json','project.json')
shutil.copy2(root/'project.json',out/'工程信息.json')

installer = f'LanDrop-v{version}-windows-x64-setup.exe'
for original, name in [(root / 'dist' / installer, installer), (root / 'docs/使用说明.txt', '使用说明.txt'), (root / 'docs/更新说明.txt', '更新说明.txt'), (root / 'docs/verification.md', '验证说明.md'), (root / 'THIRD_PARTY_NOTICES.txt', 'THIRD_PARTY_NOTICES.txt')]:
    shutil.copy2(original, out / name)
portable = out / f'LanDrop-v{version}-windows-x64.zip'
with zipfile.ZipFile(portable, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
    for name, source in (('LanDrop.exe', root/'dist/LanDrop.exe'), ('使用说明.txt', root/'docs/使用说明.txt'), ('THIRD_PARTY_NOTICES.txt', root/'THIRD_PARTY_NOTICES.txt')):
        output.write(source, name)
files = [root / name for name in ('AGENTS.md', '.gitignore', 'main.py', 'project.json', 'README.md', 'README.zh-CN.md', 'package.json', 'pnpm-lock.yaml', 'requirements.txt', 'requirements-build.txt', 'tsconfig.json', 'THIRD_PARTY_NOTICES.txt')]
files += [path for path in (root / 'landrop').glob('*') if path.suffix in {'.py', '.json'}]
allowed = {'.py', '.ts', '.mjs', '.ps1', '.json', '.html', '.css', '.svg', '.png', '.ico', '.bmp', '.jpg', '.md', '.txt', '.nsi', '.yml', '.yaml'}
for directory in ('frontend', 'resources', 'docs', 'scripts', 'tests', 'installer', '.github'):
    files += [path for path in (root / directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix in allowed]
files = sorted(set(files))
sources = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
source_digest = hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
archive = out / f'LanDrop-v{version}-源码.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
    for path in files:
        output.write(path, 'LanDrop/' + path.relative_to(root).as_posix())
    output.writestr('LanDrop/source-manifest.json', json.dumps({'version': version, 'digest': source_digest, 'files': sources}, indent=2))
payload_hash = hashlib.sha256((root / 'dist/LanDrop.exe').read_bytes()).hexdigest()
installer_report = json.loads(args.installer_report.read_text('utf-8'))
if installer_report['payloadSha256'] != payload_hash:
    raise SystemExit('Installer validation used a different application payload.')
upgrade_report=json.loads(args.upgrade_report.read_text('utf-8'))
if upgrade_report['payloadSha256'] != payload_hash:
    raise SystemExit('Upgrade validation used a different application payload.')
packaged_report=json.loads(args.packaged_report.read_text('utf-8'))
window_report=json.loads(args.window_report.read_text('utf-8'))
installed_report=json.loads(args.installed_report.read_text('utf-8'))
for record in (packaged_report, window_report, installed_report):
    if record['payloadSha256'] != payload_hash:
        raise SystemExit('Desktop validation used a different application payload.')
if packaged_report.get('externalBrowserLaunched') is not False:
    raise SystemExit('The independent desktop window was not validated.')
commit=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,check=True).stdout.strip()
dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=root,capture_output=True,text=True,check=True).stdout.strip())
if dirty:
    raise SystemExit('Commit the reviewed source before collecting the final release.')
manifest = {'project':{key:project[key] for key in ('projectName','series','developer')}, 'brand':brand, 'app': 'LanDrop', 'version': version, 'platform': 'windows-x64', 'signed': False, 'sourceCommit':commit, 'sourceDirty':dirty, 'sourceDigest': source_digest, 'runtimeSources': build['runtimeSources'], 'applicationPayloadSha256': payload_hash, 'sourceFiles': len(sources), 'checks': {'backendTests':args.backend_tests, 'frontendTests':args.frontend_tests, 'packagedDesktopAndLan':packaged_report, 'realWindow':window_report, 'currentUserInstallation':installed_report, 'isolatedInstallerUpgradeUninstall':installer_report, 'nativeUpgradeAndPortConflict':upgrade_report, 'physicalAndroid':'not-tested', 'windows10':'not-tested', 'missingRuntimeInstallation':'bundled-and-signature-verified; tested with installed runtime'}, 'files':{}}
for path in sorted(out.iterdir()):
    if path.is_file() and path.name not in {'release-manifest.json', 'SHA256SUMS.txt'}:
        manifest['files'][path.name] = {'bytes':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(out / 'release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
(out / 'SHA256SUMS.txt').write_text('\n'.join(f"{item['sha256']}  {name}" for name,item in manifest['files'].items()) + '\n', 'utf-8')
print(json.dumps({'output':str(out), 'sourceFiles':len(sources), 'installerBytes':manifest['files'][installer]['bytes'], 'payloadSha256':payload_hash}, ensure_ascii=True))
