"""Detect the installed Evergreen runtime without changing Windows settings."""
from __future__ import annotations


def valid_runtime_version(value) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split('.')
    return len(parts) == 4 and all(part.isascii() and part.isdigit() for part in parts) and any(int(part) for part in parts)


def has_webview2() -> bool:
    import winreg
    key = r'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key, access=winreg.KEY_READ | view) as handle:
                    if valid_runtime_version(winreg.QueryValueEx(handle, 'pv')[0]):
                        return True
            except OSError:
                continue
    return False
