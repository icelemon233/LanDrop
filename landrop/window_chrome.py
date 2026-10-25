"""Native caption and tray. No page bridge or arbitrary desktop commands."""
from __future__ import annotations

import ctypes
import logging
import json
from ctypes import wintypes
from pathlib import Path

THEMES = json.loads(Path(__file__).with_name('ui_theme.json').read_text('utf-8'))
SHELL = json.loads(Path(__file__).with_name('window_shell.json').read_text('utf-8'))
CAPTION = SHELL['titlebar']
CAPTION_HEIGHT = CAPTION['height']
CAPTION_BUTTON_WIDTH = CAPTION['captionButtonWidth']


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
        client_x, client_width = x - inset, width - 2 * inset
        if client_width - round(2 * CAPTION_BUTTON_WIDTH * scale) <= client_x < client_width - round(CAPTION_BUTTON_WIDTH * scale):
            return 9  # HTMAXBUTTON: Windows 11 owns Snap Layout hover and the NC click loop.
        if client_x >= client_width - round(3 * CAPTION_BUTTON_WIDTH * scale):
            return 1  # HTCLIENT: WinForms buttons must receive normal mouse messages.
        return 3 if x - inset < round((CAPTION['iconLeftInset'] + CAPTION['iconSize']) * scale) else 2
    return None


def frame_client_bounds(bounds, maximized, border_x=0, border_y=0):
    left, top, right, bottom = bounds
    if maximized:
        return left + border_x, top + border_y, right - border_x, bottom - border_y
    return bounds


class WindowChrome:
    def __init__(self, host):
        from System.Drawing import Bitmap, Font, FontStyle, Icon, Image, SystemColors
        from System.Windows.Forms import Button, ContextMenuStrip, DockStyle, FlatStyle, Label, NotifyIcon, Panel, PictureBox, PictureBoxSizeMode, ToolStripMenuItem, ToolStripRenderMode
        from Microsoft.Win32 import SystemEvents

        self.host, self.form = host, host.window.native
        self.tray = self.menu = None
        self.mode = 'auto'
        self._disposed = False
        self._callbacks = []
        self._hooks = []
        self._max_hover = False
        # GDI+ already converts point sizes using the drawing context's DPI.
        self._font = Font('Segoe UI Variable Text', CAPTION['nameFontSize'] * 72 / 96, FontStyle.Regular)
        if self._font.Name != 'Segoe UI Variable Text':
            self._font.Dispose()
            self._font = Font('Segoe UI', CAPTION['nameFontSize'] * 72 / 96, FontStyle.Regular)
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
        self._install_resize_targets()
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
            self.tray.Text = 'LanDrop · UI QA' if host.state.test_mode else 'LanDrop'
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
        self.picture.Location = Point(round(CAPTION['iconLeftInset'] * scale), round((CAPTION_HEIGHT - CAPTION['iconSize']) / 2 * scale))
        self.picture.Size = Size(round(CAPTION['iconSize'] * scale), round(CAPTION['iconSize'] * scale))
        name_left = round((CAPTION['iconLeftInset'] + CAPTION['iconSize'] + CAPTION['iconNameGap']) * scale)
        self.label.Location = Point(name_left, 0)
        self.label.Size = Size(max(0, self.form.ClientSize.Width - round(3 * CAPTION_BUTTON_WIDTH * scale) - name_left), self.caption.Height)
        for index, button in enumerate(self.buttons):
            left = self.form.ClientSize.Width - round((3 - index) * CAPTION_BUTTON_WIDTH * scale)
            right = self.form.ClientSize.Width - round((2 - index) * CAPTION_BUTTON_WIDTH * scale)
            button.Location = Point(left, 0)
            button.Size = Size(right - left, self.caption.Height)
            button.Invalidate()
        maximized = self.user32.IsZoomed(self.hwnd)
        self.buttons[1].AccessibleName = '还原' if maximized else '最大化'
        self._layout_resize_targets(bool(maximized))
        # DWM owns the real outer frame and its normal/maximized corner policy.
        corner = ctypes.c_int(1 if maximized else 2)  # DWMWCP_DONOTROUND / ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(self.hwnd), 33, ctypes.byref(corner), ctypes.sizeof(corner))

    def _minimize(self):
        from System.Windows.Forms import FormWindowState
        self.form.WindowState = FormWindowState.Minimized

    def _maximize(self):
        from System.Windows.Forms import FormWindowState
        self.form.WindowState = FormWindowState.Normal if self.form.WindowState == FormWindowState.Maximized else FormWindowState.Maximized

    def _paint_button(self, button, args, command):
        from System.Drawing import GraphicsUnit, Pen
        from System.Drawing.Drawing2D import PixelOffsetMode, SmoothingMode
        from System.Windows.Forms import Cursor, FormWindowState
        scale = getattr(self, 'scale', 1)
        size = CAPTION['captionGlyphSize'] * scale
        left, top = (button.ClientSize.Width - size) / 2, (button.ClientSize.Height - size) / 2
        stroke = max(1., CAPTION['captionGlyphStroke'] * scale)
        inset = stroke / 2
        graphics = args.Graphics
        saved = graphics.Save()
        graphics.PageUnit = GraphicsUnit.Pixel
        graphics.PixelOffsetMode = PixelOffsetMode.Half
        graphics.SmoothingMode = SmoothingMode.AntiAlias
        from System.Drawing import ColorTranslator
        close_active = command == 'close' and button.ClientRectangle.Contains(button.PointToClient(Cursor.Position))
        foreground = ColorTranslator.FromHtml(THEMES['light']['caption-close-ink']) if close_active else self._foreground
        pen = Pen(foreground, stroke)
        try:
            if command == 'minimize':
                graphics.DrawLine(pen, float(left), float(top + size / 2), float(left + size), float(top + size / 2))
            elif command == 'close':
                graphics.DrawLine(pen, float(left + inset), float(top + inset), float(left + size - inset), float(top + size - inset))
                graphics.DrawLine(pen, float(left + size - inset), float(top + inset), float(left + inset), float(top + size - inset))
            elif self.form.WindowState == FormWindowState.Maximized:
                left, top = left + inset, top + inset
                offset, side = 2 * scale, 8 * scale - stroke
                graphics.DrawLine(pen, float(left + offset), float(top + offset), float(left + offset), float(top))
                graphics.DrawLine(pen, float(left + offset), float(top), float(left + size - stroke), float(top))
                graphics.DrawLine(pen, float(left + size - stroke), float(top), float(left + size - stroke), float(top + side))
                graphics.DrawLine(pen, float(left + size - stroke), float(top + side), float(left + side), float(top + side))
                graphics.DrawRectangle(pen, float(left), float(top + offset), float(side), float(side))
            else:
                graphics.DrawRectangle(pen, float(left + inset), float(top + inset), float(size - stroke), float(size - stroke))
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
        self.user32.TrackMouseEvent.argtypes = [ctypes.c_void_p]

        class TrackMouse(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('dwFlags', wintypes.DWORD), ('hwndTrack', wintypes.HWND), ('dwHoverTime', wintypes.DWORD)]

        def frame(hwnd, message, wparam, lparam, *_):
            try:
                if message == 0xA0:  # WM_NCMOUSEMOVE. Child max button steps aside below.
                    hovered = wparam == 9
                    if hovered != self._max_hover:
                        self._max_hover = hovered
                        self.buttons[1].BackColor = self.buttons[1].FlatAppearance.MouseOverBackColor if hovered else self.caption.BackColor
                    tracking = TrackMouse(ctypes.sizeof(TrackMouse), 0x12, hwnd, 0)  # TME_NONCLIENT | TME_LEAVE
                    self.user32.TrackMouseEvent(ctypes.byref(tracking))
                    # Continue to DefWindowProc: it starts the system Snap hover,
                    # press/release and SC_MAXIMIZE/SC_RESTORE behavior.
                elif message == 0x2A2:  # WM_NCMOUSELEAVE
                    self._max_hover = False
                    self.buttons[1].BackColor = self.caption.BackColor
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
                if self.buttons[1].Bounds.Contains(point):
                    return -1  # Both the button and its parent yield to the owning form's HTMAXBUTTON.
                return 1 if any(button.Bounds.Contains(point) for button in self.buttons) else -1
            return self.comctl.DefSubclassProc(hwnd, message, wparam, lparam)

        for control, handler in ((self.form, frame), (self.caption, transparent), (self.picture, transparent), (self.label, transparent), (self.buttons[1], transparent)):
            callback = callback_type(handler)
            hwnd = int(control.Handle.ToInt64())
            if not self.comctl.SetWindowSubclass(hwnd, callback, 1, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            self._callbacks.append(callback)
            self._hooks.append((hwnd, callback))
        self.user32.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, 0x37)  # SWP_FRAMECHANGED, preserve bounds/z-order.

    def _install_resize_targets(self):
        """Keep native resize input above WebView2's out-of-process child HWNDs.

        A layered child with alpha=1 remains a hit target without replacing the
        web content at the border. No CSS gutter or synthetic window resizing is
        involved; DefWindowProc on the owning form runs Windows' sizing loop.
        """
        from System.Drawing import Color
        from System.Windows.Forms import Panel
        self._resize_targets = []
        self.user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self.user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
        self.user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
        self.user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        self.user32.SendMessageW.restype = ctypes.c_ssize_t
        self.user32.ReleaseCapture.argtypes = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t, ctypes.c_size_t, ctypes.c_size_t)

        def resize_target(hwnd, message, wparam, lparam, *_):
            if message == 0x84:  # Let the same signed root coordinates decide every edge/corner.
                return self.user32.SendMessageW(self.hwnd, message, wparam, lparam)
            if message in (0xA1, 0xA3):  # WM_NCLBUTTONDOWN / WM_NCLBUTTONDBLCLK
                self.user32.ReleaseCapture()
                return self.user32.SendMessageW(self.hwnd, message, wparam, lparam)
            return self.comctl.DefSubclassProc(hwnd, message, wparam, lparam)

        for name in ('top', 'right', 'bottom', 'left'):
            target = Panel()
            target.Name = 'LanDropNativeResize_' + name
            target.TabStop = False
            target.BackColor = Color.Black
            self.form.Controls.Add(target)
            hwnd = int(target.Handle.ToInt64())
            style = self.user32.GetWindowLongPtrW(hwnd, -20)
            self.user32.SetWindowLongPtrW(hwnd, -20, style | 0x80000)  # WS_EX_LAYERED, without WS_EX_TRANSPARENT.
            if not self.user32.SetLayeredWindowAttributes(hwnd, 0, 1, 2):
                raise ctypes.WinError(ctypes.get_last_error())
            callback = callback_type(resize_target)
            if not self.comctl.SetWindowSubclass(hwnd, callback, 1, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            self._callbacks.append(callback)
            self._hooks.append((hwnd, callback))
            self._resize_targets.append(target)

    def _layout_resize_targets(self, maximized):
        from System.Drawing import Rectangle
        border = max(1, round(6 * self.scale))
        width, height = self.form.ClientSize.Width, self.form.ClientSize.Height
        bounds = ((0, 0, width, border), (width - border, 0, border, height),
                  (0, height - border, width, border), (0, 0, border, height))
        for target, rect in zip(self._resize_targets, bounds):
            target.Visible = not maximized
            target.Bounds = Rectangle(*rect)
            target.BringToFront()

    def layout_observation(self):
        def bounds(control):
            rect = control.Bounds
            return {'x': rect.X, 'y': rect.Y, 'width': rect.Width, 'height': rect.Height}
        return {'hwnd': self.hwnd, 'title': self.form.Text, 'caption': bounds(self.caption),
                'icon': bounds(self.picture), 'name': bounds(self.label),
                'buttons': [bounds(button) for button in self.buttons],
                'resizeTargets': [{'name': target.Name, **bounds(target), 'visible': target.Visible,
                                   'enabledInNormalWindow': not bool(self.user32.IsZoomed(self.hwnd))} for target in self._resize_targets]}

    def frame_geometry(self):
        """Physical screen coordinates, including DWM's visible frame boundary."""
        from System.Drawing import Point
        window, visible, origin = wintypes.RECT(), wintypes.RECT(), wintypes.POINT()
        self.user32.GetWindowRect(self.hwnd, ctypes.byref(window))
        self.user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmGetWindowAttribute.restype = ctypes.c_long
        result = dwm.DwmGetWindowAttribute(self.hwnd, 9, ctypes.byref(visible), ctypes.sizeof(visible))
        def rect(value):
            return {'left': value.left, 'top': value.top, 'right': value.right, 'bottom': value.bottom,
                    'width': value.right - value.left, 'height': value.bottom - value.top}
        webview = getattr(self.form, 'webview', None)
        point = webview.PointToScreen(Point(0, 0)) if webview else None
        padding = self.form.Padding
        return {'units': 'physical screen pixels', 'windowRect': rect(window),
                'extendedFrameBounds': rect(visible) if result == 0 else None, 'dwmResult': result,
                'clientOrigin': {'x': origin.x, 'y': origin.y},
                'webviewOrigin': {'x': point.X, 'y': point.Y} if point else None,
                'hostPadding': {'left': padding.Left, 'top': padding.Top, 'right': padding.Right, 'bottom': padding.Bottom}}

    def caption_hit_observation(self):
        from System.Drawing import Point
        results = []
        for index, button in enumerate(self.buttons):
            point = button.PointToScreen(Point(button.Width // 2, button.Height // 2))
            packed = (point.X & 0xFFFF) | ((point.Y & 0xFFFF) << 16)
            handles = (self.hwnd, int(self.caption.Handle.ToInt64()), int(button.Handle.ToInt64()))
            results.append({'button': button.AccessibleName, 'expected': [9, -1, -1] if index == 1 else [1, 1, 1],
                            'framePanelButton': [self.user32.SendMessageW(hwnd, 0x84, 0, packed) for hwnd in handles]})
        return results

    def resize_hit_observation(self):
        """Own-HWND routing diagnostics. Physical edge dragging is a separate QA step."""
        rect = wintypes.RECT()
        self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        points = ((width // 2, 1, 0, 12), (width - 1, height // 2, 1, 11),
                  (width // 2, height - 1, 2, 15), (1, height // 2, 3, 10),
                  (1, 1, 0, 13), (width - 1, 1, 0, 14),
                  (width - 1, height - 1, 2, 17), (1, height - 1, 2, 16))
        results = []
        for x, y, target, expected in points:
            packed = ((rect.left + x) & 0xFFFF) | (((rect.top + y) & 0xFFFF) << 16)
            hwnd = int(self._resize_targets[target].Handle.ToInt64())
            results.append({'point': [x, y], 'expected': expected,
                            'frame': self.user32.SendMessageW(self.hwnd, 0x84, 0, packed),
                            'target': self.user32.SendMessageW(hwnd, 0x84, 0, packed)})
        return results

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
        hover = ColorTranslator.FromHtml(colors['hover'])
        if SystemInformation.HighContrast:
            background, foreground, hover = SystemColors.Window, SystemColors.WindowText, SystemColors.Highlight
        self._foreground = foreground
        self.form.BackColor = self.caption.BackColor = background
        self.label.ForeColor = foreground
        for index, button in enumerate(self.buttons):
            button.BackColor, button.ForeColor = background, foreground
            button.FlatAppearance.MouseOverBackColor = ColorTranslator.FromHtml(colors['caption-close']) if index == 2 else hover
            button.FlatAppearance.MouseDownBackColor = ColorTranslator.FromHtml(colors['caption-close']) if index == 2 else hover
            button.Invalidate()
        if self._max_hover:
            self.buttons[1].BackColor = hover
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
