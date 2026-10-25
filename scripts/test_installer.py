"""Run Inno installation and data-preservation QA without using the daily installation."""
import argparse
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--compiler', type=Path)
args = parser.parse_args()
version = json.loads((root / 'landrop/version.json').read_text('utf-8'))['version']
command = ['pwsh', '-NoProfile', '-File', str(root / 'installer/inno/test.ps1'),
           '-PayloadDirectory', str(root / 'build/inno-payload'), '-Version', version]
if args.compiler:
    command.extend(('-CompilerPath', str(args.compiler.resolve())))
subprocess.run(command, check=True, cwd=root)
