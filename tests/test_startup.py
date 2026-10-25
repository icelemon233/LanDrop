from __future__ import annotations

import argparse
import http.cookiejar
import io
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler

import main
from landrop.server import Server
from landrop.state import State
from landrop.errors import AppError
from landrop import launcher
from landrop.runtime import RuntimeInfo


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.temp.name))
        state = self.state
        class WindowFixture:
            def __init__(self):
                self.ready = threading.Event()
                self.ready.set()
                self.calls = []
                self.chrome = Mock()
            def preferences(self):
                return {'closeBehavior': state.config.get('preferences', {}).get('windowCloseBehavior', 'tray'), 'trayAvailable': True}
            def _on_ui(self, operation):
                return operation()
            def call(self, action):
                self.calls.append(action)
                return True
        self.desktop = WindowFixture()
        self.server = Server(('127.0.0.1', 0), self.state, self.desktop)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.runtime = self.state.data_dir / 'runtime.json'
        self.runtime.write_text(json.dumps({'port': self.state.port, 'admin': self.state.admin_token}), 'utf-8')
        self.args = argparse.Namespace(share=[], no_browser=False, headless=False)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_reopening_exe_activates_existing_window_without_a_browser(self):
        with patch('webbrowser.open') as opened:
            self.assertTrue(main.reopen(self.runtime, self.args))
            opened.assert_not_called()
        self.assertEqual(self.desktop.calls, ['activate'])

    def test_ui_qa_listener_can_be_restricted_to_loopback(self):
        server = main.bind_server(0, self.state, loopback_only=True)
        try:
            self.assertEqual(server.socket.getsockname()[0], '127.0.0.1')
        finally:
            server.server_close()

    def test_authenticated_entry_still_establishes_a_local_admin_session(self):
        launched = launcher.post(launcher.local_client(), f'http://127.0.0.1:{self.state.port}', '/api/desktop-launch', {'token': self.state.admin_token})
        url = launched['url']
        self.assertEqual(urlsplit(url).fragment, '')
        self.assertTrue(urlsplit(url).path.startswith('/desktop/'))
        browser = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with browser.open(url) as response:
            self.assertEqual(response.url, f'http://127.0.0.1:{self.state.port}/desktop')
            self.assertIn(b'data-client="desktop"', response.read())
        with browser.open(f'http://127.0.0.1:{self.state.port}/api/state') as response:
            self.assertEqual(json.load(response)['role'], 'admin')

    def test_stale_runtime_cannot_open_expired_login_page(self):
        self.runtime.write_text(json.dumps({'port': self.state.port, 'admin': 'stale'}), 'utf-8')
        with patch('webbrowser.open') as opened:
            with self.assertRaises(AppError):
                main.reopen(self.runtime, self.args)
            opened.assert_not_called()

    def test_authenticated_window_settings_are_saved_and_reported(self):
        base = f'http://127.0.0.1:{self.state.port}'
        client = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        launched = launcher.post(client, base, '/api/desktop-launch', {'token': self.state.admin_token})
        client.open(launched['url']).close()
        launcher.post(client, base, '/api/admin/window-close-behavior', {'behavior': 'exit'})
        launcher.post(client, base, '/api/admin/window-theme', {'mode': 'dark'})
        self.desktop.chrome.set_theme.assert_called_once_with('dark')
        with client.open(base + '/api/state') as response:
            self.assertEqual(json.load(response)['desktop'], {'closeBehavior': 'exit', 'trayAvailable': True})
        restored = State(self.state.data_dir)
        self.assertEqual(restored.config['preferences']['windowTheme'], 'dark')
        with client.open(base + '/desktop') as response:
            self.assertIn(b'data-window-theme="dark"', response.read())
        with self.assertRaises(AppError):
            launcher.post(client, base, '/api/admin/window-close-behavior', {'behavior': 'unknown'})
        self.assertEqual(self.state.config['preferences']['windowCloseBehavior'], 'exit')

    def test_local_reopen_works_with_proxy_environment(self):
        import os
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1', 'NO_PROXY': '', 'no_proxy': ''}), patch('webbrowser.open') as opened:
            self.assertTrue(main.reopen(self.runtime, self.args))
            opened.assert_not_called()
            self.assertEqual(self.desktop.calls, ['activate'])

    def test_every_exe_launch_gets_an_independent_ticket(self):
        client = launcher.local_client()
        base = f'http://127.0.0.1:{self.state.port}'
        first = launcher.post(client, base, '/api/desktop-launch', {'token': self.state.admin_token})
        second = launcher.post(client, base, '/api/desktop-launch', {'token': self.state.admin_token})
        self.assertNotEqual(first['url'], second['url'])

    def test_headless_reopen_does_not_activate_a_window(self):
        self.args.headless = True
        self.assertTrue(main.reopen(self.runtime, self.args))
        self.assertEqual(self.desktop.calls, [])

    def test_regular_reopen_does_not_fall_back_to_a_browser_for_headless_service(self):
        self.server.desktop = None
        with patch('webbrowser.open') as opened:
            with self.assertRaises(AppError) as failure:
                main.reopen(self.runtime, self.args)
            self.assertEqual(failure.exception.code, 'desktop-unavailable')
            opened.assert_not_called()

    def test_wrong_instance_pid_stops_before_sending_credential(self):
        self.runtime.write_text(json.dumps({'port':self.state.port,'admin':self.state.admin_token,'pid':os.getpid()+100000}), 'utf-8')
        with patch('landrop.launcher.post') as posted:
            with self.assertRaises(AppError) as rejected:
                main.reopen(self.runtime,self.args)
            self.assertEqual(rejected.exception.code, 'runtime-mismatch')
            posted.assert_not_called()

    def test_stopping_service_is_not_treated_as_absent(self):
        self.state.stopping.set()
        with self.assertRaises(launcher.InstanceStopping):
            main.reopen(self.runtime,self.args)

    def test_shutdown_succeeds_when_runtime_is_locked_for_deletion(self):
        info=RuntimeInfo(self.state.port,self.state.admin_token,os.getpid(),'1.1.2')
        with patch('landrop.launcher.RuntimeStore') as store, patch('landrop.launcher.ProcessWaiter') as processes, patch('landrop.launcher.local_client') as client, patch('landrop.launcher.post'):
            store.return_value.read.side_effect=[info,AppError('runtime locked for deletion',409,'runtime-unreadable')]
            processes.return_value.handles=[1]
            client.return_value.open.return_value=io.BytesIO(json.dumps({'app':'landrop','pid':info.pid,'version':info.version}).encode())
            launcher.stop_previous(self.runtime)
            processes.return_value.wait.assert_called_once()
            processes.return_value.close.assert_called_once()
            store.return_value.read.assert_called_once()


class InstanceStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, reopen, run, stop=None):
        with patch('sys.argv',['main.py','--headless','--no-browser','--approve-upgrade','--state-dir',str(self.directory)]), patch('main.logging.basicConfig'), patch('main.reopen',side_effect=reopen), patch('main.run',side_effect=run), patch('main.launcher.stop_previous',side_effect=stop), patch('main.time.sleep'):
            main.main()

    def test_existing_legacy_is_checked_even_if_instance_lock_is_free(self):
        events=[]
        self.invoke(lambda *_: events.append('reuse') or True, lambda *_: events.append('new-server'))
        self.assertEqual(events,['reuse'])

    def test_legacy_upgrade_happens_before_starting_new_service(self):
        events=[]
        def old(*_):
            events.append('old-detected')
            raise launcher.UpgradeRequired('1.0.1')
        self.invoke(old,lambda *_:events.append('new-server'),lambda *_:events.append('old-exited'))
        self.assertEqual(events,['old-detected','old-exited','new-server'])

    def test_stopping_instance_finishes_before_new_service(self):
        events=[]
        checks=iter([launcher.InstanceStopping(),False])
        def check(*_):
            value=next(checks)
            events.append('check')
            if isinstance(value,Exception):
                raise value
            return value
        self.invoke(check,lambda *_:events.append('new-server'))
        self.assertEqual(events,['check','check','new-server'])

    @unittest.skipUnless(os.name=='nt','Windows socket semantics')
    def test_windows_port_is_exclusive_even_against_reuseaddr(self):
        state=State(self.directory/'state')
        server=Server(('0.0.0.0',0),state)
        try:
            with socket.socket() as competing:
                competing.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                with self.assertRaises(OSError):
                    competing.bind(('0.0.0.0',server.server_port))
            self.assertEqual(server.socket.getsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE),1)
        finally:
            server.server_close()

    @unittest.skipUnless(os.name=='nt','Windows socket semantics')
    def test_legacy_reusable_listener_gets_a_different_port(self):
        with socket.socket() as legacy:
            legacy.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            legacy.bind(('0.0.0.0',0))
            legacy.listen()
            legacy_port=legacy.getsockname()[1]
            state=State(self.directory/'state')
            server=main.bind_server(legacy_port,state)
            try:
                self.assertNotEqual(server.server_port,legacy_port)
            finally:
                server.server_close()


if __name__ == '__main__':
    unittest.main()
