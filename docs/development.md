# Development

Use Python 3.12 with Tk, Node.js 22+ and pnpm 11.25.0 on Windows x64. The desktop host uses pywebview with the installed Microsoft Edge WebView2 Runtime. Tk is used only for startup errors and upgrade confirmation before the main window exists. Application version comes from `landrop/version.json`; Python, the HTTP health endpoint, PE resources and installer use it.

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
| desktop_window | Independent Windows window, UI-thread file pickers, restricted navigation, minimize on close, activation and explicit shutdown |
| desktop, platform_identity, window_runtime | Pre-window prompts, stable Windows identity and WebView2 detection |
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

The smoke test uses Python's standard `BROWSER` override as a trap: any external-browser launch fails the check. With isolated `--test-data`, the real window records a read-only observation of its authenticated UI, then the script checks window reuse, redirect/cookie flow, restart and file hashes. The observer does not operate the GUI or record connection credentials. Headless mode is explicit; it does not launch a browser. The legacy `--no-browser` flag remains accepted for compatibility.

For installer QA, build with `--qa-state` and a unique `--qa-id`; use fresh paths under the project's ignored `.local/` directory. Registry keys, shortcuts, files and user data remain isolated. The Microsoft bootstrapper is pinned in `resources/webview2-bootstrapper.json`; the builder checks its hash and Microsoft Authenticode signature. Only missing runtimes are installed. The bootstrapper and NSIS tools are build inputs, not source files.

The original Cinna portrait is in `resources/cinna-portrait.png`. Use Pillow with `scripts/export_brand.py` to re-export icons. Light colors follow Cinna tokens; dark colors are a local adaptation. Assets and fonts are not fetched at runtime.
