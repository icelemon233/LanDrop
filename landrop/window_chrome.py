"""Native caption and tray. No page bridge or arbitrary desktop commands."""
from __future__ import annotations

import ctypes
import logging
import json
from ctypes import wintypes
from pathlib import Path

THEMES = json.loads(Path(__file__).with_name('ui_theme.json').read_text('utf-8'))
CAPTION_HEIGHT = 40
CAPTION_BUTTON_WIDTH = 46


def theme_colors(mode):
    return THEMES['dark' if mode == 'dark' or (mode == 'auto' and system_dark()) else 'light']


def system_dark() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
    except OSError:
        return False


def caption_hit(x: int, y: int, width: int, height: int, scale: float, maximized: bool, inset: int = 0) -> int | None:
    """Signed client coordinates; Windows continues to own move/resize/snap."""
    border = max(1, round(6 * scale))
    if not maximized:
        left, right, top, bottom = x < border, x >= width - border, y < border, y >= height - border
        if top:
            return 13 if left else 14 if right else 12
        if bottom:
            return 16 if left else 17 if right else 15
        if left or right:
            return 10 if left else 11
    if 0 <= y - inset < round(CAPTION_HEIGHT * scale):
        if x - inset >= width - 2 * inset - round(3 * CAPTION_BUTTON_WIDTH * scale):
            return 1  # HTCLIENT: WinForms buttons must receive normal mouse messages.
        return 3 if x - inset < round(36 * scale) else 2
    return None


def frame_client_bounds(bounds, maximized, border_x=0, border_y=0):
    left, top, right, bottom = bounds
    if maximized:
        return left + border_x, top + border_y, right - border_x, bottom - border_y
    return bounds


class WindowChrome:
    def __init__(self, host):
        from System.Drawing import Bitmap, Font, Icon, Image, SystemColors
        from System.Windows.Forms import Button, ContextMenuStrip, DockStyle, FlatStyle, Label, NotifyIcon, Panel, PictureBox, PictureBoxSizeMode, ToolStripMenuItem, ToolStripRenderMode
        from Microsoft.Win32 import SystemEvents

        self.host, self.form = host, host.window.native
        self.tray = self.menu = None
        self.mode = 'auto'
        self._disposed = False
        self._callbacks = []
        self._hooks = []
        # GDI+ already converts point sizes using the drawing context's DPI.
        self._font = Font('Segoe UI', 10.5)
        self._foreground = SystemColors.ControlText
        self._icon = Icon(str(Path(__file__).resolve().parent.parent / 'resources/app.ico'))
        self.form.Icon = self._icon
        # Use the existing brand PNG for the visible caption; Icon.ToBitmap can
        # corrupt PNG-compressed ICO frames in the .NET Framework renderer.
        source = Image.FromFile(str(Path(__file__).with_name('web') / 'assets/cinna-icon.png'))
        try:
            self._bitmap = Bitmap(source)
        finally:
            source.Dispose()
        self.caption = Panel()
        self.caption.Dock = DockStyle.Top
        self.picture = PictureBox()
        self.picture.Image = self._bitmap
        self.picture.SizeMode = PictureBoxSizeMode.Zoom
        self.label = Label()
        self.label.Text = 'LanDrop'
        self.label.Font = self._font
        self.label.AutoSize = False
        self.label.AutoEllipsis = True
        from System.Drawing import ContentAlignment
        self.label.TextAlign = ContentAlignment.MiddleLeft
        self.buttons = []
        for name, command, callback in (
            ('最小化', 'minimize', lambda *_: self._minimize()),
            ('最大化', 'maximize', lambda *_: self._maximize()),
            ('关闭窗口', 'close', lambda *_: self.form.Close()),
        ):
            button = Button()
            button.AccessibleName = name
            button.Text = ''
            button.FlatStyle = FlatStyle.Flat
            button.FlatAppearance.BorderSize = 0
            button.TabStop = False
            button.Click += callback
            button.Paint += lambda sender, args, kind=command: self._paint_button(sender, args, kind)
            self.caption.Controls.Add(button)
            self.buttons.append(button)
        self.caption.Controls.Add(self.picture)
        self.caption.Controls.Add(self.label)
        self.form.Controls.Add(self.caption)
        self.caption.SendToBack()
        self._install_frame()
        self.form.Resize += self._layout
        self.form.DpiChanged += self._layout
        self.form.Shown += self._layout
        self._system_event = self._system_changed
        SystemEvents.UserPreferenceChanged += self._system_event
        self.form.update_title_bar_theme = self._system_event
        self._layout()
        self.set_theme(host.state.config.get('preferences', {}).get('windowTheme', 'auto'))
        try:
            if not self.user32.FindWindowW('Shell_TrayWnd', None):
                raise OSError('Windows notification area unavailable')
            self.menu = ContextMenuStrip()
            self.menu.ShowImageMargin = False
            self.menu.RenderMode = ToolStripRenderMode.System
            opened = ToolStripMenuItem('打开应用')
            opened.Click += lambda *_: host._activate()
            quit_item = ToolStripMenuItem('退出应用')
            quit_item.Click += lambda *_: host._request_exit()
            self.menu.Items.Add(opened)
            self.menu.Items.Add(quit_item)
            self.tray = NotifyIcon()
            self.tray.Icon = self._icon
            self.tray.Text = 'LanDrop'
            self.tray.ContextMenuStrip = self.menu
            self.tray.DoubleClick += lambda *_: host._activate()
            self.tray.Visible = True
            self.set_theme(self.mode)
        except Exception:
            logging.exception('Tray unavailable; keeping a recoverable taskbar window')
            if self.tray:
                self.tray.Dispose()
            self.tray = None

    @property
    def available(self):
        return bool(not self._disposed and self.tray and self.tray.Visible and self.user32.FindWindowW('Shell_TrayWnd', None))

    def _layout(self, *_):
        from System.Drawing import Point, Size
        from System.Windows.Forms import FormWindowState
        if self.form.WindowState != FormWindowState.Minimized:
            self.last_window_state = self.form.WindowState
        scale = self.user32.GetDpiForWindow(self.hwnd) / 96 or 1
        self.scale = scale
        self.caption.Height = round(CAPTION_HEIGHT * scale)
        self.picture.Location = Point(round(12 * scale), round(10 * scale))
        self.picture.Size = Size(round(20 * scale), round(20 * scale))
        self.label.Location = Point(round(40 * scale), 0)
        self.label.Size = Size(max(0, self.form.ClientSize.Width - round(190 * scale)), self.caption.Height)
        for index, button in enumerate(self.buttons):
            left = self.form.ClientSize.Width - round((3 - index) * CAPTION_BUTTON_WIDTH * scale)
            right = self.form.ClientSize.Width - round((2 - index) * CAPTION_BUTTON_WIDTH * scale)
            button.Location = Point(left, 0)
            button.Size = Size(right - left, self.caption.Height)
            button.Invalidate()
        maximized = self.user32.IsZoomed(self.hwnd)
        self.buttons[1].AccessibleName = '还原' if maximized else '最大化'

    def _minimize(self):
        from System.Windows.Forms import FormWindowState
        self.form.WindowState = FormWindowState.Minimized

    def _maximize(self):
        from System.Windows.Forms import FormWindowState
        self.form.WindowState = FormWindowState.Normal if self.form.WindowState == FormWindowState.Maximized else FormWindowState.Maximized

    def _paint_button(self, button, args, command):
        from System.Drawing import GraphicsUnit, Pen
        from System.Drawing.Drawing2D import PixelOffsetMode, SmoothingMode
        from System.Windows.Forms import FormWindowState
        scale = getattr(self, 'scale', 1)
        size = 10 * scale
        left, top = (button.ClientSize.Width - size) / 2, (button.ClientSize.Height - size) / 2
        graphics = args.Graphics
        saved = graphics.Save()
        graphics.PageUnit = GraphicsUnit.Pixel
        graphics.PixelOffsetMode = PixelOffsetMode.Half
        graphics.SmoothingMode = SmoothingMode.AntiAlias
        pen = Pen(self._foreground, max(1., scale))
        try:
            if command == 'minimize':
                graphics.DrawLine(pen, float(left), float(top + size / 2), float(left + size), float(top + size / 2))
            elif command == 'close':
                graphics.DrawLine(pen, float(left), float(top), float(left + size), float(top + size))
                graphics.DrawLine(pen, float(left + size), float(top), float(left), float(top + size))
            elif self.form.WindowState == FormWindowState.Maximized:
                offset, side = 2 * scale, 8 * scale
                graphics.DrawLine(pen, float(left + offset), float(top + offset), float(left + offset), float(top))
                graphics.DrawLine(pen, float(left + offset), float(top), float(left + size), float(top))
                graphics.DrawLine(pen, float(left + size), float(top), float(left + size), float(top + side))
                graphics.DrawLine(pen, float(left + size), float(top + side), float(left + side), float(top + side))
                graphics.DrawRectangle(pen, float(left), float(top + offset), float(side), float(side))
            else:
                graphics.DrawRectangle(pen, float(left), float(top), float(size), float(size))
        finally:
            pen.Dispose()
            graphics.Restore(saved)

    def render_caption(self, path):
        """Render only our caption controls for isolated QA, without desktop capture."""
        from System.Drawing import Bitmap, Rectangle
        from System.Drawing.Imaging import ImageFormat
        bitmap = Bitmap(self.caption.Width, self.caption.Height)
        bitmap.SetResolution(float(96 * self.scale), float(96 * self.scale))
        try:
            self.caption.DrawToBitmap(bitmap, Rectangle(0, 0, bitmap.Width, bitmap.Height))
            bitmap.Save(str(path), ImageFormat.Png)
        finally:
            bitmap.Dispose()

    def client_top_inset(self):
        bounds, origin = wintypes.RECT(), wintypes.POINT()
        self.user32.GetWindowRect(self.hwnd, ctypes.byref(bounds))
        self.user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        return origin.y - bounds.top

    def _install_frame(self):
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.comctl = ctypes.WinDLL('comctl32', use_last_error=True)
        self.hwnd = int(self.form.Handle.ToInt64())
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t, ctypes.c_size_t, ctypes.c_size_t)
        self.comctl.SetWindowSubclass.argtypes = [wintypes.HWND, callback_type, ctypes.c_size_t, ctypes.c_size_t]
        self.comctl.SetWindowSubclass.restype = wintypes.BOOL
        self.comctl.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        self.comctl.DefSubclassProc.restype = ctypes.c_ssize_t
        self.comctl.RemoveWindowSubclass.argtypes = [wintypes.HWND, callback_type, ctypes.c_size_t]
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.IsZoomed.argtypes = [wintypes.HWND]
        self.user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.user32.GetDpiForWindow.restype = wintypes.UINT
        self.user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
        self.user32.GetSystemMetricsForDpi.restype = ctypes.c_int
        self.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        self.user32.FindWindowW.restype = wintypes.HWND
        self.user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]

        def frame(hwnd, message, wparam, lparam, *_):
            try:
                if message == 0x83 and wparam:  # WM_NCCALCSIZE: no leftover native caption strip.
                    rect = ctypes.cast(lparam, ctypes.POINTER(wintypes.RECT)).contents
                    dpi = self.user32.GetDpiForWindow(hwnd) or 96
                    padding = self.user32.GetSystemMetricsForDpi(92, dpi)
                    bounds = frame_client_bounds((rect.left, rect.top, rect.right, rect.bottom), bool(self.user32.IsZoomed(hwnd)),
                        self.user32.GetSystemMetricsForDpi(32, dpi) + padding, self.user32.GetSystemMetricsForDpi(33, dpi) + padding)
                    rect.left, rect.top, rect.right, rect.bottom = bounds
                    return 0
                if message == 0x84:  # WM_NCHITTEST, signed screen coordinates (negative monitors included).
                    rect = wintypes.RECT()
                    self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    x = ctypes.c_short(lparam & 0xFFFF).value - rect.left
                    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value - rect.top
                    origin = wintypes.POINT()
                    self.user32.ClientToScreen(hwnd, ctypes.byref(origin))
                    result = caption_hit(x, y, rect.right - rect.left, rect.bottom - rect.top, self.user32.GetDpiForWindow(hwnd) / 96 or 1, bool(self.user32.IsZoomed(hwnd)), origin.y - rect.top)
                    if result is not None:
                        return result
            except Exception:
                logging.exception('Native frame handling failed')
            return self.comctl.DefSubclassProc(hwnd, message, wparam, lparam)

        def transparent(hwnd, message, wparam, lparam, *_):
            if message == 0x84:
                from System.Drawing import Point
                point = self.caption.PointToClient(Point(ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value))
                # A transparent parent must not make its interactive children
                # disappear from Windows pointer hit testing.
                return 1 if any(button.Bounds.Contains(point) for button in self.buttons) else -1
            return self.comctl.DefSubclassProc(hwnd, message, wparam, lparam)

        for control, handler in ((self.form, frame), (self.caption, transparent), (self.picture, transparent), (self.label, transparent)):
            callback = callback_type(handler)
            hwnd = int(control.Handle.ToInt64())
            if not self.comctl.SetWindowSubclass(hwnd, callback, 1, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            self._callbacks.append(callback)
            self._hooks.append((hwnd, callback))
        self.user32.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, 0x37)  # SWP_FRAMECHANGED, preserve bounds/z-order.

    def _system_changed(self, *_):
        if not self._disposed:
            self.host._on_ui(lambda: self.set_theme(self.mode))

    def set_theme(self, mode):
        from System.Drawing import ColorTranslator, SystemColors
        from System.Windows.Forms import SystemInformation
        self.mode = mode
        colors = theme_colors(mode)
        dark = ctypes.c_int(colors is THEMES['dark'])
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute(self.hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        background = ColorTranslator.FromHtml(colors['sidebar'])
        foreground = ColorTranslator.FromHtml(colors['ink'])
        hover = ColorTranslator.FromHtml(colors['soft'])
        if SystemInformation.HighContrast:
            background, foreground, hover = SystemColors.Window, SystemColors.WindowText, SystemColors.Highlight
        self._foreground = foreground
        self.form.BackColor = self.caption.BackColor = background
        self.label.ForeColor = foreground
        for index, button in enumerate(self.buttons):
            button.BackColor, button.ForeColor = background, foreground
            button.FlatAppearance.MouseOverBackColor = ColorTranslator.FromHtml(colors['danger-bg']) if index == 2 else hover
            button.FlatAppearance.MouseDownBackColor = hover
            button.Invalidate()
        if self.menu:
            self.menu.Font = self._font
            self.menu.BackColor, self.menu.ForeColor = background, foreground
            for item in self.menu.Items:
                item.BackColor, item.ForeColor = background, foreground

    def hide(self):
        if not self.available:
            return False
        if not self.host.state.config.get('preferences', {}).get('trayNoticeSeen'):
            from System.Windows.Forms import ToolTipIcon
            self.tray.ShowBalloonTip(5000, 'LanDrop 仍在运行', '连接和传输继续。双击托盘图标打开，右键菜单可退出。', ToolTipIcon.Info)
            try:
                self.host.state.set_window_preference('trayNoticeSeen', True)
            except Exception:
                logging.exception('Could not save the tray notice preference')
        self.form.Hide()
        return True

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        from Microsoft.Win32 import SystemEvents
        SystemEvents.UserPreferenceChanged -= self._system_event
        for hwnd, callback in self._hooks:
            self.comctl.RemoveWindowSubclass(hwnd, callback, 1)
        if self.tray:
            self.tray.Visible = False
            self.tray.Dispose()
        if self.menu:
            self.menu.Dispose()
        self._bitmap.Dispose()
        self._icon.Dispose()
        self._font.Dispose()
