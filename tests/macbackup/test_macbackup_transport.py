"""Real rclone round trips against synthetic local and crypt remotes only."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / "home/.config/scripts/macbackup"
M = runpy.run_path(str(SCRIPT))


class VerifyProgressTests(unittest.TestCase):
    def test_verification_text_uses_original_safe_paths(self):
        self.assertEqual(M['verify_display_path']('Users/example/link.rclonelink', 'files'),
                         '/Users/example/link')
        self.assertEqual(M['verify_display_path']('Users/example/folder/icon.json', 'macos-icons'),
                         r'/Users/example/folder/Icon\r')
        self.assertEqual(M['verify_display_path']('Users/example/a\nb', 'files'),
                         r'/Users/example/a\nb')

    def test_inventory_counter_handles_chunks_nested_values_and_escaped_names(self):
        counter = M['JsonArrayObjectCounter']()
        for chunk in (b'[\n{"Path":"a\\\"}b","Meta":{"n":1}},\n{"Path":',
                      b'"second","Tags":[{"k":"v"}]}\n]'):
            counter.feed(chunk)
        self.assertEqual(counter.count, 2)

    def test_inventory_bar_shows_entries_read_without_a_known_total(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch.object(sys, 'stderr', terminal), patch.dict(os.environ, {
                'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                'NO_COLOR': '', 'PYTHON_COLORS': ''}):
            pulse = M['MountPulse']('Inventory google/plain/current', show_count='entries')
            pulse.completed = 42
            pulse.draw()
        self.assertIn('\x1b[2;90mEntries read 42\x1b[0m', terminal.getvalue())

    def test_completed_phase_keeps_the_final_count(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch.object(sys, 'stderr', terminal), patch.dict(os.environ, {
                'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                'NO_COLOR': '', 'PYTHON_COLORS': ''}):
            checked = M['MountPulse']('Verifying google/plain/files', 3)
            checked.completed = 3
            checked.done('completato')
            inventory = M['MountPulse']('Inventory google/plain/current', show_count='entries')
            inventory.completed = 42
            inventory.done('completato')
        output = terminal.getvalue()
        self.assertIn('(0s).  \x1b[2;90mChecked 3/3\x1b[0m', output)
        self.assertIn('(0s).  \x1b[2;90mEntries read 42\x1b[0m', output)

    def test_long_phase_durations_use_compact_hours_minutes_seconds(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch.object(sys, 'stderr', terminal), patch.object(M['time'], 'monotonic', return_value=6270):
            pulse = M['MountPulse']('Inventory google/plain/current', show_count='entries')
            pulse.started = 0
            pulse.draw()
            pulse.done('completato')
        output = terminal.getvalue()
        self.assertIn('1h44m30s', output)
        self.assertNotIn('6270s', output)
        self.assertEqual(M['progress_duration'](59), '59s')
        self.assertEqual(M['progress_duration'](150), '2m30s')
        self.assertEqual(M['progress_duration'](620), '10m20s')
        self.assertEqual(M['progress_duration'](60), '1m')
        self.assertEqual(M['progress_duration'](3605), '1h5s')
        self.assertEqual(M['progress_duration'](0), '0s')

    def test_size_only_verification_names_its_comparison_and_keeps_final_count(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'a.txt').write_bytes(b'abc')
            terminal = Terminal()
            with patch.object(sys, 'stderr', terminal), patch.dict(os.environ, {
                    'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                    'NO_COLOR': '', 'PYTHON_COLORS': ''}), \
                    patch.dict(M['verify_report'].__globals__, {
                        'mount_inventory': lambda *args, **kwargs: [
                            {'Path': 'a.txt', 'Size': 3}]}, clear=False):
                pulse = M['MountPulse']('Verifica google/plain/files', 1)
                result = M['verify_report'](str(source), 'synthetic:', ['a.txt'],
                                            source, False, False, True, pulse)
                pulse.done('completato')
            self.assertEqual(result['matched'], 1)
            self.assertIn('Comparing sizes google/plain/files', terminal.getvalue())
            self.assertIn('Checked 1/1', terminal.getvalue())

    def test_restore_and_apply_progress_use_their_own_units(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with tempfile.TemporaryFile() as downloaded:
            downloaded.write(b'12345')
            downloaded.flush()
            with patch.object(sys, 'stderr', terminal), patch.dict(os.environ, {
                    'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                    'NO_COLOR': '', 'PYTHON_COLORS': ''}):
                restore = M['MountPulse']('Restoring file')
                restore.byte_fd = downloaded.fileno()
                restore.byte_total = 10
                restore.draw()
                removed = M['MountPulse']('Removing copies', 2)
                removed.count_verb = 'removed'
                removed.completed = 1
                removed.draw()
                archived = M['MountPulse']('Archiving policy', 3)
                archived.count_verb = 'archived'
                archived.completed = 2
                archived.draw()
        self.assertIn('\x1b[2;90mReceived\x1b[0m 5 B / 10 B', terminal.getvalue())
        self.assertIn('Removed 1/2', terminal.getvalue())
        self.assertIn('Archived 2/3', terminal.getvalue())

    @unittest.skipUnless(shutil.which('rclone'), 'rclone is needed for inventory streaming')
    def test_inventory_can_update_a_shared_progress_bar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'one.txt').write_text('one')
            (root / 'two.txt').write_text('two')
            pulse = M['MountPulse']('Inventory', show_count='entries')
            pulse.matches = 0
            items = M['mount_inventory'](str(root), 'synthetic/current',
                                         activity=pulse)
            self.assertEqual(len(items), 2)
            self.assertEqual(pulse.completed, 2)
            self.assertEqual(pulse.label, 'Inventario synthetic/current')

    def test_remote_check_warning_uses_muted_path_style(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch.object(sys, 'stdout', terminal), patch.dict(os.environ, {
                'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                'NO_COLOR': '', 'PYTHON_COLORS': ''}):
            line = M['issue_line']('AVVISO:', '/tmp/link: collegamento; destinazione non attraversata.', 'warning')
        self.assertIn('\x1b[2m/tmp/link\x1b[0m', line)
        self.assertIn('\x1b[1;33mAVVISO:\x1b[0m', line)

    def test_local_scan_shows_a_running_path_count_without_an_unknown_total(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch.object(sys, 'stderr', terminal), patch.dict(os.environ, {
                'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                'NO_COLOR': '', 'PYTHON_COLORS': ''}):
            pulse = M['MountPulse']('Local scan', show_count=True)
            pulse.completed = 3
            pulse.draw()
        self.assertIn('\x1b[2;90mPaths checked 3\x1b[0m', terminal.getvalue())
        self.assertNotIn('Checked 3/3', terminal.getvalue())

    def test_report_progress_counts_only_complete_entries_without_double_counting(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'combined.txt'
            report.write_bytes(b'')
            terminal = Terminal()
            with patch.object(sys, 'stderr', terminal), patch.dict(os.environ, {
                    'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                    'NO_COLOR': '', 'PYTHON_COLORS': ''}):
                pulse = M['MountPulse']('Verifying synthetic/private/files', 2)
                pulse.report_path = report
                report.write_bytes(b'= first')
                pulse.draw()
                self.assertIn('\x1b[2;90mChecked 0/2\x1b[0m', terminal.getvalue())
                with report.open('ab') as stream:
                    stream.write(b'\n* second\n')
                pulse.draw()
                self.assertIn('Checked 2/2', terminal.getvalue())
                pulse.draw()
                self.assertEqual(pulse.completed, 2)
            plain = io.StringIO()
            with patch.object(sys, 'stderr', plain):
                self.assertEqual(M['terminal_style']('Checked 2/2', '2;90', plain), 'Checked 2/2')

    def test_preview_report_counts_only_selected_complete_paths(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'combined.txt'
            report.write_bytes(b'= first\n- remote-only\n+ second')
            terminal = Terminal()
            with patch.object(sys, 'stderr', terminal), patch.dict(os.environ, {
                    'MACBACKUP_LANG': 'en', 'TERM': 'xterm-256color',
                    'NO_COLOR': '', 'PYTHON_COLORS': ''}):
                pulse = M['MountPulse']('Preview synthetic/plain/files', 2)
                pulse.count_verb = 'processed'
                pulse.report_path = report
                pulse.report_expected = {'first', 'second'}
                pulse.draw()
                self.assertIn('Processed 1/2', terminal.getvalue())
                with report.open('ab') as stream:
                    stream.write(b'\n= first\n')
                pulse.draw()
                self.assertIn('Processed 2/2', terminal.getvalue())
                self.assertNotIn('Checked 2/2', terminal.getvalue())
                self.assertEqual(pulse.completed, 2)


@unittest.skipUnless(shutil.which("rclone"), "rclone is needed for local round trips")
class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        self.config = self.home / ".config/macbackup"
        M["init_config"](self.config, self.home)
        self.source = self.home / "Desktop/project"
        self.source.mkdir(parents=True)
        self.normal = self.source / "normal.txt"
        self.normal.write_text("synthetic normal v1")
        self.secret = self.source / ".env"
        self.secret.write_text("synthetic private v1")
        self.rclone_config = self.base / "rclone.conf"
        password = subprocess.run(["rclone", "obscure", "synthetic-test-password"], capture_output=True, text=True, check=True).stdout.strip()
        self.rclone_config.write_text(
            "[localplain]\ntype = alias\nremote = " + str(self.base / "plain-store")
            + "\n[localcrypt]\ntype = crypt\nremote = " + str(self.base / "crypt-store")
            + "\npassword = " + password + "\nfilename_encryption = standard\ndirectory_name_encryption = true\n"
        )
        self.rclone_config.chmod(0o600)
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith("RCLONE_")}
        self.environment.update(HOME=str(self.home), RCLONE_CONFIG=str(self.rclone_config))
        self.settings()
        self.rules()

    def settings(self, limit=25, private="localcrypt:", enabled=True):
        (self.config / "settings.toml").write_text(
            f'schema_version = 1\nmax_delete = {limit}\n[targets.google]\n'
            f'enabled = {str(enabled).lower()}\nplain = "localplain:MacBackup/plain"\nprivate = "{private}"\n'
            '[targets.proton]\nenabled = false\nplain = "notconfigured:MacBackup/plain"\nprivate = "notconfiguredcrypt:"\n'
        )

    def rules(self, private=False, exact_plain=False, excluded=False):
        (self.config / "plain-paths.txt").write_text(str(self.source) + "/\n" + (str(self.secret) + "\n" if exact_plain else ""))
        (self.config / "private-paths.txt").write_text(str(self.secret) + "\n" if private else "")
        (self.config / "exclude-paths.txt").write_text(str(self.normal) + "\n" if excluded else "")

    def cli(self, *args, extra_env=None):
        env = self.environment | (extra_env or {})
        return subprocess.run([sys.executable, str(SCRIPT), "--config-dir", str(self.config), *args], env=env, capture_output=True, text=True)

    def test_local_check_scan_updates_path_count(self):
        pulse = M['MountPulse']('Local scan', show_count=True)
        scan = M['scan_policy'](M['Policy'](self.config, self.home), pulse)
        self.assertFalse(scan.errors)
        self.assertGreater(pulse.completed, 0)
        self.assertEqual(pulse.completed, 3)  # project directory and its two files

    def run_backup(self):
        result = self.cli("run", "--target", "google", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    @property
    def current(self):
        return self.base / "plain-store/MacBackup/plain/current"

    def remote_path(self, file):
        return self.current / str(file).lstrip("/")

    def test_preview_never_creates_remote_files(self):
        result = self.cli("preview", "--target", "google", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.current.exists())
        self.assertIn('content differences not checked', json.loads(result.stdout)['note'])
        self.assertNotIn('Preview google/plain/files:', result.stderr)

    def test_preview_identifies_local_selection_absences_in_text_and_json(self):
        private = self.source / 'private-config'
        private.mkdir()
        private_file = private / 'settings.ini'
        private_file.write_text('synthetic private settings')
        (self.config / 'private-paths.txt').write_text(str(private) + '/\n')
        self.run_backup()
        self.normal.unlink()
        private_file.unlink()

        preview = self.cli('preview', '--target', 'google', '--json')
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        rows = {item['area']: item for item in json.loads(preview.stdout)['results']
                if item['kind'] == 'files'}
        self.assertEqual(rows['plain']['archive_deleted_paths'], [str(self.normal)])
        self.assertEqual(rows['private']['archive_deleted_paths'], [str(private_file)])
        self.assertEqual(rows['plain']['archive_deleted'], 1)
        self.assertEqual(rows['private']['archive_deleted'], 1)
        self.assertTrue(self.remote_path(self.normal).exists())

        readable = self.cli('preview', '--target', 'google')
        self.assertEqual(readable.returncode, 0, readable.stdout + readable.stderr)
        self.assertIn('to archive because absent from local selection 1', readable.stdout)
        self.assertIn('Absent from local selection: ' + str(self.normal), readable.stdout)
        self.assertIn('Absent from local selection: ' + str(private_file), readable.stdout)

    def test_run_status_keeps_planned_absences_and_partial_phase_state(self):
        self.run_backup()
        self.normal.unlink()
        observed = []

        def interrupted_sync(*args, **kwargs):
            observed.append(json.loads((self.home / '.local/state/macbackup/last-run.json').read_text()))
            raise KeyboardInterrupt

        args = argparse.Namespace(command='run', target='google', json=True, progress_depth=2)
        with patch.dict(os.environ, self.environment), \
                patch.dict(M['transport_operation'].__globals__, {'perform_sync': interrupted_sync}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M['transport_operation'](args, M['Policy'](self.config, self.home)), 1)
        self.assertEqual(observed[0]['active_phase'], 'google/plain/files')
        self.assertFalse(observed[0]['complete'])
        self.assertEqual(observed[0]['results'][0]['archive_deleted_paths'], [str(self.normal)])
        saved = json.loads((self.home / '.local/state/macbackup/last-run.json').read_text())
        self.assertTrue(saved['interrupted'])
        self.assertFalse(saved['complete'])
        self.assertEqual(saved['active_phase'], 'google/plain/files')
        self.assertEqual(saved['results'][0]['archive_deleted_paths'], [str(self.normal)])
        self.assertEqual(saved['results'][0]['archive_deleted_completed_paths'], [])

    def test_interrupted_run_confirms_only_copies_found_in_its_history(self):
        other = self.source / 'other.txt'
        other.write_text('another synthetic file')
        self.run_backup()
        self.normal.unlink()
        other.unlink()

        def partly_archived(plan, state, run_id, *args):
            original = self.remote_path(self.normal)
            history = self.base / 'plain-store/MacBackup/plain/history' / run_id / str(self.normal).lstrip('/')
            history.parent.mkdir(parents=True)
            original.rename(history)
            (history.parent / 'previous-version.txt').write_text('unrelated history item')
            raise KeyboardInterrupt

        args = argparse.Namespace(command='run', target='google', json=True, progress_depth=2)
        with patch.dict(os.environ, self.environment), \
                patch.dict(M['transport_operation'].__globals__, {'perform_sync': partly_archived}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M['transport_operation'](args, M['Policy'](self.config, self.home)), 1)
        saved = json.loads((self.home / '.local/state/macbackup/last-run.json').read_text())
        row = saved['results'][0]
        self.assertCountEqual(row['archive_deleted_paths'], [str(self.normal), str(other)])
        self.assertEqual(row['archive_deleted_completed_paths'], [str(self.normal)])
        self.assertTrue(self.remote_path(other).exists())

    def test_unreadable_history_does_not_report_zero_completed_archives(self):
        plan = {'target': 'google', 'area': 'plain', 'root': 'localplain:MacBackup/plain',
                'deletions': ['Users/example/a.txt']}
        with patch.dict(M['completed_deleted_archive_paths'].__globals__, {
                'remote_current_objects': lambda *args: (_ for _ in ()).throw(M['TransportError']('offline'))}):
            self.assertIsNone(M['completed_deleted_archive_paths'](plan, 'synthetic-run'))

    def test_completed_archive_paths_are_read_through_crypt_remote(self):
        self.rules(private=True)
        self.run_backup()
        relative = str(self.secret).lstrip('/')
        with patch.dict(os.environ, self.environment):
            M['rclone_call']('moveto', 'localcrypt:current/' + relative,
                             'localcrypt:history/synthetic-run/' + relative)
            completed = M['completed_deleted_archive_paths']({
                'target': 'google', 'area': 'private', 'root': 'localcrypt:',
                'deletions': [relative], 'kind': 'files'}, 'synthetic-run')
        self.assertEqual(completed, [str(self.secret)])

    def test_successful_run_status_keeps_archive_paths(self):
        self.run_backup()
        self.normal.unlink()
        readable = self.cli('run', '--target', 'google')
        self.assertEqual(readable.returncode, 0, readable.stdout + readable.stderr)
        self.assertIn('Absent from local selection: ' + str(self.normal), readable.stdout)
        self.assertIn('Archived for absence from local selection: 1/1.', readable.stdout)
        saved = self.cli('status')
        self.assertEqual(json.loads(saved.stdout)['results'][0]['archive_deleted_paths'], [str(self.normal)])
        self.assertEqual(json.loads(saved.stdout)['results'][0]['archive_deleted_completed_paths'], [str(self.normal)])
        self.assertEqual((self.home / '.local/state/macbackup/last-run.json').stat().st_mode & 0o777, 0o600)

    def test_run_status_exposes_completed_phase_while_next_phase_is_active(self):
        self.rules(private=True)
        real_sync = M['perform_sync']
        observed = []

        def stop_in_second_phase(*args, **kwargs):
            if observed:
                observed.append(json.loads((self.home / '.local/state/macbackup/last-run.json').read_text()))
                raise KeyboardInterrupt
            observed.append(None)
            return real_sync(*args, **kwargs)

        args = argparse.Namespace(command='run', target='google', json=True, progress_depth=2)
        with patch.dict(os.environ, self.environment), \
                patch.dict(M['transport_operation'].__globals__, {'perform_sync': stop_in_second_phase}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M['transport_operation'](args, M['Policy'](self.config, self.home)), 1)
        active = observed[1]
        self.assertTrue(active['results'][0]['ok'])
        self.assertFalse(active['results'][0].get('in_progress', False))
        self.assertTrue(active['results'][1]['in_progress'])
        self.assertEqual(active['active_phase'], 'google/private/files')

    def test_preview_uses_original_symlink_path_and_keeps_policy_archives_separate(self):
        link = self.source / 'normal-link'
        link.symlink_to('normal.txt')
        self.run_backup()
        link.unlink()
        self.rules(excluded=True)

        preview = self.cli('preview', '--target', 'google', '--json')
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        row = next(item for item in json.loads(preview.stdout)['results']
                   if item['area'] == 'plain' and item['kind'] == 'files')
        self.assertEqual(row['archive_deleted_paths'], [str(link)])
        self.assertEqual(row['archive_policy'], 1)
        self.assertEqual(row['policy_archives'][0]['path'], str(self.normal))
        self.assertNotIn('.rclonelink', json.dumps(row['archive_deleted_paths']))

    def test_simulated_preview_retains_transfer_dry_run(self):
        result = self.cli('preview', '--target', 'google', '--simulate', '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.current.exists())
        self.assertIn('Preview google/plain/files: in progress...', result.stderr)
        self.assertIn('Preview google/plain/files: complete', result.stderr)
        self.assertIn('Processed ', result.stderr)

    def test_simulation_requires_remote_target(self):
        result = self.cli('preview', '--local', '--simulate')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('preview --simulate requires --target', result.stderr)

    def test_preview_reports_private_comparison_progress_without_changing_cloud(self):
        self.rules(private=True)
        self.run_backup()
        result = self.cli('preview', '--target', 'google', '--simulate', '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Comparing private google/private/files: in progress...', result.stderr)
        self.assertIn('Comparing private google/private/files: complete', result.stderr)
        self.assertEqual(self.secret.read_text(), 'synthetic private v1')

    def test_backup_excludes_env_and_keeps_absolute_path_structure(self):
        self.run_backup()
        self.assertEqual(self.remote_path(self.normal).read_bytes(), self.normal.read_bytes())
        self.assertFalse(self.remote_path(self.secret).exists())

    def test_remote_check_allows_shared_directories_with_distinct_files(self):
        self.rules(private=True)
        self.run_backup()
        result = self.cli('check', '--remote', '--target', 'google', '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertIn('warnings', json.loads(result.stdout))

    def test_remote_check_formats_warnings_and_reports_local_selection(self):
        link = self.source / 'link.txt'
        link.symlink_to(self.normal)
        result = self.cli('check', '--remote', '--target', 'google')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f'WARNING: {link}: symlink; target not traversed.', result.stdout)
        self.assertIn('Plain: 2; private: 0; skipped:', result.stdout)
        self.assertIn('selected size:', result.stdout)
        self.assertIn('Inventory google/plain/current: in progress...', result.stderr)
        self.assertIn('Inventory google/plain/current:', result.stderr)
        self.assertIn('entries read', result.stderr)
        structured = self.cli('check', '--remote', '--target', 'google', '--json')
        self.assertEqual(structured.returncode, 0, structured.stdout + structured.stderr)
        self.assertEqual(json.loads(structured.stdout)['summary']['plain'], 2)

    def test_remote_check_rejects_same_file_in_plain_and_private(self):
        self.run_backup()
        private = 'localcrypt:current/' + str(self.normal).lstrip('/')
        subprocess.run(['rclone', 'copyto', str(self.normal), private],
                       env=self.environment, check=True, capture_output=True)
        result = self.cli('check', '--remote', '--target', 'google')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.normal), result.stderr)
        self.assertIn('conflicting between plain and private', result.stderr)
        self.assertTrue(self.remote_path(self.normal).exists())

    def test_remote_check_rejects_file_at_private_directory_path(self):
        self.run_backup()
        private_child = 'localcrypt:current/' + str(self.normal).lstrip('/') + '/child.txt'
        subprocess.run(['rclone', 'copyto', str(self.secret), private_child],
                       env=self.environment, check=True, capture_output=True)
        result = self.cli('check', '--remote', '--target', 'google')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.normal), result.stderr)

    def test_local_check_uses_decimal_units_in_human_output(self):
        with self.normal.open('wb') as stream:
            stream.truncate(1_234_567_890)
        result = self.cli('check')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1.2 GB', result.stdout)
        result_json = self.cli('check', '--json')
        self.assertEqual(result_json.returncode, 0, result_json.stdout + result_json.stderr)
        self.assertGreaterEqual(json.loads(result_json.stdout)['summary']['selected_bytes'],
                                1_234_567_890)

    def test_run_shows_byte_progress_without_corrupting_json_output(self):
        result = self.cli('run', '--target', 'google', '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['ok'])
        plain = next(item for item in data['results'] if item['area'] == 'plain' and item['kind'] == 'files')
        self.assertEqual(plain['selected'], 1)
        self.assertEqual(plain['transferred_files'], 1)
        self.assertEqual(plain['transferred_bytes'], self.normal.stat().st_size)
        self.assertTrue(plain['counts_complete'])
        self.assertEqual(plain['server_side_moves'], 0)
        self.assertIn('Data       [', result.stderr)
        self.assertIn('SPEED', result.stderr)
        self.assertIn('Starting google/plain/files:', result.stderr)

    def test_real_interrupted_progress_retains_latest_stats(self):
        large = self.source / 'large.bin'
        large.write_bytes(b'x' * 2_000_000)
        destination = self.base / 'slow-store'
        destination.mkdir()
        helper = '''
import json, pathlib, runpy, sys
module = runpy.run_path(sys.argv[1])
try:
    module['rclone_progress_call']([
        'sync', sys.argv[2], sys.argv[3], '--stats', '1s',
        '--stats-log-level', 'NOTICE', '--use-json-log',
        '--bwlimit', '100k', '--disable', 'copy'], pathlib.Path(sys.argv[2]), 2)
except module['TransferInterrupted'] as exc:
    print(json.dumps(module['transfer_metrics'](exc.stats, False)))
'''
        process = subprocess.Popen(
            [sys.executable, '-c', helper, str(SCRIPT), str(self.source), str(destination)],
            env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            import time
            time.sleep(2.5)
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(process.returncode, 0, stderr)
        metrics = json.loads(stdout)
        self.assertIsInstance(metrics['transferred_bytes'], int)
        self.assertGreater(metrics['transferred_bytes'], 0)
        self.assertFalse(metrics['counts_complete'])
        self.assertIn('Data       [', stderr)
        self.assertIn('Elapsed 2s', stderr)

    def test_run_text_summary_distinguishes_selected_and_transferred(self):
        result = self.cli('run', '--target', 'google')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('selected 1', result.stdout)
        self.assertIn('Transferred 1 file, 19 B', result.stdout)

    def test_active_directory_groups_at_requested_home_depth(self):
        stats = {'transferring': [
            {'name': str(self.home).lstrip('/') + '/Desktop/project/a.txt'},
            {'name': str(self.home).lstrip('/') + '/Desktop/project/sub/b.txt'},
            {'name': str(self.home).lstrip('/') + '/Documents/report.txt'},
        ]}
        self.assertEqual(M['active_directories'](stats, self.home, 2),
                         ['~/Desktop/project', '~/Documents'])

    def test_progress_screen_units_legend_bars_and_whole_seconds(self):
        stats = {'bytes': 1_048_576, 'totalBytes': 2_097_152,
                 'transfers': 1, 'totalTransfers': 2, 'speed': 1_048_576,
                 'elapsedTime': 65.9, 'eta': 61.7, 'checks': 3,
                 'totalChecks': 4, 'listed': 6, 'renames': 1,
                 'serverSideMoves': 1, 'serverSideMoveBytes': 1024,
                 'transferring': [{'name': str(self.normal).lstrip('/'),
                                  'bytes': 1024, 'size': 2048, 'speed': 512}]}
        display = M['ProgressDisplay'](self.home, 2, 'google/plain/files')
        display.stats = stats
        binary = '\n'.join(M['progress_lines'](stats, self.home, 2, True, False,
                                              display.label))
        self.assertIn('Tempo 1m5s', binary)
        self.assertIn('1.0 MiB / 2.0 MiB', binary)
        self.assertIn('VELOCITÀ  1.0 MiB/s', binary)
        self.assertIn('[#################------------------]', binary)
        self.assertIn(str(self.normal).lstrip('/'), binary)
        self.assertNotIn('65.9', binary)
        display.key(b'u')
        display.key(b'?')
        decimal = '\n'.join(M['progress_lines'](stats, self.home, 2,
                                               display.binary, display.legend, display.label))
        self.assertIn('1.0 MB / 2.1 MB', decimal)
        self.assertIn('VELOCITÀ  1.0 MB/s', decimal)
        self.assertIn('Spostati sul cloud:', decimal)
        self.assertIn('[?] Nascondi legenda', decimal)
        self.assertIn('Unità attuali: decimale', decimal)
        self.assertIn('Legenda (solo fase corrente:', decimal)
        self.assertIn('Tempo stimato: previsione variabile', decimal)

    def test_incomplete_remote_copy_is_replaced_on_next_run(self):
        incomplete = self.remote_path(self.normal)
        incomplete.parent.mkdir(parents=True)
        incomplete.write_text('partial')
        self.run_backup()
        self.assertEqual(incomplete.read_bytes(), self.normal.read_bytes())

    def test_interrupted_transfer_records_partial_status(self):
        script_globals = M['transport_operation'].__globals__
        original = script_globals['perform_sync']
        def interrupted(*_args, **_kwargs):
            raise M['TransferInterrupted']({'transfers': 3, 'bytes': 100, 'checks': 2,
                                            'listed': 7, 'renames': 2,
                                            'serverSideMoves': 2, 'serverSideMoveBytes': 48})
        script_globals['perform_sync'] = interrupted
        try:
            with patch.dict(os.environ, self.environment, clear=True):
                args = argparse.Namespace(command='run', target='google', json=True)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = M['transport_operation'](args, M['Policy'](self.config, self.home))
            self.assertEqual(code, 1)
            result = json.loads(output.getvalue())
            self.assertFalse(result['ok'])
            self.assertEqual(result['results'][0]['transferred_files'], 3)
            self.assertEqual(result['results'][0]['transferred_bytes'], 100)
            self.assertEqual(result['results'][0]['server_side_moves'], 2)
            self.assertEqual(result['results'][0]['server_side_move_bytes'], 48)
            self.assertEqual(result['results'][0]['renamed_files'], 2)
            self.assertFalse(result['results'][0]['counts_complete'])
            state = self.home / '.local/state/macbackup/last-run.json'
            self.assertIn('Interrupted', state.read_text())
            self.assertNotIn('\\u2019', state.read_text())
            status = self.cli('status')
            self.assertIn('by user', status.stdout)
            self.assertIn('already', status.stdout)
            self.assertNotIn('\\u00e0', status.stdout)
        finally:
            script_globals['perform_sync'] = original

    def test_private_round_trip_and_explicit_revocation_archive_old_copy(self):
        self.rules(private=True)
        self.run_backup()
        self.assertFalse(self.remote_path(self.secret).exists())
        restored = self.base / "restored.env"
        source = "localcrypt:current/" + str(self.secret).lstrip("/")
        command = ["rclone", "copyto", source, str(restored)]
        subprocess.run(command, env=self.environment, capture_output=True, check=True)
        self.assertEqual(restored.read_text(), "synthetic private v1")
        self.secret.write_text("synthetic private v2")
        self.rules(private=False)
        self.run_backup()
        history = subprocess.run(['rclone', 'lsf', 'localcrypt:history', '--recursive', '--files-only'],
                                 env=self.environment, capture_output=True, text=True, check=True)
        old = next(name for name in history.stdout.splitlines() if name.endswith('/.env'))
        result = subprocess.run(['rclone', 'cat', 'localcrypt:history/' + old],
                                env=self.environment, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, 'synthetic private v1')

    def test_private_same_size_same_mtime_change_is_saved_and_archived(self):
        self.rules(private=True)
        self.run_backup()
        timestamp = self.secret.stat().st_mtime_ns
        self.secret.write_text("synthetic private v2")
        os.utime(self.secret, ns=(timestamp, timestamp))
        self.run_backup()
        source = "localcrypt:current/" + str(self.secret).lstrip("/")
        result = subprocess.run(["rclone", "cat", source], env=self.environment, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "synthetic private v2")
        history = subprocess.run(["rclone", "lsf", "localcrypt:history", "--recursive", "--files-only"], env=self.environment, capture_output=True, text=True, check=True).stdout.splitlines()
        previous = next(name for name in history if name.endswith("/.env"))
        old = subprocess.run(["rclone", "cat", "localcrypt:history/" + previous], env=self.environment, capture_output=True, text=True, check=True)
        self.assertEqual(old.stdout, "synthetic private v1")

    def test_unchanged_private_file_does_not_create_new_history(self):
        self.rules(private=True)
        self.run_backup()
        self.run_backup()
        result = subprocess.run(["rclone", "lsf", "localcrypt:history", "--recursive", "--files-only"], env=self.environment, capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 3))
        self.assertEqual(result.stdout.strip(), "")

    def test_replacements_and_source_deletions_are_archived(self):
        removed = self.source / "removed.txt"
        removed.write_text("synthetic removed")
        self.run_backup()
        removed.unlink()
        self.normal.write_text("synthetic normal v2")
        self.run_backup()
        history = self.base / "plain-store/MacBackup/plain/history"
        self.assertEqual(next(history.rglob("normal.txt")).read_text(), "synthetic normal v1")
        self.assertEqual(next(history.rglob("removed.txt")).read_text(), "synthetic removed")
        self.assertFalse(self.remote_path(removed).exists())

    def test_private_file_deleted_inside_selected_directory_is_archived(self):
        directory = self.source / "private-config"
        directory.mkdir()
        file = directory / "settings.ini"
        file.write_text("synthetic private settings")
        (self.config / "private-paths.txt").write_text(str(directory) + "/\n")
        self.run_backup()
        file.unlink()
        self.run_backup()
        history = subprocess.run(["rclone", "lsf", "localcrypt:history", "--recursive", "--files-only"], env=self.environment, capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertTrue(any(name.endswith("/settings.ini") for name in history))

    def test_plain_same_size_same_mtime_change_is_saved(self):
        self.run_backup()
        timestamp = self.normal.stat().st_mtime_ns
        self.normal.write_text("synthetic normal v2")
        os.utime(self.normal, ns=(timestamp, timestamp))
        self.run_backup()
        self.assertEqual(self.remote_path(self.normal).read_text(), "synthetic normal v2")

    def test_new_exclusion_archives_existing_copy_with_reason(self):
        self.run_backup()
        self.normal.write_text("changed but excluded")
        self.rules(excluded=True)
        preview = self.cli('preview', '--target', 'google', '--json')
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        planned = next(row for row in json.loads(preview.stdout)['results']
                       if row['area'] == 'plain' and row['kind'] == 'files')
        self.assertEqual(planned['archive_policy'], 1)
        self.assertEqual(planned['policy_archives'][0]['reason'], 'Absolute exclusion.')
        self.assertTrue(self.remote_path(self.normal).exists())
        result = self.run_backup()
        self.assertFalse(self.remote_path(self.normal).exists())
        self.assertEqual(next((self.base / 'plain-store/MacBackup/plain/history').rglob('normal.txt')).read_text(),
                         'synthetic normal v1')
        self.assertEqual(result['results'][0]['policy_archived'][0]['reason'], 'Absolute exclusion.')
        self.rules(excluded=False)
        self.run_backup()
        self.assertEqual(self.remote_path(self.normal).read_text(), 'changed but excluded')

    def test_new_directory_name_pattern_archives_old_cloud_copy(self):
        old = self.source / "node_modules/package.txt"
        old.parent.mkdir()
        old.write_text("synthetic dependency v1")
        self.run_backup()
        self.assertEqual(self.remote_path(old).read_text(), "synthetic dependency v1")
        old.write_text("synthetic dependency v2")
        (self.config / "explicit-only-patterns.txt").write_text(".env\n.env.*\nnode_modules/\n")
        result = self.run_backup()
        self.assertFalse(self.remote_path(old).exists())
        self.assertFalse(any(item["archive_deleted"] for item in result["results"]))
        history = self.base / "plain-store/MacBackup/plain/history"
        self.assertEqual(next(history.rglob('package.txt')).read_text(), 'synthetic dependency v1')
        self.assertEqual(result['results'][0]['archive_policy'], 1)

    def test_git_history_routes_to_crypt_and_archives_old_plain_copy(self):
        object_file = self.source / '.git/objects/ab/cdef'
        object_file.parent.mkdir(parents=True)
        object_file.write_text('synthetic git object')
        env_file = self.source / '.git/.env'
        env_file.write_text('synthetic forbidden env')
        self.run_backup()
        self.assertTrue(self.remote_path(object_file).exists())
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'max_delete = 25\n', 'max_delete = 25\n[policy]\nprivate_directory_names = [".git"]\n'))
        (self.config / 'explicit-only-patterns.txt').write_text('.env\n.env.*\n.git\n')
        result = self.run_backup()
        self.assertFalse(any(item['archive_deleted'] for item in result['results']))
        self.assertFalse(self.remote_path(object_file).exists())
        self.assertEqual(next((self.base / 'plain-store/MacBackup/plain/history').rglob('cdef')).read_text(),
                         'synthetic git object')
        encrypted = 'localcrypt:current/' + str(object_file).lstrip('/')
        restored = subprocess.run(['rclone', 'cat', encrypted], env=self.environment,
                                  capture_output=True, text=True, check=True)
        self.assertEqual(restored.stdout, 'synthetic git object')
        forbidden = subprocess.run(['rclone', 'lsf', 'localcrypt:current/' +
                                    str(env_file.parent).lstrip('/')], env=self.environment,
                                   capture_output=True, text=True)
        self.assertNotIn('.env', forbidden.stdout.splitlines())

    def test_versions_groups_history_of_crypt_git_directory(self):
        git_dir = self.source / '.git'
        object_file = git_dir / 'objects/ab/cdef'
        object_file.parent.mkdir(parents=True)
        object_file.write_text('synthetic git object v1')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'max_delete = 25\n', 'max_delete = 25\n[policy]\nprivate_directory_names = [".git"]\n'))
        (self.config / 'explicit-only-patterns.txt').write_text('.env\n.env.*\n.git\n')
        self.run_backup()
        object_file.write_text('synthetic git object v2')
        self.run_backup()
        listing = self.cli('versions', str(git_dir), '--target', 'google',
                           '--area', 'private', '--json')
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        groups = json.loads(listing.stdout)['versions']
        self.assertEqual(len(groups), 2)
        self.assertEqual(len([group for group in groups if group['version'] != 'current']), 1)
        self.assertTrue(all(group['area'] == 'private' for group in groups))
        self.assertTrue(all(group['count'] == 1 for group in groups))
        self.assertEqual({item['path'] for group in groups for item in group['items']},
                         {str(object_file)})

    def test_exact_plain_git_directory_archives_old_private_copy(self):
        git_dir = self.source / '.git'
        object_file = git_dir / 'objects/ab/cdef'
        object_file.parent.mkdir(parents=True)
        object_file.write_text('synthetic git object')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'max_delete = 25\n', 'max_delete = 25\n[policy]\nprivate_directory_names = [".git"]\n'))
        (self.config / 'explicit-only-patterns.txt').write_text('.env\n.env.*\n.git\n')
        self.run_backup()
        self.assertFalse(self.remote_path(object_file).exists())
        (self.config / 'plain-paths.txt').write_text(str(self.source) + '/\n' + str(git_dir) + '/\n')
        result = self.run_backup()
        self.assertEqual(self.remote_path(object_file).read_text(), 'synthetic git object')
        private_result = next(item for item in result['results']
                              if item['area'] == 'private' and item['kind'] == 'files')
        self.assertEqual(private_result['archive_policy'], 1)
        old = subprocess.run(['rclone', 'lsf', 'localcrypt:history', '--recursive', '--files-only'],
                             env=self.environment, capture_output=True, text=True, check=True)
        self.assertTrue(any(name.endswith('/.git/objects/ab/cdef') for name in old.stdout.splitlines()))

    def test_new_ignored_file_rule_archives_old_cloud_copy(self):
        old = self.source / '.DS_Store'
        old.write_text('synthetic finder metadata')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'max_delete = 25\n', 'max_delete = 25\n[policy]\nignored_file_names = []\n'))
        self.run_backup()
        self.assertTrue(self.remote_path(old).exists())
        settings.write_text(settings.read_text().replace(
            'ignored_file_names = []', 'ignored_file_names = [".DS_Store"]'))
        result = self.run_backup()
        self.assertFalse(any(item['archive_deleted'] for item in result['results']))
        self.assertFalse(self.remote_path(old).exists())
        self.assertEqual(next((self.base / 'plain-store/MacBackup/plain/history').rglob('.DS_Store')).read_text(),
                         'synthetic finder metadata')

    def test_exact_inclusion_overrides_ignored_file_name(self):
        ignored = self.source / '.DS_Store'
        ignored.write_text('synthetic metadata')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'max_delete = 25\n', 'max_delete = 25\n[policy]\nignored_file_names = [".DS_Store"]\n'))
        self.run_backup()
        self.assertFalse(self.remote_path(ignored).exists())
        (self.config / 'plain-paths.txt').write_text(str(self.source) + '/\n' + str(ignored) + '\n')
        self.run_backup()
        self.assertEqual(self.remote_path(ignored).read_text(), 'synthetic metadata')
        (self.config / 'plain-paths.txt').write_text(str(self.source) + '/\n')
        (self.config / 'private-paths.txt').write_text(str(ignored) + '\n')
        result = self.run_backup()
        self.assertFalse(self.remote_path(ignored).exists())
        old_plain = self.base / 'plain-store/MacBackup/plain/history'
        self.assertEqual(next(old_plain.rglob('.DS_Store')).read_text(), 'synthetic metadata')
        private_file = subprocess.run(['rclone', 'cat', 'localcrypt:current/' + str(ignored).lstrip('/')],
                                      env=self.environment, capture_output=True, text=True, check=True)
        self.assertEqual(private_file.stdout, 'synthetic metadata')
        self.assertEqual(next(row for row in result['results']
                              if row['area'] == 'plain' and row['kind'] == 'files')['archive_policy'], 1)

    @unittest.skipUnless(shutil.which('git'), 'Git is needed for .gitignore matching')
    def test_new_gitignore_rule_archives_old_cloud_copy(self):
        old = self.source / 'generated.log'
        old.write_text('synthetic generated v1')
        self.run_backup()
        self.assertTrue(self.remote_path(old).exists())
        old.write_text('synthetic generated v2')
        (self.source / '.gitignore').write_text('*.log\n')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'max_delete = 25\n', 'max_delete = 25\n[policy]\nuse_gitignore = true\n'))
        result = self.run_backup()
        self.assertFalse(any(item['archive_deleted'] for item in result['results']))
        self.assertFalse(self.remote_path(old).exists())
        self.assertEqual(next((self.base / 'plain-store/MacBackup/plain/history').rglob('generated.log')).read_text(),
                         'synthetic generated v1')
        self.assertEqual(result['results'][0]['policy_archived'][0]['rule'],
                         str(self.source / '.gitignore') + ':1:*.log')
        self.assertTrue(self.remote_path(self.source / '.gitignore').exists())

    def test_verify_reports_match_and_changed_local_file_without_calling_it_corruption(self):
        self.run_backup()
        matched = self.cli('verify', '--target', 'google', '--area', 'plain', '--json')
        self.assertEqual(matched.returncode, 0, matched.stdout + matched.stderr)
        data = json.loads(matched.stdout)
        self.assertTrue(data['ok'])
        self.assertEqual(data['results'][0]['matched'], 1)
        self.normal.write_text('changed local content')
        changed = self.cli('verify', '--target', 'google', '--area', 'plain', '--json')
        self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
        data = json.loads(changed.stdout)
        self.assertEqual(len(data['results'][0]['different']), 1)
        self.assertIn('does not prove corruption', data['note'])
        readable = self.cli('verify', '--target', 'google', '--area', 'plain')
        self.assertIn('Different: ' + str(self.normal), readable.stdout)
        saved = self.cli('status', '--verify')
        self.assertEqual(json.loads(saved.stdout)['results'][0]['different'], [str(self.normal).lstrip('/')])
        report = self.home / '.local/state/macbackup/last-verify.json'
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)

    def test_verify_before_first_backup_reports_missing_copy(self):
        checked = self.cli('verify', '--target', 'google', '--area', 'plain', '--json')
        self.assertEqual(checked.returncode, 1)
        data = json.loads(checked.stdout)
        self.assertEqual(len(data['results'][0]['missing']), 1)
        readable = self.cli('verify', '--target', 'google', '--area', 'plain')
        self.assertIn('Missing: ' + str(self.normal), readable.stdout)

    def test_interrupted_verify_saves_only_completed_phases(self):
        self.rules(private=True)
        calls = []

        def interrupted_report(*args, **kwargs):
            calls.append(args)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return {'selected': len(args[2]), 'matched': len(args[2]),
                    'different': [], 'missing': [], 'errors': []}

        args = argparse.Namespace(target='google', area='all', download=False,
                                  size_only=False, json=True)
        with patch.dict(os.environ, self.environment), \
                patch.dict(M['verify_operation'].__globals__, {'verify_report': interrupted_report}):
            with self.assertRaises(KeyboardInterrupt):
                M['verify_operation'](args, self.config, self.home)
        saved = json.loads((self.home / '.local/state/macbackup/last-verify.json').read_text())
        self.assertFalse(saved['complete'])
        self.assertTrue(saved['interrupted'])
        self.assertEqual(saved['active_phase'], 'google/private/files')
        self.assertEqual(len(saved['results']), 1)
        self.assertEqual(saved['results'][0]['area'], 'plain')

    def test_verify_private_crypt_and_download_mode(self):
        self.rules(private=True)
        self.run_backup()
        for args in ((), ('--download',)):
            with self.subTest(args=args):
                checked = self.cli('verify', '--target', 'google', '--area', 'private',
                                   *args, '--json')
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                data = json.loads(checked.stdout)
                self.assertEqual(data['results'][0]['matched'], 1)

    def test_verify_size_only_reports_its_weaker_method(self):
        self.rules(private=True)
        self.run_backup()
        self.secret.write_text('synthetic private v2')
        quick = self.cli('verify', '--target', 'google', '--area', 'private',
                         '--size-only', '--json')
        self.assertEqual(quick.returncode, 0, quick.stdout + quick.stderr)
        data = json.loads(quick.stdout)
        self.assertEqual(data['results'][0]['method'], 'size-only')
        self.assertEqual(data['results'][0]['matched'], 1)
        full = self.cli('verify', '--target', 'google', '--area', 'private', '--json')
        self.assertEqual(full.returncode, 1, full.stdout + full.stderr)
        self.assertEqual(len(json.loads(full.stdout)['results'][0]['different']), 1)

    def test_verify_size_only_handles_selected_symlink(self):
        (self.source / 'normal-link').symlink_to('normal.txt')
        self.run_backup()
        checked = self.cli('verify', '--target', 'google', '--area', 'plain',
                           '--size-only', '--json')
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(json.loads(checked.stdout)['results'][0]['matched'], 2)

    def test_ctrl_c_at_command_boundary_has_no_traceback(self):
        with patch.dict(M['main'].__globals__, {'verify_operation': lambda *args: (_ for _ in ()).throw(KeyboardInterrupt)}):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                result = M['main'](['--config-dir', str(self.config), 'verify', '--target', 'google'])
        self.assertEqual(result, 130)
        self.assertIn('Interrupted', stderr.getvalue())
        self.assertNotIn('Traceback', stderr.getvalue())

    def test_deletion_threshold_stops_before_any_transfer(self):
        self.run_backup()
        self.normal.unlink()
        self.settings(limit=0)
        result = self.cli("run", "--target", "google", "--json")
        self.assertNotEqual(result.returncode, 0)
        status = json.loads(self.cli('status').stdout)
        self.assertFalse(status['complete'])
        self.assertEqual(status['active_phase'], 'planning')
        self.assertIn('max_delete', status['error'])
        self.assertTrue(self.remote_path(self.normal).exists())
        self.assertIn("max_delete", result.stdout)

    def test_policy_archive_limit_blocks_run_but_preview_shows_plan(self):
        extra = self.source / 'extra.txt'
        extra.write_text('synthetic extra')
        self.run_backup()
        (self.config / 'exclude-paths.txt').write_text(str(self.source.parent) + '/\n')
        self.settings(limit=1)
        preview = self.cli('preview', '--target', 'google', '--json')
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        row = next(item for item in json.loads(preview.stdout)['results']
                   if item['area'] == 'plain' and item['kind'] == 'files')
        self.assertEqual(row['archive_policy'], 2)
        self.assertTrue(row['archive_limit_exceeded'])
        self.assertTrue(self.remote_path(extra).exists())
        run = self.cli('run', '--target', 'google', '--json')
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('max_delete', run.stdout)
        self.assertTrue(self.remote_path(extra).exists())
        self.assertTrue(self.remote_path(self.normal).exists())
        self.assertFalse((self.base / 'plain-store/MacBackup/plain/history').exists())

    def test_removed_inclusion_archives_old_copy(self):
        extra = self.source / 'extra.txt'
        extra.write_text('synthetic extra')
        self.run_backup()
        (self.config / 'plain-paths.txt').write_text(str(self.normal) + '\n')
        result = self.run_backup()
        self.assertFalse(self.remote_path(extra).exists())
        self.assertEqual(next((self.base / 'plain-store/MacBackup/plain/history').rglob('extra.txt')).read_text(),
                         'synthetic extra')
        row = next(item for item in result['results'] if item['area'] == 'plain' and item['kind'] == 'files')
        self.assertEqual(row['policy_archived'][0]['reason'], 'Path not selected.')

    def test_removing_all_inclusions_archives_existing_current(self):
        self.run_backup()
        (self.config / 'plain-paths.txt').write_text('')
        result = self.run_backup()
        self.assertFalse(self.remote_path(self.normal).exists())
        history = self.base / 'plain-store/MacBackup/plain/history'
        self.assertEqual(next(history.rglob('normal.txt')).read_text(), 'synthetic normal v1')
        row = next(item for item in result['results'] if item['area'] == 'plain' and item['kind'] == 'files')
        self.assertEqual(row['archive_policy'], 1)

    def test_forget_removes_policy_archived_copy_from_history(self):
        self.run_backup()
        self.rules(excluded=True)
        self.run_backup()
        self.assertFalse(self.remote_path(self.normal).exists())
        history = self.base / 'plain-store/MacBackup/plain/history'
        self.assertEqual(len(list(history.rglob('normal.txt'))), 1)
        plan_call = self.cli('forget', str(self.normal), '--target', 'google',
                             '--area', 'plain', '--mode', 'trash', '--json')
        self.assertEqual(plan_call.returncode, 0, plan_call.stdout + plan_call.stderr)
        plan = json.loads(plan_call.stdout)
        self.assertEqual(plan['count'], 1)
        self.assertEqual(plan['items'][0]['version'], next(history.iterdir()).name)
        applied = self.cli('forget', '--plan', plan['plan_id'], '--apply', '--json')
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        self.assertFalse(list(history.rglob('normal.txt')))

    def test_private_destination_must_really_be_crypt(self):
        self.rules(private=True)
        self.settings(private="localplain:pretend-private")
        result = self.cli("run", "--target", "google", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("crypt", result.stdout)
        self.assertFalse(self.current.exists())

    def test_ambient_rclone_manifest_cannot_override_selection(self):
        malicious = self.base / "malicious.list"
        malicious.write_text(str(self.secret).lstrip("/") + "\n")
        result = self.cli("run", "--target", "google", "--json", extra_env={"RCLONE_FILES_FROM": str(malicious), "RCLONE_DELETE_EXCLUDED": "true"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.remote_path(self.normal).exists())
        self.assertFalse(self.remote_path(self.secret).exists())

    def test_all_refuses_disabled_proton_instead_of_claiming_two_copies(self):
        result = self.cli("run", "--target", "all", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proton", result.stdout)
        self.assertFalse(self.current.exists())

    def test_file_created_after_plan_cannot_enter_the_transfer(self):
        with patch.dict(os.environ, self.environment, clear=True):
            policy = M["Policy"](self.config, self.home)
            with M["operation_lock"](policy.state_dir):
                targets, limit = M["load_targets"](self.config, "google")
                scan = M["scan_policy"](policy)
                plans = M["transfer_plan"](policy, scan, targets, limit)
                later = self.source / ".env.just-created"
                later.write_text("must never be included")
                for plan in plans:
                    M["perform_sync"](plan, policy.state_dir, "synthetic-run", limit, False)
        self.assertFalse(self.remote_path(later).exists())

    def test_partial_failure_is_recorded_without_claiming_success(self):
        self.rules(private=True)
        policy = M["Policy"](self.config, self.home)
        args = argparse.Namespace(command="run", target="google", json=True)
        operation = M["transport_operation"]
        native = operation.__globals__["perform_sync"]

        def fail_private(plan, *rest):
            if plan["area"] == "private":
                raise M["TransportError"]("synthetic failure")
            return native(plan, *rest)

        with patch.dict(os.environ, self.environment, clear=True), patch.dict(operation.__globals__, {"perform_sync": fail_private}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(operation(args, policy), 1)
        status = json.loads((policy.state_dir / "last-run.json").read_text())
        self.assertFalse(status["ok"])
        self.assertEqual([row["ok"] for row in status["results"]], [True, False])


if __name__ == "__main__":
    unittest.main()
