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


SCRIPT = Path(__file__).resolve().parents[1] / "home/.config/scripts/macbackup"
M = runpy.run_path(str(SCRIPT))


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
        (self.config / "plain-paths.txt").write_text(str(self.source) + "\n" + (str(self.secret) + "\n" if exact_plain else ""))
        (self.config / "private-paths.txt").write_text(str(self.secret) + "\n" if private else "")
        (self.config / "exclude-paths.txt").write_text(str(self.normal) + "\n" if excluded else "")

    def cli(self, *args, extra_env=None):
        env = self.environment | (extra_env or {})
        return subprocess.run([sys.executable, str(SCRIPT), "--config-dir", str(self.config), *args], env=env, capture_output=True, text=True)

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
        self.assertIn("Anteprima", json.loads(result.stdout)["note"])

    def test_backup_excludes_env_and_keeps_absolute_path_structure(self):
        self.run_backup()
        self.assertEqual(self.remote_path(self.normal).read_bytes(), self.normal.read_bytes())
        self.assertFalse(self.remote_path(self.secret).exists())

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
        self.assertIn('Dati       [', result.stderr)
        self.assertIn('VELOCITÀ', result.stderr)
        self.assertIn('Avvio google/plain/files:', result.stderr)

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
        self.assertIn('Dati       [', stderr)
        self.assertIn('Tempo 2s', stderr)

    def test_run_text_summary_distinguishes_selected_and_transferred(self):
        result = self.cli('run', '--target', 'google')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('selezionati 1', result.stdout)
        self.assertIn('Trasferiti 1 file, 19 byte', result.stdout)

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
        self.assertIn('Tempo 1m 5s', binary)
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
        self.assertIn('Tempo stimato: stima variabile', decimal)

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
            self.assertIn('Interrotto', state.read_text())
            self.assertNotIn('\\u2019', state.read_text())
            status = self.cli('status')
            self.assertIn("dall'utente", status.stdout)
            self.assertIn('già', status.stdout)
            self.assertNotIn('\\u00e0', status.stdout)
        finally:
            script_globals['perform_sync'] = original

    def test_private_round_trip_and_explicit_revocation_preserve_old_copy(self):
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
        result = subprocess.run(["rclone", "cat", source], env=self.environment, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "synthetic private v1")

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
        (self.config / "private-paths.txt").write_text(str(directory) + "\n")
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

    def test_new_exclusion_does_not_delete_or_update_existing_copy(self):
        self.run_backup()
        self.normal.write_text("changed but excluded")
        self.rules(excluded=True)
        self.run_backup()
        self.assertEqual(self.remote_path(self.normal).read_text(), "synthetic normal v1")

    def test_new_directory_name_pattern_preserves_old_cloud_copy(self):
        old = self.source / "node_modules/package.txt"
        old.parent.mkdir()
        old.write_text("synthetic dependency v1")
        self.run_backup()
        self.assertEqual(self.remote_path(old).read_text(), "synthetic dependency v1")
        old.write_text("synthetic dependency v2")
        (self.config / "explicit-only-patterns.txt").write_text(".env\n.env.*\nnode_modules\n")
        result = self.run_backup()
        self.assertEqual(self.remote_path(old).read_text(), "synthetic dependency v1")
        self.assertFalse(any(item["archive_deleted"] for item in result["results"]))
        history = self.base / "plain-store/MacBackup/plain/history"
        self.assertFalse(history.exists())

    def test_git_history_routes_to_crypt_and_old_plain_copy_is_retained(self):
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
        self.assertTrue(self.remote_path(object_file).exists())
        encrypted = 'localcrypt:current/' + str(object_file).lstrip('/')
        restored = subprocess.run(['rclone', 'cat', encrypted], env=self.environment,
                                  capture_output=True, text=True, check=True)
        self.assertEqual(restored.stdout, 'synthetic git object')
        forbidden = subprocess.run(['rclone', 'lsf', 'localcrypt:current/' +
                                    str(env_file.parent).lstrip('/')], env=self.environment,
                                   capture_output=True, text=True)
        self.assertNotIn('.env', forbidden.stdout.splitlines())

    def test_new_ignored_file_rule_keeps_old_cloud_copy(self):
        old = self.source / '.DS_Store'
        old.write_text('synthetic finder metadata')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'ignored_file_names = [".DS_Store"]', 'ignored_file_names = []'))
        self.run_backup()
        self.assertTrue(self.remote_path(old).exists())
        settings.write_text(settings.read_text().replace(
            'ignored_file_names = []', 'ignored_file_names = [".DS_Store"]'))
        result = self.run_backup()
        self.assertFalse(any(item['archive_deleted'] for item in result['results']))
        self.assertTrue(self.remote_path(old).exists())

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
        self.assertIn('non prova corruzione', data['note'])

    def test_verify_before_first_backup_reports_missing_copy(self):
        checked = self.cli('verify', '--target', 'google', '--area', 'plain', '--json')
        self.assertEqual(checked.returncode, 1)
        data = json.loads(checked.stdout)
        self.assertEqual(len(data['results'][0]['missing']), 1)

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

    def test_deletion_threshold_stops_before_any_transfer(self):
        self.run_backup()
        self.normal.unlink()
        self.settings(limit=0)
        result = self.cli("run", "--target", "google", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.remote_path(self.normal).exists())
        self.assertIn("max_delete", result.stdout)

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
