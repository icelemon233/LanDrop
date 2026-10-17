import json
from pathlib import Path

__version__ = json.loads(Path(__file__).with_name('version.json').read_text('utf-8'))['version']
