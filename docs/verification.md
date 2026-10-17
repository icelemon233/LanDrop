# Version 1.1.2 verification

64 backend tests and 8 frontend tests passed. Transfer fixtures use isolated synthetic data.

| Area | Result |
| --- | --- |
| Cinna membership | project.json records LanDrop, the Cinna series and developer Cinna |
| Exports | One generated source drives the app, ICO, favicon, native window, installer artwork and README outputs; file hashes match the export manifest |
| Actual binary resources | App, installer and uninstaller icon resources match; Cinna publisher and developer fields verified |
| Shortcuts | Desktop and Start menu targets, arguments and explicit app.ico references verified |
| Installer | Per-user install, migration, running silent refusal, reinstall, uninstall and data preservation passed |
| Executable | Native Tk startup, repeated launch, restart, LAN upload/download of 5 MB files with matching hashes passed |
| Upgrade | Old native and headless copies upgrade to a new native copy; independent instances use separate ports |
| Exit race | Known Windows process handles confirm completion without racing deletion of runtime.json |

The icon was inspected at 16, 24, 32, 48, 64 and 128 pixels on light and dark backgrounds. README corners use real alpha. Layout screenshots use synthetic files and hidden pairing details.

The installed current-user copy was updated to 1.1.2. Its executable and icon hashes, Cinna publisher, app version and actual desktop/Start menu icon paths were checked. The installed browser page displayed the new artwork. Existing user files and shared settings were compared before and after the update and preserved.

Desktop and 390px phone pages loaded the new interface image and favicon references; neither had horizontal overflow. The installed empty-list screenshot has connection details hidden.

The installer wizard's visual inspection was interrupted by a Windows Firewall permission dialog. No action was taken on that system security prompt. Wizard sidebar/header appearance and individual native-dialog appearance are recorded as pending visual checks; resource equality and silent install/upgrade/uninstall checks passed. Source and artifacts were checkpointed for the coordinated project migration, with those visual checks to resume afterward.

Not verified: physical Android QR scanning, Android installation prompts, Windows 10 or multiple Windows accounts. Local validation uses Windows 11 x64. The distribution is unsigned. No firewall permission is granted automatically; system security prompts require the user to act.
