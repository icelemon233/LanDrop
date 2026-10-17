from __future__ import annotations

import concurrent.futures
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .state import AppError


def branded_root():
    if os.name == 'nt':
        import ctypes
        identity = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        identity.argtypes = [ctypes.c_wchar_p]
        identity.restype = ctypes.c_long
        identity('Cinna.LanDrop')
    root = tk.Tk()
    root.withdraw()
    root.title('LanDrop')
    icon = Path(__file__).parent / 'web/assets/cinna-icon.png'
    if icon.is_file():
        root.brand_icon = tk.PhotoImage(file=str(icon))
        root.iconphoto(True, root.brand_icon)
    return root


class DesktopBridge:
    def __init__(self, inbox: Path):
        self.root = branded_root()
        self.inbox = inbox
        self.tasks: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.dialog_busy = False
        self.closed = False
        self.root.after(80, self.pump)

    def call(self, action: str):
        future: concurrent.futures.Future = concurrent.futures.Future()
        with self.lock:
            if self.closed:
                raise AppError('电脑端已退出，请重新打开程序。', 503, 'desktop-closed')
            if action in {'files', 'folder'}:
                if self.dialog_busy:
                    raise AppError('请先完成当前的文件选择。', 409, 'desktop-busy')
                self.dialog_busy = True
        self.tasks.put((action, future))
        try:
            return future.result(timeout=600)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise AppError('文件选择等待超时，请关闭系统选择窗口后重试。', 408, 'desktop-timeout')
        finally:
            if action in {'files', 'folder'} and future.done():
                with self.lock:
                    self.dialog_busy = False

    def ensure_can_shutdown(self):
        with self.lock:
            if self.dialog_busy:
                raise AppError('请先关闭系统文件选择窗口，再退出LanDrop。', 409, 'desktop-busy')

    def report_error(self, message: str):
        messagebox.showerror('LanDrop', message, parent=self.root)

    def pump(self):
        if self.closed:
            return
        self.root.after(80, self.pump)
        try:
            action, future = self.tasks.get_nowait()
        except queue.Empty:
            return
        if not future.set_running_or_notify_cancel():
            return
        try:
            self.root.attributes('-topmost', True)
            if action == 'files':
                result = list(filedialog.askopenfilenames(parent=self.root, title='添加要发送到手机的文件', filetypes=[('所有文件', '*.*'), ('安卓安装包', '*.apk *.aab *.apks *.xapk')]))
            elif action == 'folder':
                result = filedialog.askdirectory(parent=self.root, title='选择项目的安装包输出文件夹')
            elif action == 'open-inbox':
                os.startfile(str(self.inbox))
                result = True
            elif action == 'shutdown':
                result = True
                self.root.after(250, self.root.quit)
            else:
                raise AppError('未知的桌面操作。')
            future.set_result(result)
        except Exception as error:
            future.set_exception(error)
        finally:
            self.root.attributes('-topmost', False)
            if action in {'files', 'folder'}:
                with self.lock:
                    self.dialog_busy = False

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        while not self.tasks.empty():
            _, future = self.tasks.get_nowait()
            if not future.done():
                future.set_exception(AppError('电脑端已退出。', 503, 'desktop-closed'))
        self.root.destroy()


def show_error(message: str):
    root = branded_root()
    messagebox.showerror('LanDrop', message, parent=root)
    root.destroy()


def confirm_upgrade(previous: str, current: str) -> bool:
    root = branded_root()
    result = messagebox.askyesno('更新LanDrop', f'版本 {previous} 正在运行。是否退出旧版并启动 {current}？\n\n已有文件和共享目录会保留；正在进行的传输会中断。', parent=root)
    root.destroy()
    return result
