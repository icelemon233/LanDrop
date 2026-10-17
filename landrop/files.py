from __future__ import annotations

import ctypes
import hashlib
import os
import re
from contextlib import contextmanager
from pathlib import Path

from .errors import AppError


def file_id(path: Path) -> str:
    return hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()[:24]


def safe_name(name: str) -> str:
    if not name or name in {'.', '..'} or '/' in name or '\\' in name:
        raise AppError('文件名不正确。')
    name = re.sub(r'[\x00-\x1f<>:"|?*]', '_', name).strip(' .')
    if not name:
        raise AppError('文件名不能为空。')
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', name, re.I):
        name = '_' + name
    if len(name) > 180:
        suffix = Path(name).suffix[:20]
        name = name[:180-len(suffix)] + suffix
    return name


def trusted_path(path: Path) -> Path:
    """Saved paths are canonical anchors, never newly resolved directory aliases."""
    absolute = path.absolute()
    if path.is_symlink() or path.is_junction() or path.resolve(strict=True) != absolute:
        raise AppError('共享路径已变成链接或目录联接，请重新选择要共享的文件。', 403, 'share-path-changed')
    return absolute


def opened_path(file) -> Path:
    if os.name == 'nt':
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        function = kernel.GetFinalPathNameByHandleW
        function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        function.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        count = function(msvcrt.get_osfhandle(file.fileno()), buffer, len(buffer), 0)
        if not count or count >= len(buffer):
            raise OSError(ctypes.get_last_error(), 'Could not verify opened file')
        value = buffer.value
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
        return Path(value)
    descriptor = Path(f'/proc/self/fd/{file.fileno()}')
    return descriptor.resolve(strict=True) if descriptor.exists() else Path(file.name).resolve(strict=True)


@contextmanager
def open_shared(path: Path, identity: tuple[int, int] | None = None):
    expected = trusted_path(path)
    with expected.open('rb') as source:
        if opened_path(source) != expected:
            raise AppError('文件路径在打开时发生变化，请重新添加共享。', 403, 'share-path-changed')
        info = os.fstat(source.fileno())
        if identity is not None and (info.st_size, info.st_mtime_ns) != identity:
            raise AppError('文件正在更新，请刷新列表后再下载。', 409, 'file-updating')
        yield source
