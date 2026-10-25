# Windows installer

The three Cinna Windows apps use Inno Setup 7.1.0 for installation and a shared native C++ interface for the full-window scene, summary homepage, settings drawer and in-place progress/completion states. The interface needs only Windows system DLLs, including GDI+ and the Universal CRT supplied by Windows 10/11. It does not start a browser or require WebView2, Electron or .NET. The application payload retains its own runtime requirements.

`product.json` contains product identity, description, lifecycle protocol and legacy registration. `assets/` contains the approved product-specific day/night scenes, original PNGs, JPEG exports and integrity manifest. Keep the other shared files byte-identical in the three repositories. Run `export-scenes.ps1` only after intentionally replacing scene sources; `test-assets.ps1` and every build verify their identity, hashes, dimensions and distinct day/night text surfaces.

## Interface and permissions

The homepage shows the scope and destination. Installation settings provide current-user/all-users selection, a destination field and browser, and desktop/Start menu shortcuts. New installations default to current user and both shortcuts. Existing installations restore their scope, destination and saved shortcut preferences. Upgrades lock the old destination; changing it requires uninstalling first, with user data retained.

The foreground package runs without elevation and keeps its message loop independent of the installation transaction. On Install it starts the original Inno loader in a separate backend process for either scope, transferring the validated directory and tasks. All-users UAC occurs at that point. A versioned local shared-memory channel, restricted to the initiating user, SYSTEM and administrators, carries only bounded status, progress, confirmation and cancellation data. An owned mutex detects foreground-process exit. The parent releases maintenance locks before launch and waits for the backend process to exit before showing success or allowing app launch.

The backend uses /SILENT /SUPPRESSMSGBOXES. Its wizard remains logically visible, fully transparent and non-activating so Inno's normal cancellation path remains available; it presents no separate user interface. The foreground sends a cancellation request, Inno rolls back, then the existing recovery journal restores previous files. Application-exit confirmation is returned to the foreground; direct command-line silent maintenance still refuses a running app without /CLOSEAPP. No backend process is killed. Open uses the foreground's original-user context, only after success. The x64 payload retains Inno's x86 host.

Native buttons, fields, checkboxes, combobox and progress control retain their Windows accessibility providers. The chevron is inset from the edge. Completion buttons share their geometry. Cancel installation is a red filled button, and the confirmation defaults to Continue. Its callback requests normal Inno cancellation. Preparation, actual copy progress, errors and completion use the same canvas. System theme changes update the scene and controls; high-contrast mode removes the artwork.

## Maintenance and recovery

Setup and uninstall hold application maintenance and cross-session mutexes. They request normal application exit and wait for the host and workers. Silent maintenance refuses a running app unless `/CLOSEAPP` explicitly requests normal exit; `/CLOSEAPPLICATIONS` and `/FORCECLOSEAPPLICATIONS` are rejected. User settings, received files and unrelated files in the program directory remain after uninstall.

Before replacing a recognized installation, setup backs up the affected program files, installer-owned licenses, uninstall log, owned shortcuts and uninstall record in a unique adjacent `.Product.rollback-*` directory. Inno handles its normal rollback; afterwards the journal restores the old bytes and registration if the installation did not commit. Success removes only the journal's known files. Failed restoration keeps the recovery directory and reports its location. User data directories are never snapshotted or removed. Legacy registration and known old uninstallers are retired only after success; the legacy uninstaller never runs against new files.

## Build

The engine is pinned to Inno Setup 7.1.0. `build.ps1` validates the official download's SHA-256 and Pyrsys Authenticode publisher and extracts documented portable mode, avoiding compiler registration and associations. Use `INNOSETUP_ISCC` or `-CompilerPath` to reuse it.

The UI is built from source with Zig 0.15.2, also pinned to an official archive and SHA-256. Set `CINNA_ZIG` to reuse that compiler. The build verifies an x86 PE DLL and vendors the relevant Zig, LLVM, MinGW and Lucide notices. Application runtime prerequisites are checked separately; FanController/LanDrop validate the official Microsoft WebView2 bootstrapper. QA never installs a shared runtime.

Each setup has `.sha256` and `.build.json` companions. The record includes app/engine/UI compiler versions, UI DLL hash, shared sources, scene manifest, payload and installer-owned license hashes. Every delivered app or installer change increments the semantic application version. Use canonical versioned filenames, without r/custom revision suffixes. These three products retain only their latest release: verify and publish the new version before removing older distribution files and release objects. Source history and user data are separate from that cleanup.

## Validation

- `test.ps1 -PayloadDirectory <folder> -Version <version>`: isolated fresh install, Chinese/space paths, shortcut preferences, mutexes, upgrades, legacy migration, unsafe-path refusal, uninstall and data preservation.
- `test-custom.ps1` with the same arguments: initializes the real native interface and drives the Inno transaction; verifies fresh/upgrade completion, cancelled fresh cleanup, and cancelled upgrade recovery against every old file hash, including a deliberately different previous executable, plus the original uninstall record.
- `ui/test.ps1` (also run by `test-custom.ps1`): checks the real GDI+ gradient at 100/125/150/200% render scales, stable native controls and scene reuse across 40 drawer transitions, retained drafts, and distinct neutral minimize hover surfaces in both themes. The scene raster is cached until size, DPI or theme changes; drawer layout updates are composed and committed together.
- Existing app-specific lifecycle tests cover normal exit/refusal, tray/legacy windows and packaged LanDrop maintenance.

QA changes the registration, program/data directories, shortcuts and mutexes at compile time and restricts paths to one private `work`, `.local` or `.runtime` `inno-qa-<GUID>` root. QA-only auto-finish/cancellation switches do not exist in production builds. FanController launch uses its UI-QA mode; LanDrop uses a private state directory; do not launch NetworkToolbox's real UI against daily data.

Record visual mouse/keyboard/accessibility checks separately from transaction automation. Real UAC, missing-runtime clean machines, Windows 10, DPI/text scaling, high contrast, cross-monitor movement and physical hardware/network exit require their own verification. A local build or automated QA pass does not establish those results. See `docs/custom-installer-validation.md` for the current evidence and limits.

QA may opt into /CINNAQAPROBE to record real message-dispatch and owner-draw response latency during installation. The probe posts only to its own window; it sends no user input and does not measure compositor presentation or replace physical pointer verification.
