from importlib.metadata import distribution
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
parts = ['LanDrop — Third-party notices\n\nThis distribution contains Python, Tcl/Tk, qrcode, pywebview and Python.NET dependencies, and is packaged with the PyInstaller bootloader. The installer uses Inno Setup 7.1.0: https://jrsoftware.org/ . Microsoft Edge WebView2 is distributed under Microsoft terms: https://developer.microsoft.com/microsoft-edge/webview2/ . The following notices are reproduced from the installed distributions.\n']
for name in ['qrcode', 'colorama', 'pyinstaller', 'pywebview', 'pythonnet', 'clr_loader', 'cffi', 'pycparser', 'proxy_tools', 'bottle', 'typing_extensions']:
    installed = distribution(name)
    for item in installed.files or []:
        if any(word in str(item).lower() for word in ('license', 'licence', 'copying')):
            path = Path(installed.locate_file(item))
            parts.append(f'\n\n=== {name} {installed.version} — {path.name} ===\n\n' + path.read_text('utf-8'))
python_root = Path(sys.base_prefix)
for path in [python_root / 'LICENSE.txt', python_root / 'tcl/tk8.6/license.terms', python_root / 'tcl/tcl8.6/license.terms', root / 'resources/licenses/inno-setup.txt', root / 'resources/licenses/lucide.txt']:
    if path.exists():
        name = 'Python' if path.name == 'LICENSE.txt' else 'Inno Setup' if path.name == 'inno-setup.txt' else 'Lucide 1.61.0' if path.name == 'lucide.txt' else path.parent.name
        parts.append(f'\n\n=== {name} ===\n\n' + path.read_text('utf-8'))
(root / 'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(parts), 'utf-8')
print('Dependency notices collected.')
