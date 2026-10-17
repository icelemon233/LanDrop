"""Wait for a known Windows app and its one-file bootloader; never terminate it."""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from pathlib import Path

from .errors import AppError


class ProcessWaiter:
    def __init__(self, pid: int):
        self.handles: list[int] = []
        if os.name != 'nt' or pid <= 0:
            return
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        handle = self.api.OpenProcess(0x101000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:  # Process already exited.
                return
            raise AppError('无法确认旧程序是否退出，请先手动退出隔空传。', 409, 'process-unavailable')
        self.handles.append(handle)
        image = self.image(handle)
        parent = self.parent(pid)
        if parent and image:
            parent_handle = self.api.OpenProcess(0x101000, False, parent)
            if parent_handle:
                if self.image(parent_handle) == image:
                    self.handles.append(parent_handle)
                else:
                    self.api.CloseHandle(parent_handle)

    def image(self, handle) -> str:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if self.api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.normcase(buffer.value)
        return ''

    def parent(self, pid: int) -> int:
        class Entry(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                        ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                        ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                        ('exe', wintypes.WCHAR * 260)]
        self.api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.api.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        self.api.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        snapshot = self.api.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return 0
        try:
            entry = Entry()
            entry.size = ctypes.sizeof(entry)
            more = self.api.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                if entry.pid == pid:
                    return entry.parent
                more = self.api.Process32NextW(snapshot, ctypes.byref(entry))
            return 0
        finally:
            self.api.CloseHandle(snapshot)

    def wait(self, timeout: float = 15):
        deadline = time.monotonic() + timeout
        for handle in self.handles:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if self.api.WaitForSingleObject(handle, remaining) != 0:
                raise AppError('旧程序尚未完全退出，请稍后重试安装。', 409, 'process-pending')

    def close(self):
        for handle in self.handles:
            self.api.CloseHandle(handle)
        self.handles.clear()
