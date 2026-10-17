"""Build a current-user NSIS installer from the pinned, verified compiler archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--nsis-archive', type=Path, required=True, help='Official nsis-3.13.zip')
parser.add_argument('--output', type=Path)
parser.add_argument('--qa-state', type=Path, help='Isolated installer test only')
parser.add_argument('--qa-id', default='')
args = parser.parse_args()
version = json.loads((root / 'landrop/version.json').read_text('utf-8'))['version']
project = json.loads((root / 'project.json').read_text('utf-8'))
expected = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
archive = args.nsis_archive.resolve(strict=True)
with archive.open('rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
        raise SystemExit('NSIS 3.13 archive checksum mismatch.')
tool_dir = root / 'build/tools'
tool_dir.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(archive) as source:
    for member in source.infolist():
        if not (tool_dir / member.filename).resolve().is_relative_to(tool_dir.resolve()):
            raise SystemExit('Unexpected compiler archive path.')
    for member in source.infolist():
        target=tool_dir/member.filename
        if member.is_dir():
            target.mkdir(parents=True,exist_ok=True)
        elif not target.is_file() or hashlib.sha256(target.read_bytes()).digest()!=hashlib.sha256(source.read(member)).digest():
            source.extract(member,tool_dir)
compiler = tool_dir / 'nsis-3.13/makensis.exe'
payload = root / 'build/installer-payload'
payload.mkdir(parents=True, exist_ok=True)
shutil.copy2(root / 'dist/隔空传.exe', payload / '隔空传.exe')
shutil.copy2(root / 'resources/app.ico', payload / 'app.ico')
shutil.copy2(root / 'docs/使用说明.txt', payload / '使用说明.txt')
shutil.copy2(root / 'THIRD_PARTY_NOTICES.txt', payload / 'THIRD_PARTY_NOTICES.txt')
output = (args.output or root / f'dist/隔空传-v{version}-安装程序.exe').resolve()
output.parent.mkdir(parents=True, exist_ok=True)
size = sum(path.stat().st_size for path in payload.iterdir())
command = [str(compiler), '/V2', '/INPUTCHARSET', 'UTF8', f'/DProjectRoot={root}', f'/DAppVersion={version}', f'/DDeveloper={project["developer"]}', f'/DPayload={payload}', f'/DOutputFile={output}', f'/DInstalledSizeKB={(size + 1023) // 1024}']
if args.qa_state:
    if not args.qa_id or not args.qa_id.isalnum():
        raise SystemExit('QA build needs an alphanumeric --qa-id.')
    state = args.qa_state.resolve()
    if not state.is_relative_to(root.parent.resolve()):
        raise SystemExit('QA data must stay inside the task work directory.')
    data_args = '--state-dir $\\"' + str(state).replace('$', '$$') + '$\\"'
    command.extend([f'/DAppKey=LanDrop.Cinna.QA.{args.qa_id}', f'/DShortcutName=隔空传 QA {args.qa_id}', f'/DDataArgs={data_args}'])
command.append(str(root / 'installer/setup.nsi'))
subprocess.run(command, check=True, cwd=root)
print(output)
