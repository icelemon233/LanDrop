from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .desktop_window import DesktopWindow as DesktopBridge
from .platform_identity import set_app_identity


def branded_root():
    set_app_identity()
    root = tk.Tk()
    root.withdraw()
    root.title('LanDrop')
    icon = Path(__file__).parent / 'web/assets/cinna-icon.png'
    if icon.is_file():
        root.brand_icon = tk.PhotoImage(file=str(icon))
        root.iconphoto(True, root.brand_icon)
    return root


def show_error(message: str):
    root = branded_root()
    messagebox.showerror('LanDrop', message, parent=root)
    root.destroy()


def confirm_upgrade(previous: str, current: str) -> bool:
    root = branded_root()
    result = messagebox.askyesno('更新LanDrop', f'版本 {previous} 正在运行。是否退出旧版并启动 {current}？\n\n已有文件和共享目录会保留；正在进行的传输会中断。', parent=root)
    root.destroy()
    return result
