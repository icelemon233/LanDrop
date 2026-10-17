from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .errors import AppError


def _dpapi(value: bytes, decrypt: bool) -> bytes:
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(value)
    incoming = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    function = api.CryptUnprotectData if decrypt else api.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise OSError(ctypes.get_last_error(), 'Windows credential protection failed')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def protect_secret(value: str) -> str:
    raw = value.encode('utf-8')
    if os.name == 'nt':
        return 'dpapi:' + base64.b64encode(_dpapi(raw, False)).decode('ascii')
    return 'private-file:' + base64.b64encode(raw).decode('ascii')


def unprotect_secret(value: str) -> str:
    prefix, encoded = value.split(':', 1)
    raw = base64.b64decode(encoded, validate=True)
    if prefix == 'dpapi' and os.name == 'nt':
        raw = _dpapi(raw, True)
    elif prefix != 'private-file' or os.name == 'nt':
        raise ValueError('unsupported credential format')
    return raw.decode('utf-8')


@dataclass(frozen=True)
class RuntimeInfo:
    port: int
    secret: str = field(repr=False)
    pid: int = 0
    version: str = ''


class RuntimeStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> RuntimeInfo | None:
        try:
            if self.path.stat().st_size > 16384:
                raise ValueError('runtime file too large')
            value = json.loads(self.path.read_text('utf-8'))
            if not isinstance(value, dict) or type(value.get('port')) is not int or not 1 <= value['port'] <= 65535:
                raise ValueError('invalid runtime port')
            if value.get('schema') == 2:
                secret = unprotect_secret(value['protectedSecret'])
            else:
                secret = value.get('admin')  # Read legacy runtime only for an orderly upgrade.
            if not isinstance(secret, str) or not 24 <= len(secret) <= 128:
                raise ValueError('invalid runtime credential')
            pid = value.get('pid', 0)
            if type(pid) is not int or pid < 0:
                raise ValueError('invalid runtime process')
            version = value.get('appVersion', '')
            if not isinstance(version, str):
                raise ValueError('invalid runtime version')
            return RuntimeInfo(value['port'], secret, pid, version)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise AppError('电脑端运行信息无法恢复，请先退出正在运行的隔空传后重试。', 409, 'runtime-unreadable') from error

    def write(self, port: int, secret: str):
        payload = {'schema': 2, 'port': port, 'pid': os.getpid(), 'appVersion': __version__, 'protectedSecret': protect_secret(secret)}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.runtime-', suffix='.tmp', dir=self.path.parent, delete=False) as file:
                temporary = Path(file.name)
                file.write(json.dumps(payload).encode('utf-8'))
                file.flush()
                os.fsync(file.fileno())
            if os.name != 'nt':
                os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def remove_owned(self):
        info = self.read()
        if info and info.pid == os.getpid():
            self.path.unlink(missing_ok=True)


class InstanceGuard:
    def __init__(self, directory: Path):
        self.stream = (directory / '.instance-lock').open('a+b')
        if self.stream.tell() == 0:
            self.stream.write(b'0')
            self.stream.flush()
        self.acquired = False

    def acquire(self) -> bool:
        if self.acquired:
            return True
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
            return True
        except OSError:
            return False

    def close(self):
        self.stream.close()
