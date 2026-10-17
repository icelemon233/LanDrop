# Development

Use Python 3.12 with Tk, Node.js 22+ and pnpm 11.25.0 on Windows x64. Application version comes from `landrop/version.json`; Python, the HTTP health endpoint, PE resources and installer use it.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-build.txt
pnpm install --frozen-lockfile
pnpm check
pnpm build
pnpm test
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe main.py
```

Synthetic UI fixtures require both `--test-data` and a separate `--state-dir`. The app displays a test banner. A headless test run uses `--headless --no-browser --port 0`. Do not use real user data for tests. Generated `landrop/web/` is excluded from the source archive; build it before running.

## Boundaries

| Module | Responsibility |
| --- | --- |
| main, launcher, runtime, processes | Composition, authenticated startup, DPAPI runtime info, instance lock, orderly upgrade |
| settings | Validation, protected corrupt state, atomic commits and explicit recovery |
| state, files | Catalog, background scans, path and opened-handle checks |
| sessions, transfers | Connection lifecycle, owner-bound idempotent uploads and final commit |
| server | HTTP, host/origin checks, separate local/LAN worker budgets, socket cleanup |
| desktop | Main-thread native dialogs and shutdown coordination |
| frontend/api, session | Nested response validation, shared reads, late-response rejection |
| frontend/features, ui | File lists, upload queue, dialogs, preferences and rendering |

Settings and committed uploads are server facts. The UI distinguishes confirmed cancellation from an unknown outcome and can check the same task ID. File blobs are not persisted in browser storage. Scanner limits per root are 30,000 files, 5,000 directories and about five seconds. Links and hidden paths are skipped.

Windows downloads verify the actual handle with [GetFinalPathNameByHandleW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew). Runtime credentials use [DPAPI](https://learn.microsoft.com/en-us/windows/win32/seccrypto/example-c-program-using-cryptprotectdata).

Automatic port selection skips browser-blocked ports from the [Fetch standard](https://fetch.spec.whatwg.org/#port-blocking). An explicitly blocked port is rejected before startup.

## Package

```powershell
python scripts/package.py
python scripts/smoke_exe.py dist/LanDrop.exe
python scripts/build_installer.py --nsis-archive D:/Tools/nsis-3.13.zip
```

Use the official NSIS 3.13 ZIP from [NSIS](https://nsis.sourceforge.io/Download), SHA-256 `ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8`. The build verifies it before extraction. See the [NSIS manual](https://nsis.sourceforge.io/Docs/Chapter4.html) for syntax. Installation is per user, with a directory page, Start menu and optional desktop shortcut. `/S` refuses a running app; explicit `/CLOSEAPP` allows normal shutdown. Never force-kill an old app to replace it.

The smoke test uses Python's standard `BROWSER` override to capture real launch URLs, then checks redirect/cookie flow and file hashes. It does not automate the default browser. For installer QA, build with `--qa-state` and a unique `--qa-id`; `scripts/test_installer.py` checks only QA paths under work/ so app data, registry and shortcuts are isolated.

The original Cinna portrait is in `resources/cinna-portrait.png`. Use Pillow with `scripts/export_brand.py` to re-export icons. Light colors follow Cinna tokens; dark colors are a local adaptation. Assets and fonts are not fetched at runtime.
