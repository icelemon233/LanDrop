from __future__ import annotations

import hashlib
import json
from pathlib import Path


def runtime_manifest(root: Path) -> dict:
    paths = [root / name for name in ('main.py', 'project.json', 'requirements.txt', 'requirements-build.txt', 'package.json', 'pnpm-lock.yaml', 'tsconfig.json', 'resources/app.ico')]
    paths += list((root / 'landrop').glob('*.py')) + [root / 'landrop/version.json', root / 'landrop/ui_theme.json', root / 'landrop/window_shell.json']
    paths += [path for path in (root / 'frontend').rglob('*') if path.is_file()]
    paths += [root / 'scripts' / name for name in ('build.mjs', 'clean.mjs', 'package.py', 'source_manifest.py')]
    files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'digest': digest, 'files': files}
