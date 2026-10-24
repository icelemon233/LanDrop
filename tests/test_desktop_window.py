from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from landrop.desktop_window import DesktopWindow, is_window_url
from landrop.errors import AppError
from landrop.state import State
from landrop.window_runtime import valid_runtime_version
from landrop.window_chrome import caption_hit


class DesktopWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.temp.name))
        self.state.port = 41421
        self.gui = SimpleNamespace(FileDialog=SimpleNamespace(OPEN=1, FOLDER=2, SAVE=3))
        self.host = DesktopWindow(self.state, self.gui)
        self.window = Mock()
        self.host.window = self.window
        self.host.ready.set()
        self.host._on_ui = lambda operation: operation()

    def tearDown(self):
        self.temp.cleanup()

    def test_navigation_is_limited_to_this_desktop_and_its_downloads(self):
        for path in ('/desktop', '/desktop/one-time_ticket', '/desktop?view=received', '/download/' + 'a' * 24 + '?received=1'):
            self.assertTrue(is_window_url('http://127.0.0.1:41421' + path, 41421))
        for url in ('https://example.com', 'file:///C:/Windows', 'http://127.0.0.1:41422/desktop', 'http://127.0.0.1:41421@evil.test/desktop', 'http://127.0.0.1:41421/api/state', 'http://127.0.0.1:41421/'):
            self.assertFalse(is_window_url(url, 41421), url)

    def test_dialog_cancel_clears_busy_and_does_not_start_shutdown(self):
        self.window.create_file_dialog.return_value = None
        self.assertEqual(self.host.call('files'), [])
        self.assertFalse(self.host.dialog_busy)
        self.assertFalse(self.state.stopping.is_set())

    def test_file_selection_preserves_paths_and_folder_cancel_is_empty(self):
        self.window.create_file_dialog.return_value = ('D:/合成数据/应用.apk',)
        self.assertEqual(self.host.call('files'), ['D:/合成数据/应用.apk'])
        self.window.create_file_dialog.return_value = None
        self.assertEqual(self.host.call('folder'), '')

    def test_dialog_failure_releases_busy_flag(self):
        self.window.create_file_dialog.side_effect = RuntimeError('synthetic picker failure')
        with self.assertRaises(RuntimeError):
            self.host.call('files')
        self.assertFalse(self.host.dialog_busy)

    def test_maintenance_and_titlebar_close_refuse_while_picker_is_open(self):
        self.host.dialog_busy = True
        with self.assertRaises(AppError) as blocked:
            self.host.ensure_can_shutdown()
        self.assertEqual(blocked.exception.code, 'desktop-busy')
        self.assertFalse(self.host._closing())
        self.assertFalse(self.state.stopping.is_set())

    def test_unavailable_tray_falls_back_to_taskbar_and_preserves_transfers(self):
        self.state.scan_requested.clear()
        operation = Mock()
        self.host._downloads.add(operation)
        with patch.object(self.state.uploads, 'active_count', return_value=1), \
                patch.object(self.state.uploads, 'cancel_all') as cancel_uploads:
            for active_downloads in (0, 1):
                with self.subTest(active_downloads=active_downloads):
                    self.state.active_downloads = active_downloads
                    self.assertFalse(self.host._closing())
                    self.assertFalse(self.state.stopping.is_set())
                    self.assertFalse(self.state.scan_requested.is_set())
            cancel_uploads.assert_not_called()
        self.assertEqual(self.window.minimize.call_count, 2)
        self.window.create_confirmation_dialog.assert_not_called()
        self.window.destroy.assert_not_called()
        operation.Cancel.assert_not_called()

    def test_close_to_tray_preserves_service_and_owned_transfers(self):
        self.host.chrome = Mock()
        self.host.chrome.hide.return_value = True
        operation = Mock()
        self.host._downloads.add(operation)
        self.assertFalse(self.host._closing())
        self.host.chrome.hide.assert_called_once()
        self.window.minimize.assert_not_called()
        self.assertFalse(self.state.stopping.is_set())
        operation.Cancel.assert_not_called()

    def test_tray_failure_never_hides_the_only_recoverable_window(self):
        self.host.chrome = Mock()
        self.host.chrome.hide.side_effect = OSError('synthetic missing taskbar')
        with self.assertLogs(level='ERROR'):
            self.assertFalse(self.host._closing())
        self.window.minimize.assert_called_once()
        self.assertFalse(self.state.stopping.is_set())

    def test_close_preference_survives_restart_and_respects_cancel(self):
        self.state.set_window_preference('windowCloseBehavior', 'exit')
        restored = State(self.state.data_dir)
        self.assertEqual(DesktopWindow(restored, self.gui).preferences()['closeBehavior'], 'exit')
        with patch.object(self.host, '_confirm_exit', return_value=False):
            self.assertFalse(self.host._closing())
        self.assertFalse(self.state.stopping.is_set())
        with patch.object(self.host, '_confirm_exit', return_value=True):
            self.assertTrue(self.host._closing())
        self.assertTrue(self.state.stopping.is_set())

    def test_window_preference_failure_keeps_the_previous_choice(self):
        with patch('landrop.settings.os.replace', side_effect=OSError('synthetic disk full')):
            with self.assertRaises(AppError):
                self.state.set_window_preference('windowCloseBehavior', 'exit')
        self.assertEqual(self.host.preferences()['closeBehavior'], 'tray')
        with self.assertRaises(AppError):
            self.state.set_window_preference('windowCloseBehavior', 'unknown')

    def test_caption_hit_testing_preserves_edges_and_client_controls_at_dpi_scales(self):
        for scale in (1, 1.25, 1.5, 2):
            with self.subTest(scale=scale):
                width, height = round(1000 * scale), round(700 * scale)
                self.assertEqual(caption_hit(1, 1, width, height, scale, False), 13)
                self.assertEqual(caption_hit(width - 1, height - 1, width, height, scale, False), 17)
                self.assertEqual(caption_hit(round(100 * scale), round(20 * scale), width, height, scale, False), 2)
                self.assertIsNone(caption_hit(round(200 * scale), round(100 * scale), width, height, scale, False))
                self.assertIsNone(caption_hit(width - round(100 * scale), round(20 * scale), width, height, scale, False))
                self.assertEqual(caption_hit(1, 1, width, height, scale, True), 3)

    def test_explicit_exit_cancels_owned_transfers_and_signals_service_cleanup(self):
        self.state.active_downloads = 1
        self.host.allow_close = True
        operation = Mock()
        self.host._downloads.add(operation)
        with patch.object(self.state.uploads, 'cancel_all') as cancel_uploads:
            self.assertTrue(self.host._closing())
            cancel_uploads.assert_called_once()
        self.assertTrue(self.state.stopping.is_set())
        self.assertTrue(self.state.scan_requested.is_set())
        self.window.minimize.assert_not_called()
        operation.Cancel.assert_called_once()

    def test_maintenance_shutdown_closes_window_without_a_second_confirmation(self):
        self.assertTrue(self.host.call('shutdown'))
        self.assertTrue(self.host.allow_close)
        self.window.destroy.assert_called_once()

    def test_external_download_never_opens_a_native_picker(self):
        args = SimpleNamespace(DownloadOperation=SimpleNamespace(Uri='https://example.com/file'), Cancel=False)
        self.host._download(None, args)
        self.assertTrue(args.Cancel)
        self.window.create_file_dialog.assert_not_called()

    def test_missing_or_zero_runtime_version_is_not_an_installed_runtime(self):
        for value in (None, '', '0.0.0.0', '155.invalid.0.0', '1.2'):
            self.assertFalse(valid_runtime_version(value))
        self.assertTrue(valid_runtime_version('155.0.4283.60'))


if __name__ == '__main__':
    unittest.main()
