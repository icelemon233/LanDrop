<p align="center"><img src="docs/assets/icon.png" width="104" alt="Cinna" /></p>

# 隔空传

[简体中文](README.zh-CN.md)

A Cinna series application. Developed by Cinna.

Transfer files between a Windows PC and an Android phone over your local network. Open the installed app, scan its QR code, and use the phone's browser to download builds or send files back to the PC.

![Desktop app with connection details hidden](docs/assets/desktop-current.jpg)

The screenshot shows version 1.1.2 with synthetic transfer fixtures and hidden connection details.

## Install and connect

Run `隔空传-v1.1.2-安装程序.exe`, choose an installation folder, then open **隔空传** from the desktop or Start menu. Requires Windows 10/11 x64. Python and a phone app are not required. This release is unsigned.

1. Connect the phone and PC to the same local network. Ethernet on the same router also works.
2. Add files on the PC, or select a project's build output folder.
3. Scan the QR code and open the link in the phone's system browser.
4. Download a file, or choose **发送文件到电脑** to upload to the PC.

Watched folders publish APK, AAB, APKS and XAPK files recursively. They are checked about every four seconds; newly written files are briefly withheld. AAB files cannot be installed directly. Downloads and resuming are managed by the browser.

Uploads support multiple files, progress, cancellation and result checks, up to 8 GB per file. Duplicate names get a new filename. Native selection shares the original; dropping files into the webpage copies them into the app's outgoing folder. Removing a share keeps the file.

## Data and updates

Files and shared-folder settings live under `%LOCALAPPDATA%/LanDrop`. Updates and uninstallation preserve that directory. Transfer history keeps the latest 100 entries for the current run. Theme preferences are stored in the browser.

The installer asks before normally closing a running copy. Close native file pickers first. Interrupted uploads are cancelled; saved files remain. Closing the webpage leaves the service running. Choose **退出程序** to stop it. Reopening the app opens its existing interface.

Unreadable or newer settings are protected from overwriting. The app offers an explicit backup and reset. A new share is published only after settings have been saved successfully.

## Connection and access

If the phone cannot connect, check guest Wi-Fi isolation, VPN routing and Windows Firewall. Allow access on a trusted private network. Use the PC address selector for multiple adapters. When scanning with WeChat, open the link in the system browser through its menu.

Transfers use local HTTP; use a trusted home or development network. The QR code contains a temporary pairing credential. **重置连接** revokes phone sessions; a device can also be disconnected individually. PC administration requires a loopback request and an authenticated admin session. Windows protects the runtime credential with DPAPI.

## Development and verification

The app keeps its Python HTTP server, Tk dialogs and strict TypeScript frontend. See [build instructions](docs/development.md), [verification details](docs/verification.md) and [third-party notices](THIRD_PARTY_NOTICES.txt).

Version 1.1.2 was checked with backend regression tests, frontend state tests, a packaged transfer test, isolated installer tests and an actual browser at desktop and phone widths. Physical Android QR scanning and the interactive installation wizard remain unverified. The release manifest records hashes and a source digest.

The app icon follows the current Cinna application icon series. Its generated source and deterministic exports are recorded in [brand assets](docs/brand.md).
