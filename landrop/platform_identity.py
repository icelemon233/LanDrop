"""Stable Windows identity shared by startup dialogs and the main window."""
import os


def set_app_identity(test_mode=False):
    if os.name == 'nt':
        import ctypes
        identity = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        identity.argtypes = [ctypes.c_wchar_p]
        identity.restype = ctypes.c_long
        identity('Cinna.LanDrop.QA' if test_mode else 'Cinna.LanDrop')
