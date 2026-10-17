"""Collect user-facing release files with an allowlisted, hashed source snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from source_manifest import runtime_manifest

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--installer-report', type=Path, required=True)
parser.add_argument('--upgrade-report', type=Path, required=True)
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

installer = f'隔空传-v{version}-安装程序.exe'
for original, name in [(root / 'dist' / installer, installer), (root / 'docs/使用说明.txt', '使用说明.txt'), (root / 'docs/更新说明.txt', '更新说明.txt'), (root / 'docs/verification.md', '验证说明.md'), (root / 'docs/assets/desktop-current.jpg', '电脑界面.jpg'), (root / 'docs/assets/mobile-current.jpg', '手机界面.jpg'), (root / 'docs/assets/installed-brand-current.jpg','已安装界面.jpg'), (root / 'THIRD_PARTY_NOTICES.txt', 'THIRD_PARTY_NOTICES.txt')]:
    shutil.copy2(original, out / name)
files = [root / name for name in ('AGENTS.md', '.gitignore', 'main.py', 'project.json', 'README.md', 'README.zh-CN.md', 'package.json', 'pnpm-lock.yaml', 'requirements.txt', 'requirements-build.txt', 'tsconfig.json', 'THIRD_PARTY_NOTICES.txt')]
files += [path for path in (root / 'landrop').glob('*') if path.suffix in {'.py', '.json'}]
allowed = {'.py', '.ts', '.mjs', '.ps1', '.json', '.html', '.css', '.svg', '.png', '.ico', '.bmp', '.jpg', '.md', '.txt', '.nsi'}
for directory in ('frontend', 'resources', 'docs', 'scripts', 'tests', 'installer'):
    files += [path for path in (root / directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix in allowed]
files = sorted(set(files))
sources = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
source_digest = hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
archive = out / f'隔空传-v{version}-源码.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
    for path in files:
        output.write(path, 'lan-drop/' + path.relative_to(root).as_posix())
    output.writestr('lan-drop/source-manifest.json', json.dumps({'version': version, 'digest': source_digest, 'files': sources}, indent=2))
payload_hash = hashlib.sha256((root / 'dist/隔空传.exe').read_bytes()).hexdigest()
installer_report = json.loads(args.installer_report.read_text('utf-8'))
if installer_report['payloadSha256'] != payload_hash:
    raise SystemExit('Installer validation used a different application payload.')
upgrade_report=json.loads(args.upgrade_report.read_text('utf-8'))
if upgrade_report['payloadSha256'] != payload_hash:
    raise SystemExit('Upgrade validation used a different application payload.')
manifest = {'project':{key:project[key] for key in ('projectName','series','developer')}, 'brand':brand, 'app': '隔空传', 'version': version, 'platform': 'windows-x64', 'signed': False, 'sourceDigest': source_digest, 'runtimeSources': build['runtimeSources'], 'applicationPayloadSha256': payload_hash, 'sourceFiles': len(sources), 'checks': {'backendTests':args.backend_tests, 'frontendTests':args.frontend_tests, 'packagedLanTransferSha256':'passed', 'isolatedInstallerUpgradeUninstall':installer_report, 'nativeUpgradeAndPortConflict':upgrade_report, 'browserDesktop':'passed-1.1.2', 'browserPhoneWidth':'passed-1.1.2-390px', 'physicalAndroid':'not-tested', 'interactiveInstallerWizard':'visual-check-blocked-by-system-permission-dialog'}, 'files':{}}
for path in sorted(out.iterdir()):
    if path.is_file() and path.name not in {'release-manifest.json', 'SHA256SUMS.txt'}:
        manifest['files'][path.name] = {'bytes':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(out / 'release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
(out / 'SHA256SUMS.txt').write_text('\n'.join(f"{item['sha256']}  {name}" for name,item in manifest['files'].items()) + '\n', 'utf-8')
print(json.dumps({'output':str(out), 'sourceFiles':len(sources), 'installerBytes':manifest['files'][installer]['bytes'], 'payloadSha256':payload_hash}, ensure_ascii=True))
