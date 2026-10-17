from __future__ import annotations

import argparse
import io
import json
import os
import secrets
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from landrop.errors import AppError
from landrop.files import file_id, open_shared, trusted_path
from landrop.runtime import InstanceGuard, RuntimeStore
from landrop.settings import SettingsStore, empty_settings
from landrop.state import State


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = State(self.root / 'state')
        self.token = self.state.create_session('phone', 'Android', '127.0.0.1')
        self.phone = {**self.state.session(self.token), '_token': self.token}
        self.admin_token = self.state.create_session('admin', '', '127.0.0.1')
        self.admin = {**self.state.session(self.admin_token), '_token': self.admin_token}

    def tearDown(self):
        self.temp.cleanup()

    def test_unknown_schema_is_preserved_and_blocks_mutation(self):
        path = self.root / 'unknown.json'
        raw = b'{"version":42,"private":"keep"}'
        path.write_bytes(raw)
        store = SettingsStore(path)
        with self.assertRaises(AppError):
            store.commit(empty_settings())
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(store.problem, 'newer-version')

    def test_recovery_keeps_exact_corrupt_original(self):
        path = self.root / 'broken.json'
        path.write_bytes(b'broken\xff\x00')
        store = SettingsStore(path)
        backup = store.recover()
        self.assertEqual(backup.read_bytes(), b'broken\xff\x00')
        self.assertEqual(json.loads(path.read_bytes())['files'], [])
        self.assertEqual(store.problem, '')

    def test_failed_disk_commit_does_not_publish_in_memory(self):
        shared = self.root / 'file.apk'
        shared.write_bytes(b'first')
        before = self.state.config
        with patch('landrop.settings.os.replace', side_effect=OSError('full')):
            with self.assertRaises(AppError):
                self.state.add_files([str(shared)])
        self.assertEqual(self.state.config, before)
        self.assertEqual(self.state.catalog, {})
        self.assertEqual(list(self.state.data_dir.glob('.settings-*.tmp')), [])

    def test_external_edit_is_not_overwritten(self):
        store = self.state.settings
        store.commit(empty_settings())
        self.state.config_path.write_bytes(b'{"version":100}')
        with self.assertRaises(AppError):
            store.commit(empty_settings())
        self.assertEqual(self.state.config_path.read_bytes(), b'{"version":100}')

    def test_failed_backup_cannot_reset_settings(self):
        self.state.config_path.write_bytes(b'broken')
        store = SettingsStore(self.state.config_path)
        with patch('landrop.settings.shutil.copy2', side_effect=OSError('denied')):
            with self.assertRaises(AppError):
                store.recover()
        self.assertEqual(self.state.config_path.read_bytes(), b'broken')
        self.assertTrue(store.problem)

    def begin(self, session=None, name='payload.apk', size=3):
        identifier = secrets.token_hex(16)
        self.state.uploads.create(session or self.phone, identifier, name, size)
        return identifier

    def test_upload_idempotency_does_not_create_duplicate_file(self):
        identifier = self.begin()
        result = self.state.uploads.receive(identifier, self.phone, io.BytesIO(b'abc'), 3)
        again = self.state.uploads.create(self.phone, identifier, 'payload.apk', 3)
        self.assertEqual(result, again)
        with self.assertRaises(AppError):
            self.state.uploads.receive(identifier, self.phone, io.BytesIO(b'abc'), 3)
        self.assertEqual(len(list(self.state.inbox.iterdir())), 1)

    def test_upload_status_and_cancel_are_owner_bound(self):
        identifier = self.begin()
        token = self.state.create_session('phone', 'other', '127.0.0.1')
        other = {**self.state.session(token), '_token': token}
        for operation in (self.state.uploads.status, self.state.uploads.cancel):
            with self.assertRaises(AppError):
                operation(identifier, other)
        self.assertEqual(self.state.uploads.status(identifier, self.phone)['phase'], 'queued')

    def test_cancellation_before_commit_removes_partial(self):
        identifier = self.begin()
        service = self.state.uploads
        class Reader:
            def read(_self, _size):
                service.cancel(identifier, self.phone)
                return b'abc'
        with self.assertRaises(AppError):
            service.receive(identifier, self.phone, Reader(), 3)
        self.assertEqual(service.status(identifier, self.phone)['phase'], 'cancelled')
        self.assertEqual(list(self.state.inbox.iterdir()), [])
        self.assertEqual(list(self.state.partial_dir.iterdir()), [])

    def test_cancellation_after_commit_reports_completed(self):
        identifier = self.begin()
        self.state.uploads.receive(identifier, self.phone, io.BytesIO(b'abc'), 3)
        result = self.state.uploads.cancel(identifier, self.phone)
        self.assertEqual(result['phase'], 'completed')
        self.assertEqual((self.state.inbox / result['savedName']).read_bytes(), b'abc')

    def test_failed_shared_upload_commit_removes_only_new_copy(self):
        original = self.state.outbox / 'payload.apk'
        original.write_bytes(b'old')
        identifier = self.begin(self.admin)
        with patch.object(self.state.settings, 'commit', side_effect=AppError('save failed', 507)):
            with self.assertRaises(AppError):
                self.state.uploads.receive(identifier, self.admin, io.BytesIO(b'abc'), 3)
        self.assertEqual(original.read_bytes(), b'old')
        self.assertEqual(list(self.state.outbox.iterdir()), [original])
        self.assertEqual(self.state.config['files'], [])

    def test_complete_file_with_legacy_temp_name_survives_cleanup(self):
        filename = '.landrop-' + secrets.token_hex(16) + '.part'
        (self.state.inbox / filename).write_bytes(b'abc')
        self.state.cleanup_owned_partials()
        self.assertEqual((self.state.inbox / filename).read_bytes(), b'abc')
        self.assertEqual(self.state.inbox_files()[0]['name'], filename)

    def test_revocation_blocks_final_commit(self):
        identifier = self.begin()
        class Reader:
            def read(_self, _size):
                self.state.auth.revoke(self.phone['id'])
                return b'abc'
        with self.assertRaises(AppError):
            self.state.uploads.receive(identifier, self.phone, Reader(), 3)
        self.assertEqual(list(self.state.inbox.iterdir()), [])

    def test_changed_download_source_requires_refresh(self):
        path = self.root / 'build.apk'
        path.write_bytes(b'old')
        self.state.add_files([str(path)])
        path.write_bytes(b'new-and-larger')
        with self.assertRaises(AppError):
            with open_shared(path, self.state.file_identity(file_id(path))):
                pass

    @unittest.skipUnless(os.name == 'nt', 'Windows junction boundary')
    def test_new_junction_cannot_publish_or_read_a_different_target(self):
        target = self.root / 'private'
        target.mkdir()
        (target / 'private.apk').write_bytes(b'private')
        link = self.root / 'shared'
        completed = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
        self.assertEqual(completed.returncode, 0)
        try:
            with self.assertRaises(AppError):
                trusted_path(link / 'private.apk')
            with self.assertRaises(AppError):
                with open_shared(link / 'private.apk', None):
                    pass
        finally:
            link.rmdir()

    def test_runtime_secret_roundtrip_has_no_plaintext(self):
        store = RuntimeStore(self.root / 'runtime.json')
        secret = secrets.token_urlsafe(32)
        store.write(34567, secret)
        self.assertNotIn(secret, store.path.read_text('utf-8'))
        self.assertEqual(store.read().secret, secret)
        self.assertNotIn(secret, repr(store.read()))
        store.remove_owned()
        self.assertFalse(store.path.exists())

    def test_headless_instance_has_exclusive_lock(self):
        first, second = InstanceGuard(self.root), InstanceGuard(self.root)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.close()
            self.assertTrue(second.acquire())
        finally:
            second.close()
            if not first.stream.closed:
                first.close()

    def test_runtime_save_failure_cleans_started_service(self):
        args = argparse.Namespace(test_data=True, share=[], headless=True, port=0, no_browser=True)
        servers = []
        factory = main.Server
        def record(*values):
            server = factory(*values)
            servers.append(server)
            return server
        with patch('main.logging.basicConfig'), patch('main.Server', side_effect=record), patch('main.RuntimeStore.write', side_effect=OSError('full')):
            with self.assertRaises(OSError):
                main.run(args, self.state.data_dir, self.state.data_dir / 'runtime.json')
        self.assertTrue(servers[0].state.stopping.is_set())
        self.assertEqual(servers[0].socket.fileno(), -1)

    def test_random_port_skips_browser_blocked_port(self):
        from unittest.mock import Mock
        blocked, usable = Mock(server_port=5060), Mock(server_port=49152)
        with patch('main.Server', side_effect=[blocked, usable]):
            self.assertIs(main.bind_server(0, self.state), usable)
        blocked.server_close.assert_called_once()
        usable.server_close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
