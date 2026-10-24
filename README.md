<p align="center"><img src="docs/assets/icon.png" width="128" alt="LanDrop icon" /></p>

# LanDrop

English | [简体中文](README.zh-CN.md)

A Windows desktop app for transferring files to and from an Android phone over your local network. The PC has its own application window; scan its QR code to connect through your phone's browser.

[Download for Windows](https://github.com/icelemon233/LanDrop/releases/latest)

## Connect

Requires Windows 10/11 x64. Python and a phone app are not required. The installer sets up WebView2 if it is missing; that step needs an internet connection.

1. Run the installer and open **LanDrop** from the desktop or Start menu.
2. Connect the PC and phone to the same local network.
3. Add files on the PC, then scan the QR code with your phone.
4. Download a file, or choose **发送文件到电脑** to upload to the PC.

## Files

- Share files or watch a build folder for APK, AAB, APKS and XAPK files, including subfolders. AAB files cannot be installed directly.
- Upload multiple files with progress and cancellation, up to 8 GB per file. Duplicate names get a new filename.
- Select original files to share them, or drop files into the window to copy them into the outgoing folder. Removing a share keeps the original file.

## Data and updates

Updates and uninstallation preserve received files and shared-folder settings. Transfer history keeps the latest 100 entries for the current run; theme preferences stay on the current device.

Minimizing keeps LanDrop in the taskbar. Closing the window sends it to the tray and keeps transfers running; Settings can change this to exit. The tray menu can reopen or exit the app. If the tray is unavailable, the window stays in the taskbar. Choose **退出应用** to stop the app and unfinished transfers. Opening LanDrop again restores the existing window. Before upgrading, close file pickers and let the installer request a normal exit.

## Connection

Transfers use local HTTP. Use a trusted network. The QR code contains a temporary pairing credential; **重置连接** revokes connected phone sessions.

If the phone cannot connect, check guest Wi-Fi isolation, VPN routing and Windows Firewall. With multiple adapters, select the PC address below the QR code. When scanning with WeChat, open the link in the system browser.

See [the user guide](docs/使用说明.txt), [build instructions](docs/development.md) and [third-party notices](THIRD_PARTY_NOTICES.txt). Windows releases are currently unsigned.

Developer: Cinna.
