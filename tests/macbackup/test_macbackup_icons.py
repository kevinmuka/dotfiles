"""Preserve real macOS resource forks using synthetic icon contents only."""
import json
import argparse
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from . import test_macbackup_transport as transport

M = transport.M


@unittest.skipUnless(sys.platform == 'darwin', 'native macOS metadata required')
class IconTests(unittest.TestCase):
    setUp = transport.TransportTests.setUp
    settings = transport.TransportTests.settings
    rules = transport.TransportTests.rules
    cli = transport.TransportTests.cli
    run_backup = transport.TransportTests.run_backup
    current = transport.TransportTests.current
    remote_path = transport.TransportTests.remote_path

    def attr(self, path, name, value=None):
        api = M['MacXattrs']()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            if value is not None:
                api.set(fd, name, value)
            return api.get(fd, name)
        finally:
            os.close(fd)

    def icon(self, folder=None):
        folder = folder or self.source
        icon = folder / M['FINDER_ICON']
        icon.write_bytes(b'synthetic icon data')
        self.attr(icon, 'com.apple.ResourceFork', b'synthetic icon resource fork v1')
        finder = bytearray(32)
        finder[8:10] = (0x0400).to_bytes(2, 'big')
        self.attr(folder, 'com.apple.FinderInfo', bytes(finder))
        return icon

    def icon_file(self, folder=None):
        return self.base / 'plain-store/MacBackup/plain/macos-icons/current' / str(folder or self.source).lstrip('/') / 'icon.json'

    def test_snapshot_and_restore_preserve_data_resource_fork_and_icon_flag(self):
        icon = self.icon()
        self.run_backup()
        destination = self.base / 'restored'
        destination.mkdir()
        result = self.cli('restore-icon', '--file', str(self.icon_file()), '--folder', str(destination), '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        restored = destination / M['FINDER_ICON']
        self.assertEqual(restored.read_bytes(), icon.read_bytes())
        self.assertEqual(self.attr(restored, 'com.apple.ResourceFork'), self.attr(icon, 'com.apple.ResourceFork'))
        self.assertEqual(self.attr(destination, 'com.apple.FinderInfo'), self.attr(self.source, 'com.apple.FinderInfo'))
        self.assertFalse(self.remote_path(icon).exists())
        self.assertNotIn(self.secret.read_text(), self.icon_file().read_text())

    def test_unchanged_icons_do_not_accumulate_history(self):
        self.icon()
        self.run_backup()
        original = self.icon_file().read_bytes()
        self.run_backup()
        self.assertEqual(original, self.icon_file().read_bytes())
        history = self.base / 'plain-store/MacBackup/plain/macos-icons/history'
        self.assertFalse(list(history.rglob('icon.json')))

    def test_verify_covers_icon_metadata_and_detects_changed_resource_fork(self):
        icon = self.icon()
        self.run_backup()
        matched = self.cli('verify', '--target', 'google', '--area', 'plain', '--json')
        self.assertEqual(matched.returncode, 0, matched.stdout + matched.stderr)
        by_kind = {item['kind']: item for item in json.loads(matched.stdout)['results']}
        self.assertEqual(by_kind['macos-icons']['matched'], 1)
        self.attr(icon, 'com.apple.ResourceFork', b'changed synthetic resource fork')
        changed = self.cli('verify', '--target', 'google', '--area', 'plain', '--json')
        self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
        by_kind = {item['kind']: item for item in json.loads(changed.stdout)['results']}
        self.assertEqual(len(by_kind['macos-icons']['different']), 1)

    def test_new_exclusion_archives_old_icon_snapshot(self):
        icon = self.icon()
        self.run_backup()
        original = self.icon_file().read_bytes()
        self.attr(icon, 'com.apple.ResourceFork', b'excluded icon v2')
        (self.config / 'exclude-paths.txt').write_text(str(self.source) + '\n')
        result = self.run_backup()
        self.assertFalse(self.icon_file().exists())
        history = self.base / 'plain-store/MacBackup/plain/macos-icons/history'
        self.assertEqual(next(history.rglob('icon.json')).read_bytes(), original)
        row = next(item for item in result['results'] if item['kind'] == 'macos-icons')
        self.assertEqual(row['archive_policy'], 1)
        self.assertEqual(row['policy_archived'][0]['reason'], 'Esclusione assoluta.')

    def test_deleted_icon_is_archived(self):
        icon = self.icon()
        self.run_backup()
        original = self.icon_file().read_bytes()
        icon.unlink()
        self.run_backup()
        self.assertFalse(self.icon_file().exists())
        history = self.base / 'plain-store/MacBackup/plain/macos-icons/history'
        self.assertEqual(next(history.rglob('icon.json')).read_bytes(), original)

    def test_changed_resource_fork_is_archived_even_with_same_file_size_and_time(self):
        icon = self.icon()
        self.run_backup()
        original = self.icon_file().read_bytes()
        timestamp = icon.stat().st_mtime_ns
        self.attr(icon, 'com.apple.ResourceFork', b'synthetic icon resource fork v2')
        os.utime(icon, ns=(timestamp, timestamp))
        self.run_backup()
        self.assertNotEqual(original, self.icon_file().read_bytes())
        history = self.base / 'plain-store/MacBackup/plain/macos-icons/history'
        self.assertEqual(next(history.rglob('icon.json')).read_bytes(), original)

    def test_private_icon_is_only_in_crypt_and_round_trips(self):
        folder = self.source / 'private-config'
        folder.mkdir()
        self.icon(folder)
        (self.config / 'private-paths.txt').write_text(str(folder) + '\n')
        self.run_backup()
        self.assertFalse(self.icon_file(folder).exists())
        relative = str(folder).lstrip('/') + '/icon.json'
        recovered = self.base / 'private-icon.json'
        subprocess.run(['rclone', 'copyto', 'localcrypt:macos-icons/current/' + relative, str(recovered)],
                       env=self.environment, capture_output=True, check=True)
        destination = self.base / 'recovered-private'
        destination.mkdir()
        M['restore_icon'](recovered, destination, False)
        self.assertEqual(self.attr(destination / M['FINDER_ICON'], 'com.apple.ResourceFork'), b'synthetic icon resource fork v1')
        self.run_backup()
        listing = subprocess.run(['rclone', 'lsf', 'localcrypt:macos-icons/history', '--recursive', '--files-only'],
                                 env=self.environment, capture_output=True, text=True)
        self.assertEqual(listing.stdout.strip(), '')

    def test_restore_refuses_existing_icon_and_preserves_other_folder_flags(self):
        self.icon()
        self.run_backup()
        destination = self.base / 'restore'
        destination.mkdir()
        target = destination / M['FINDER_ICON']
        target.write_bytes(b'previous icon')
        other = destination / 'document.txt'
        other.write_text('must remain unchanged')
        finder = bytearray(32)
        finder[8:10] = (0x4000).to_bytes(2, 'big')
        self.attr(destination, 'com.apple.FinderInfo', bytes(finder))
        with self.assertRaises(M['ConfigError']):
            M['restore_icon'](self.icon_file(), destination, False)
        self.assertEqual(target.read_bytes(), b'previous icon')
        M['restore_icon'](self.icon_file(), destination, True)
        flags = int.from_bytes(self.attr(destination, 'com.apple.FinderInfo')[8:10], 'big')
        self.assertEqual(flags, 0x4400)
        self.assertEqual(other.read_text(), 'must remain unchanged')

    def test_icon_deletion_respects_threshold_before_other_transfers(self):
        icon = self.icon()
        self.run_backup()
        icon.unlink()
        self.settings(limit=0)
        self.normal.write_text('must not upload')
        result = self.cli('run', '--target', 'google', '--json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('max_delete', result.stdout)
        self.assertEqual(self.remote_path(self.normal).read_text(), 'synthetic normal v1')
        self.assertTrue(self.icon_file().exists())

    def test_icon_symlink_is_not_followed(self):
        (self.source / M['FINDER_ICON']).symlink_to(self.secret)
        result = self.cli('check', '--json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('file regolare', result.stdout)

    def test_malformed_snapshot_does_not_write_destination(self):
        file = self.base / 'bad.json'
        file.write_text(json.dumps({'schema_version': 1, 'kind': 'macos-finder-icon', 'data_base64': 'AA==',
                                    'file_xattrs': ['com.apple.ResourceFork', 'com.apple.FinderInfo']}))
        with self.assertRaises(M['ConfigError']):
            M['restore_icon'](file, self.source, False)
        self.assertFalse((self.source / M['FINDER_ICON']).exists())

    def test_icon_capture_failure_records_partial_run(self):
        self.icon()
        policy = M['Policy'](self.config, self.home)
        args = argparse.Namespace(command='run', target='google', json=True)
        def fail(entry):
            raise M['ConfigError']('synthetic icon capture failure')
        with patch.dict(os.environ, self.environment, clear=True), patch.dict(M['perform_sync'].__globals__, {'icon_snapshot': fail}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M['transport_operation'](args, policy), 1)
        status = json.loads((self.home / '.local/state/macbackup/last-run.json').read_text())
        self.assertFalse(status['ok'])
        self.assertTrue(next(r for r in status['results'] if r['area'] == 'plain' and r['kind'] == 'files')['ok'])
        self.assertFalse(next(r for r in status['results'] if r['kind'] == 'macos-icons')['ok'])
