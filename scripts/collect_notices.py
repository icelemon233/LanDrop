from importlib.metadata import distribution
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
parts = ['隔空传 — Third-party notices\n\nThis distribution contains Python, Tcl/Tk, qrcode and colorama, and is packaged with the PyInstaller bootloader. The installer uses unmodified NSIS 3.13 including LZMA. NSIS source: https://nsis.sourceforge.io/Download . The following notices are reproduced from the installed distributions.\n']
for name in ['qrcode', 'colorama', 'pyinstaller']:
    installed = distribution(name)
    for item in installed.files or []:
        if any(word in str(item).lower() for word in ('license', 'licence', 'copying')):
            path = Path(installed.locate_file(item))
            parts.append(f'\n\n=== {name} {installed.version} — {path.name} ===\n\n' + path.read_text('utf-8'))
python_root = Path(sys.base_prefix)
for path in [python_root / 'LICENSE.txt', python_root / 'tcl/tk8.6/license.terms', python_root / 'tcl/tcl8.6/license.terms', root / 'resources/licenses/nsis.txt']:
    if path.exists():
        name = 'Python' if path.name == 'LICENSE.txt' else 'NSIS' if path.name == 'nsis.txt' else path.parent.name
        parts.append(f'\n\n=== {name} ===\n\n' + path.read_text('utf-8'))
(root / 'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(parts), 'utf-8')
print('Dependency notices collected.')
