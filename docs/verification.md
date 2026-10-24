# Version 1.2.4 verification

See [the 1.2.4 native caption fix](titlebar-verification-1.2.4.md) for rendered native controls, input hit tests and minimize/maximize/restore state checks.

## Version 1.2.3 verification

See [LanDrop 1.2.3 UI verification](ui-verification-20261024.md) for the 2026-10-24 changes, screenshots, checks and remaining native-input/device checks. The record below describes the previous 1.2.2 release.

# Version 1.2.2 verification

The Windows desktop host uses an independent WinForms/WebView2 window. The phone interface remains in the phone's browser. Source inputs and the packaged executable are checked against the build manifest; the release manifest records source and artifact hashes.

| Area | Result |
| --- | --- |
| Automated checks | 77 backend tests, 8 frontend tests, TypeScript checking and the production frontend build passed |
| Actual Windows executable | The embedded UI authenticated as the local administrator; cold launch, repeat launch, shutdown and restart passed |
| External browser | A browser-launch trap remained unused during first launch, duplicate launch, upgrade and restart |
| Repeat launch | The original process and window were reused; files passed to the second launch appeared in the shared list |
| LAN transfer | Synthetic files larger than 5 MB transferred in both directions through the LAN endpoint with matching SHA-256 hashes |
| Upgrade | Old 1.2.1 native and headless copies upgraded to 1.2.2; settings, shared paths and received files were preserved |
| Port isolation | Separate data directories authenticated through separate listeners when their requested port was occupied |
| Installer window | The isolated QA wizard opened normally. After minimizing it, opening a second copy restored the original window without a duplicate-warning dialog |
| Installer dialogs | A repeat launch while the wizard's cancellation confirmation was open returned to that owned dialog; cancelling the original released its lock so a later installation could proceed |
| Concurrent maintenance | Silent repeat launch returned code 12 without restoring the minimized wizard. Both setup and uninstall returned 12 under a held maintenance mutex and 21 when lock creation failed, leaving installed files intact |
| Restore and exit | Reopening the application reused its original process. Explicit authenticated shutdown and restart passed |
| Installer | Isolated per-user installation, old-version migration, running silent refusal, normal exit, reinstallation and uninstallation passed |
| User data | Isolated installer tests retained shared settings, received files and files not installed by the application |
| Windows identity | The QA application, installer and uninstaller used matching icon resources; publisher Cinna and desktop/Start menu icon references were checked |
| Runtime delivery | The Microsoft-signed WebView2 bootstrapper's hash and signature were verified; the installer checks whether the runtime is already present |
| Current-user installation | The final installer updated the installed executable and Windows registration from 1.2.1 to 1.2.2; user-file snapshots matched before and after. Daily-context launch was not repeated; native startup was checked separately with isolated data |

All transfer and GUI fixtures use isolated synthetic data. Installer GUI tests use a separate QA AppKey, shortcuts and state directory; the final installer uses the same NSIS source and application payload. DOM observations are read-only and contain readiness, role, layout and title information; they do not record connection credentials. Real GUI observations were inspected privately, without exporting screenshots containing pairing details.

The application payload SHA-256 is `de540cdd1cb98ccd35e33cb3a1d9e42f69eb50f45c613eae0bb8163cab061190`. Packaging and release collection reject mismatched source inputs or validation reports from another payload.

Physical Android QR scanning and installation prompts, Windows 10, multiple Windows accounts and installation on a machine lacking WebView2 remain unverified. Existing-runtime behavior was tested. The distribution is unsigned. No firewall or system privacy settings were changed.
