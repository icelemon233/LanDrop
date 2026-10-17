# Version 1.2.1 verification

The Windows desktop host uses an independent WinForms/WebView2 window. The phone interface remains in the phone's browser. Source inputs and the packaged executable are checked against the build manifest; the release manifest records source and artifact hashes.

| Area | Result |
| --- | --- |
| Automated checks | 77 backend tests, 8 frontend tests, TypeScript checking and the production frontend build passed |
| Actual Windows executable | The embedded UI authenticated as the local administrator; cold launch, repeat launch, shutdown and restart passed |
| External browser | A browser-launch trap remained unused during first launch, duplicate launch, upgrade and restart |
| Repeat launch | The original process and window were reused; files passed to the second launch appeared in the shared list |
| LAN transfer | Synthetic files larger than 5 MB transferred in both directions through the LAN endpoint with matching SHA-256 hashes |
| Upgrade | Old 1.2.0 native and headless copies upgraded to 1.2.1; settings, shared paths and received files were preserved |
| Port isolation | Separate data directories authenticated through separate listeners when their requested port was occupied |
| Title-bar close | Clicking the real close button minimized the Windows window. The original process and service remained available while an 8 MB upload continued to completion; upload and download hashes matched |
| Restore and exit | Reopening the executable restored the same window and process. Explicit authenticated shutdown closed it and removed its runtime record |
| Installer | Isolated per-user installation, old-version migration, running silent refusal, normal exit, reinstallation and uninstallation passed |
| User data | Isolated installer tests retained shared settings, received files and files not installed by the application |
| Windows identity | The QA application, installer and uninstaller used matching icon resources; publisher Cinna and desktop/Start menu icon references were checked |
| Runtime delivery | The Microsoft-signed WebView2 bootstrapper's hash and signature were verified; the installer checks whether the runtime is already present |
| Current-user installation | The final installer updated the installed executable to 1.2.1. Launching it opened an authenticated independent window; the prior shared list and inbox were empty and remained empty |

All transfer and GUI fixtures use isolated synthetic data. DOM observations are read-only and contain readiness, role, layout and title information; they do not record connection credentials. Real GUI observations were inspected privately, without exporting screenshots containing pairing details.

The application payload SHA-256 is `44e05935d32bf6ed793baca2227835b5e3a3dbb146491787c9174c892e210eb8`. Packaging and release collection reject mismatched source inputs or validation reports from another payload.

Physical Android QR scanning and installation prompts, Windows 10, multiple Windows accounts and installation on a machine lacking WebView2 remain unverified. Existing-runtime behavior was tested. The distribution is unsigned. No firewall or system privacy settings were changed.
