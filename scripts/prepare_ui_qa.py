"""Prepare isolated UI QA data without opening a window or touching daily data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from landrop.state import State

parser = argparse.ArgumentParser()
parser.add_argument('--state-dir', type=Path, required=True)
parser.add_argument('--hidden', action='store_true', help='Collect own-window observations without occupying the desktop.')
args = parser.parse_args()
directory = args.state_dir.resolve()
if not directory.is_relative_to(ROOT / '.local') or directory == ROOT / '.local':
    raise SystemExit('UI QA data must live in a dedicated directory below .local/.')
if (directory / 'runtime.json').exists():
    raise SystemExit('Exit this QA instance normally before preparing its window options.')
directory.mkdir(parents=True, exist_ok=True)
if not (directory / 'settings.json').exists():
    state = State(directory, test_mode=True)
    state.set_window_preference('windowTheme', 'dark')
    state.set_window_preference('trayNoticeSeen', True)
    state.set_name('LanDrop QA')
(directory / 'qa-window.json').write_text(json.dumps({'hidden': args.hidden, 'view': 'settings'}), 'utf-8')
print(directory)
