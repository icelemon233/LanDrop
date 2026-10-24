"""Render native caption controls and test their click handlers in an isolated QA form."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
work = args.work.resolve()
if not work.is_relative_to(ROOT / '.local'):
    raise SystemExit('Use an isolated directory inside .local/.')
work.mkdir(parents=True, exist_ok=False)

# Same process DPI policy as the desktop host, before creating any HWND.
ctypes.windll.user32.SetProcessDPIAware()
import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')
from System.Drawing import Bitmap, Point, Rectangle, Size, SizeF
from System.Drawing.Imaging import ImageFormat
from System.Threading import ApartmentState, Thread, ThreadStart
from System.Windows.Forms import Application, AutoScaleMode, Form, FormWindowState, Screen

from landrop.state import State
from landrop.window_chrome import WindowChrome

errors = []


def run():
    chrome = form = None
    try:
        Application.EnableVisualStyles()
        Application.SetCompatibleTextRenderingDefault(False)

        class TestForm(Form):
            pass

        form = TestForm()
        form.Text = 'LanDrop · 标题栏 QA'
        form.AutoScaleDimensions = SizeF(96., 96.)
        form.AutoScaleMode = AutoScaleMode.Dpi
        hwnd = int(form.Handle.ToInt64())
        user32 = ctypes.WinDLL('user32')
        user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        dpi = user32.GetDpiForWindow(hwnd)
        scale = dpi / 96
        form.Size = Size(round(1180 * scale), round(780 * scale))
        form.MinimumSize = Size(round(800 * scale), round(600 * scale))
        state = State(work / 'state', test_mode=True)
        host = SimpleNamespace(state=state, window=SimpleNamespace(native=form), _on_ui=lambda operation: operation(), _activate=lambda: None, _request_exit=lambda: None)
        chrome = WindowChrome(host)
        form.Show()
        Application.DoEvents()
        chrome._layout()

        def capture(theme):
            chrome.set_theme(theme)
            Application.DoEvents()
            image = Bitmap(chrome.caption.Width, chrome.caption.Height)
            image.SetResolution(float(dpi), float(dpi))
            try:
                chrome.caption.DrawToBitmap(image, Rectangle(0, 0, image.Width, image.Height))
                image.Save(str(work / f'caption-{theme}.png'), ImageFormat.Png)
            finally:
                image.Dispose()

        capture('light')
        capture('dark')
        chrome._bitmap.Save(str(work / 'caption-logo.png'), ImageFormat.Png)
        graphics = form.CreateGraphics()
        try:
            font_pixels = chrome.label.Font.GetHeight(graphics)
            graphics_dpi = graphics.DpiY
        finally:
            graphics.Dispose()

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
        user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.POINT)]
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        origin = ctypes.wintypes.POINT()
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        assert origin.y == rect.top, 'Residual native caption strip'

        hit_results = []
        for button in chrome.buttons:
            point = button.PointToScreen(Point(button.Width // 2, button.Height // 2))
            packed = (point.X & 0xFFFF) | ((point.Y & 0xFFFF) << 16)
            hits = [int(user32.SendMessageW(handle, 0x84, 0, packed)) for handle in (hwnd, int(chrome.caption.Handle.ToInt64()), int(button.Handle.ToInt64()))]
            assert hits == [1, 1, 1], (button.AccessibleName, hits)
            hit_results.append({'button': button.AccessibleName, 'framePanelButtonHits': hits})

        # These are managed control events, not injected physical mouse input.
        chrome.buttons[0].PerformClick()
        Application.DoEvents()
        assert form.WindowState == FormWindowState.Minimized
        form.WindowState = FormWindowState.Normal
        Application.DoEvents()
        chrome.buttons[1].PerformClick()
        Application.DoEvents()
        assert form.WindowState == FormWindowState.Maximized
        screen = Screen.FromHandle(form.Handle).WorkingArea
        client_origin = form.PointToScreen(Point(0, 0))
        assert client_origin.X == screen.Left and client_origin.Y == screen.Top
        assert form.ClientSize.Width == screen.Width and form.ClientSize.Height == screen.Height
        chrome.buttons[1].PerformClick()
        Application.DoEvents()
        assert form.WindowState == FormWindowState.Normal
        assert not state.stopping.is_set()

        logo = ROOT / 'landrop/web/assets/cinna-icon.png'
        report = {'dpi': dpi, 'graphicsDpi': graphics_dpi, 'captionHeight': chrome.caption.Height,
            'captionFontPoints': chrome.label.Font.SizeInPoints, 'captionFontPixelHeight': font_pixels,
            'captionEmPixels': chrome.label.Font.SizeInPoints * graphics_dpi / 72,
            'clientTopInset': origin.y - rect.top, 'glyphLogicalSize': 10,
            'logoSourceSha256': hashlib.sha256(logo.read_bytes()).hexdigest(), 'logoBitmapSize': [chrome._bitmap.Width, chrome._bitmap.Height],
            'hitTests': hit_results, 'managedButtonEvents': ['minimize', 'maximize', 'restore'],
            'physicalMouseInput': 'not-tested', 'snapHoverMenu': 'not-tested'}
        # GetHeight is line spacing, not the em size. Compare point-to-pixel
        # conversion against the 14 logical-pixel caption text contract.
        assert abs(report['captionEmPixels'] / (graphics_dpi / 96) - 14) < .1, report
        (work / 'caption-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
        print(json.dumps(report, ensure_ascii=True), flush=True)
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        if chrome:
            chrome.dispose()
        if form:
            form.Close()
            form.Dispose()


thread = Thread(ThreadStart(run))
thread.SetApartmentState(ApartmentState.STA)
thread.IsBackground = True
thread.Start()
if not thread.Join(30000):
    raise SystemExit('Native caption QA timed out.')
if errors:
    raise SystemExit('\n'.join(errors))
