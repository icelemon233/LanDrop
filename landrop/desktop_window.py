"""The Windows window owns the desktop UI; HTTP remains the phone boundary."""
from __future__ import annotations

import os
import json
import logging
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .errors import AppError
from .platform_identity import set_app_identity


def is_window_url(url: str, port: int) -> bool:
    try:
        target = urlsplit(url)
        return (target.scheme == 'http' and target.netloc == f'127.0.0.1:{port}'
                and (target.path == '/desktop'
                     or re.fullmatch(r'/desktop/[A-Za-z0-9_-]+', target.path) is not None
                     or re.fullmatch(r'/download/[a-f0-9]{24}', target.path) is not None))
    except (TypeError, ValueError):
        return False


class DesktopWindow:
    def __init__(self, state, webview_module=None):
        if webview_module is None:
            if os.name == 'nt':
                from .window_runtime import has_webview2
                if not has_webview2():
                    raise AppError('缺少 Microsoft Edge WebView2 运行时。请运行 LanDrop 安装程序修复后重新打开。', 503, 'window-runtime-missing')
            import webview as webview_module
        self.webview = webview_module
        self.state = state
        self.inbox = state.inbox
        self.window = None
        self.ready = threading.Event()
        self.lock = threading.RLock()
        self.dialog_busy = False
        self.closed = False
        self.allow_close = False
        self.failure = None
        self._downloads = set()
        self.chrome = None

    def preferences(self):
        return {'closeBehavior': self.state.config.get('preferences', {}).get('windowCloseBehavior', 'tray'),
                'trayAvailable': bool(self.chrome and self.chrome.available)}

    def prepare(self):
        set_app_identity()
        self.webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
        # Downloads use our owned dialog so maintenance cannot close the app
        # while a save picker is active. The renderer's default handler cancels
        # first; our handler enables only validated local downloads afterward.
        self.webview.settings['ALLOW_DOWNLOADS'] = False
        self.window = self.webview.create_window(
            'LanDrop', self.state.admin_url, width=1180, height=780,
            min_size=(800, 600), background_color=self._background(),
        )
        self.window.events.before_show += self._configure_native
        self.window.events.loaded += self._loaded
        self.window.events.closing += self._closing
        self.window.events.closed += self._closed

    def _configure_native(self):
        from .window_chrome import WindowChrome
        self.chrome = WindowChrome(self)
        control = self.window.native.webview
        control.NavigationStarting += self._navigation
        control.CoreWebView2InitializationCompleted += self._initialized

    def _background(self):
        from .window_chrome import theme_colors
        mode = self.state.config.get('preferences', {}).get('windowTheme', 'auto')
        return theme_colors(mode)['canvas']

    def _navigation(self, sender, args):
        if str(args.Uri) != 'about:blank' and not is_window_url(str(args.Uri), self.state.port):
            args.Cancel = True

    def _initialized(self, sender, args):
        if not args.IsSuccess:
            self.failure = AppError('桌面窗口未能加载。请修复 Microsoft Edge WebView2 运行时后重新打开 LanDrop。', 503, 'window-unavailable')
            self.allow_close = True
            self.ready.set()
            self.window.destroy()
            return
        sender.CoreWebView2.DownloadStarting += self._download

    def _loaded(self):
        self.ready.set()
        if self.state.test_mode:
            # Read-only, isolated test evidence; no GUI actions or credentials.
            try:
                until = time.monotonic() + 20
                while not self.closed and time.monotonic() < until:
                    script = "JSON.stringify({phase:document.body.dataset.connectionPhase,role:document.body.dataset.role,title:document.title,width:innerWidth,height:innerHeight,theme:document.documentElement.dataset.theme,host:document.body.dataset.desktopHost,overflow:document.documentElement.scrollWidth>innerWidth})"
                    task = self._on_ui(lambda: self.window.native.webview.CoreWebView2.ExecuteScriptAsync(script))
                    task.Wait(5000)
                    if not task.IsCompleted:
                        continue
                    observation = json.loads(json.loads(str(task.Result)))
                    if observation.get('phase') == 'connected':
                        if self.chrome:
                            observation['native'] = self._on_ui(lambda: {
                                'dpi': round(self.chrome.scale * 96),
                                'winformsDpi': self.window.native.DeviceDpi,
                                'captionHeight': self.chrome.caption.Height,
                                'captionTheme': self.chrome.mode,
                                'trayAvailable': self.chrome.available,
                                'webviewTop': self.window.native.webview.Top,
                                'webviewHeight': self.window.native.webview.Height,
                                'clientHeight': self.window.native.ClientSize.Height,
                                'windowHeight': self.window.native.Height,
                                'windowWidth': self.window.native.Width,
                                'captionButtons': [button.AccessibleName for button in self.chrome.buttons],
                                'captionFontPoints': self.chrome.label.Font.SizeInPoints,
                                'captionGlyphPixels': round(10 * self.chrome.scale),
                                'clientTopInset': self.chrome.client_top_inset(),
                            })
                            self._on_ui(lambda: self.chrome.render_caption(self.state.data_dir / 'native-caption.png'))
                        (self.state.data_dir / 'desktop-observation.json').write_text(json.dumps(observation), 'utf-8')
                        break
                    time.sleep(.2)
            except Exception:
                logging.exception('Isolated desktop observation failed')

    def _closed(self):
        with self.lock:
            self.closed = True
        self.state.stopping.set()
        self.state.scan_requested.set()
        self.ready.set()

    def _closing(self):
        with self.lock:
            if self.dialog_busy:
                return False
        if not self.allow_close:
            if self.preferences()['closeBehavior'] == 'tray':
                hidden = False
                try:
                    hidden = bool(self.chrome and self._on_ui(self.chrome.hide))
                except Exception:
                    logging.exception('Tray hide failed; minimizing instead')
                if not hidden:
                    self.window.minimize()
                return False
            if not self._confirm_exit():
                return False
            self.allow_close = True
        self.state.stopping.set()
        self.state.scan_requested.set()
        self.state.uploads.cancel_all()
        for operation in tuple(self._downloads):
            operation.Cancel()
        if self.chrome:
            self._on_ui(self.chrome.dispose)
        return True

    def _confirm_exit(self):
        if not self.state.uploads.active_count() and not self.state.active_downloads and not self._downloads:
            return True
        from System.Windows.Forms import DialogResult, MessageBox, MessageBoxButtons, MessageBoxIcon
        return self._on_ui(lambda: MessageBox.Show(self.window.native, '退出会中断正在进行的传输。已保存的文件和共享目录会保留。是否退出？', '退出 LanDrop', MessageBoxButtons.YesNo, MessageBoxIcon.Warning)) == DialogResult.Yes

    def _request_exit(self):
        try:
            self.ensure_can_shutdown()
            if self._confirm_exit():
                self.allow_close = True
                self.window.destroy()
        except AppError:
            from System.Windows.Forms import MessageBox
            MessageBox.Show(self.window.native, '请先关闭系统文件选择窗口，再退出 LanDrop。', 'LanDrop')

    def ensure_can_shutdown(self):
        with self.lock:
            if self.dialog_busy:
                raise AppError('请先关闭系统文件选择窗口，再退出 LanDrop。', 409, 'desktop-busy')

    def _begin_dialog(self):
        with self.lock:
            if self.closed or self.state.stopping.is_set():
                raise AppError('电脑端已退出，请重新打开 LanDrop。', 503, 'desktop-closed')
            if self.dialog_busy:
                raise AppError('请先完成当前的文件选择。', 409, 'desktop-busy')
            self.dialog_busy = True

    def _end_dialog(self):
        with self.lock:
            self.dialog_busy = False

    def _on_ui(self, operation):
        from System import Action
        result, errors = [], []
        def execute():
            try:
                result.append(operation())
            except Exception as error:
                errors.append(error)
        try:
            if self.window.native.InvokeRequired:
                self.window.native.Invoke(Action(execute))
            else:
                execute()
        except Exception as error:
            raise AppError('桌面窗口暂时无法响应，请重试。', 503, 'desktop-unavailable') from error
        if errors:
            raise AppError('系统窗口操作失败，请重试。', 503, 'desktop-unavailable') from errors[0]
        return result[0] if result else None

    def _download(self, sender, args):
        args.Cancel = True
        if not is_window_url(str(args.DownloadOperation.Uri), self.state.port):
            return
        try:
            self._begin_dialog()
        except AppError:
            return
        try:
            selected = self.window.create_file_dialog(
                self.webview.FileDialog.SAVE,
                save_filename=Path(str(args.ResultFilePath)).name,
            )
            if selected:
                args.ResultFilePath = str(selected[0])
                args.Cancel = False
                args.Handled = True
                operation = args.DownloadOperation
                self._downloads.add(operation)
                def finished(*_):
                    if str(operation.State) != 'InProgress':
                        self._downloads.discard(operation)
                operation.StateChanged += finished
        finally:
            self._end_dialog()

    def _activate(self):
        from System.Windows.Forms import FormWindowState
        from Microsoft.Web.WebView2.Core import CoreWebView2CookieSameSiteKind
        def activate():
            form = self.window.native
            core = form.webview.CoreWebView2
            token = self.state.create_session('admin', 'LanDrop desktop', '127.0.0.1')
            cookie = core.CookieManager.CreateCookie('landrop', token, '127.0.0.1', '/')
            cookie.IsHttpOnly = True
            cookie.SameSite = CoreWebView2CookieSameSiteKind.Strict
            core.CookieManager.AddOrUpdateCookie(cookie)
            if form.WindowState == FormWindowState.Minimized:
                form.WindowState = self.chrome.last_window_state if self.chrome else FormWindowState.Normal
            form.Show()
            form.Activate()
            core.ExecuteScriptAsync("document.dispatchEvent(new Event('visibilitychange'))")
        self._on_ui(activate)
        return True

    def call(self, action: str):
        if not self.ready.wait(20):
            raise AppError('桌面窗口仍在启动，请稍后重试。', 503, 'desktop-starting')
        with self.lock:
            if self.closed or self.failure:
                raise AppError('桌面窗口已关闭，请重新打开 LanDrop。', 503, 'desktop-closed')
        if action == 'activate':
            return self._activate()
        if action == 'open-inbox':
            os.startfile(str(self.inbox))
            return True
        if action == 'shutdown':
            self.ensure_can_shutdown()
            self.allow_close = True
            self.window.destroy()
            return True
        if action not in {'files', 'folder'}:
            raise AppError('未知的桌面操作。')
        self._begin_dialog()
        try:
            if action == 'files':
                return list(self._on_ui(lambda: self.window.create_file_dialog(
                    self.webview.FileDialog.OPEN, allow_multiple=True,
                    file_types=('所有文件 (*.*)', '安卓安装包 (*.apk;*.aab;*.apks;*.xapk)'),
                )) or ())
            selected = self._on_ui(lambda: self.window.create_file_dialog(self.webview.FileDialog.FOLDER))
            return str(selected[0]) if selected else ''
        finally:
            self._end_dialog()

    def run(self):
        profile = self.state.data_dir / 'window-profile'
        icon = Path(__file__).resolve().parent.parent / 'resources/app.ico'
        self.webview.start(gui='edgechromium', debug=False, private_mode=False,
                           storage_path=str(profile), icon=str(icon),
                           localization={'global.ok': '确定', 'global.cancel': '取消', 'global.quit': '退出', 'windows.fileFilter.allFiles': '所有文件'})
        if self.failure:
            raise self.failure

    def close(self):
        # Called only after the GUI loop has finished, or before it was started.
        with self.lock:
            self.closed = True
        self.ready.set()
