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
| desktop_window | Independent Windows window, UI-thread file pickers, restricted navigation, saved close behavior, tray, activation and explicit shutdown |
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
python scripts/build_installer.py
python scripts/test_installer.py
```

The installer uses pinned Inno Setup 7.1.0 and the [shared native installer](../installer/inno/README.md). The compiler download is verified by SHA-256 and publisher, then used in portable mode. `--compiler <ISCC.exe>` selects an existing copy. The settings drawer offers current-user/all-users scope, a destination and separate desktop/Start menu choices. All-users mode requests Windows elevation only after Install. Current-user mode does not.

Setup and uninstall share a maintenance mutex and request normal exit through the existing authenticated application protocol. `/VERYSILENT /CURRENTUSER /SUPPRESSMSGBOXES /NORESTART` refuses a running app; adding `/CLOSEAPP` permits normal shutdown. No process is force-killed. Legacy registration is retired after a successful install in its existing directory. Changing an existing destination requires uninstalling first. User data and unrelated installation-directory files remain.

The smoke test uses Python's standard `BROWSER` override as a trap: any external-browser launch fails the check. With isolated `--test-data`, the real window records a read-only observation of its authenticated UI, then the script checks window reuse, redirect/cookie flow, restart and file hashes. The observer does not operate the GUI or record connection credentials. Headless mode is explicit; it does not launch a browser. The legacy `--no-browser` flag remains accepted for compatibility.

For an isolated visible native installer, pass `--qa-root .local/inno-qa-<32-character GUID>`; the root must be inside this project. Registry keys, shortcuts, files and user data are isolated at compile time. `scripts/test_installer.py` builds its own QA installer. The Microsoft bootstrapper remains pinned in `resources/webview2-bootstrapper.json`; the builder verifies its hash and Microsoft signature. QA refuses to modify shared runtimes. All-users UAC and a genuinely missing runtime need separate interactive verification.

The original Cinna portrait is in `resources/cinna-portrait.png`. Use Pillow with `scripts/export_brand.py` to re-export icons. WebView and native caption/menu colors come from landrop/ui_theme.json; scripts/build.mjs generates the browser theme stylesheet. Assets and fonts are not fetched at runtime.

The full-window scene, settings drawer, red cancellation button, completion actions and upgrade recovery share one implementation. Run `installer/inno/test-custom.ps1` alongside the existing installer tests. Current evidence and manual verification limits are in [custom-installer-validation.md](custom-installer-validation.md).
