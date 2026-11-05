"""Read-only mount layout, conflict checks and mountpoint cleanup."""

import argparse
import io
import os
from pathlib import Path
import pty
import runpy
import select
import shutil
import subprocess
import tempfile
import termios
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[2] / "home/.config/scripts/macbackup"
M = runpy.run_path(str(SCRIPT))


class MountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.config = self.home / '.config/macbackup'
        M['init_config'](self.config, self.home)
        (self.home / 'Desktop').mkdir()

    def test_mount_discards_typed_input_and_restores_terminal(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, slave)
        self.addCleanup(os.close, master)
        original = termios.tcgetattr(slave)
        with os.fdopen(os.dup(slave), 'rb', buffering=0) as stream, \
             patch('sys.stdin', stream):
            with M['discard_mount_input']() as fd:
                active = termios.tcgetattr(fd)
                self.assertFalse(active[3] & termios.ECHO)
                self.assertFalse(active[3] & termios.ICANON)
                self.assertTrue(active[3] & termios.ISIG)
                self.assertEqual(active[6][termios.VINTR], original[6][termios.VINTR])
                os.write(master, b'unwanted command\n')
                self.assertTrue(select.select([fd], [], [], 1)[0])
                self.assertEqual(os.read(fd, 4096), b'unwanted command\n')
        self.assertEqual(termios.tcgetattr(slave), original)

    def test_mount_guards_input_during_inventory_and_startup(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, slave)
        self.addCleanup(os.close, master)
        original = termios.tcgetattr(slave)
        process = Mock()
        process.poll.return_value = None
        targets = ({'google': {'plain': 'localplain:MacBackup/plain',
                               'private': 'localcrypt:'}}, 25)
        stages = []

        def inventory(_roots, _name, input_fd):
            stages.append('inventory')
            self.assertFalse(termios.tcgetattr(input_fd)[3] & termios.ECHO)
            os.write(master, b'ignored')
            M['mount_input_wait'](input_fd, 0.1)
            self.assertFalse(select.select([input_fd], [], [], 0)[0])

        def startup(input_fd, _timeout):
            stages.append('startup')
            self.assertFalse(termios.tcgetattr(input_fd)[3] & termios.ECHO)
            raise KeyboardInterrupt

        args = argparse.Namespace(target='google', area='all', mountpoint=None)
        with os.fdopen(os.dup(slave), 'rb', buffering=0) as stream, \
             patch('sys.stdin', stream), redirect_stdout(io.StringIO()), \
             patch('subprocess.Popen', return_value=process), \
             patch('os.path.ismount', return_value=False), \
             patch.dict(M['mount_operation'].__globals__,
                        {'load_targets': lambda *_args: targets,
                         'mount_current_conflicts': inventory,
                         'mount_input_wait': startup}):
            self.assertEqual(M['mount_operation'](args, self.config, self.home), 0)
        self.assertEqual(stages, ['inventory', 'startup'])
        self.assertEqual(termios.tcgetattr(slave), original)
        process.terminate.assert_called_once()

    def test_mount_progress_shows_indeterminate_ascii_bar_and_elapsed_time(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch('sys.stderr', terminal), \
             patch.dict(os.environ, {'TERM': 'xterm-256color', 'NO_COLOR': '',
                                     'PYTHON_COLORS': '1'}):
            pulse = M['MountPulse']('Inventario google/plain')
            pulse.draw(1048576)
            pulse.done('12 voci lette')
        output = terminal.getvalue()
        self.assertRegex(output, r'\[[#.]{22}\]')
        self.assertIn('\x1b[1;36m', output)
        self.assertIn('metadati 1.0 MiB', output)
        self.assertIn('12 voci lette', output)
        self.assertRegex(output, r'\(\d+s\)')

    def test_mount_progress_respects_no_color_and_redirected_output(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch('sys.stderr', terminal), \
             patch.dict(os.environ, {'NO_COLOR': '1', 'PYTHON_COLORS': ''}):
            pulse = M['MountPulse']('Avvio google/all')
            pulse.draw()
            pulse.done('completato')
        self.assertNotIn('\x1b[1;36m', terminal.getvalue())
        self.assertNotIn('\x1b[32m', terminal.getvalue())
        redirected = io.StringIO()
        with patch('sys.stderr', redirected):
            pulse = M['MountPulse']('Avvio google/all')
            pulse.done('completato')
        self.assertNotIn('\x1b[', redirected.getvalue())

    @unittest.skipUnless(shutil.which('rclone'), 'rclone is needed for inventory checks')
    def test_interrupting_inventory_stops_rclone(self):
        process = Mock()
        process.poll.return_value = None
        with patch('subprocess.Popen', return_value=process), \
             patch('time.sleep', side_effect=KeyboardInterrupt):
            with self.assertRaisesRegex(M['ConfigError'], 'interrotto'):
                M['mount_inventory']('synthetic:', 'google/plain')
        process.terminate.assert_called_once()
        process.wait.assert_called_once()

    def test_mount_uses_configured_plain_remote_read_only_and_stops_on_interrupt(self):
        mounted = False
        process = Mock()
        process.poll.return_value = None
        process.wait.return_value = 0
        def stop():
            nonlocal mounted
            mounted = False
        process.terminate.side_effect = stop
        def start(command, **_kwargs):
            nonlocal mounted
            mounted = True
            self.assertEqual(command[:3], ['rclone', 'nfsmount', 'localplain:MacBackup/plain'])
            self.assertIn('--read-only', command)
            self.assertEqual(command[command.index('--addr') + 1], '127.0.0.1:0')
            return process
        args = argparse.Namespace(target='google', area='plain', mountpoint=None)
        targets = ({'google': {'plain': 'localplain:MacBackup/plain', 'private': 'localcrypt:'}}, 25)
        output = io.StringIO()
        with redirect_stdout(output), patch('subprocess.Popen', side_effect=start), \
             patch('os.path.ismount', side_effect=lambda _path: mounted), \
             patch('time.sleep', side_effect=KeyboardInterrupt), \
             patch.dict(M['mount_operation'].__globals__, {'load_targets': lambda *_args: targets}):
            result = M['mount_operation'](args, self.config, self.home)
        self.assertEqual(result, 0)
        process.terminate.assert_called_once()
        point = self.home / 'Desktop/google-plain'
        self.assertIn(f'Volume smontato: {point}', output.getvalue())
        self.assertFalse(point.exists())
        decision = M['Policy'](self.config, self.home).decide(point / 'current/file.txt')
        self.assertEqual(decision.action, 'skip')
        self.assertEqual(decision.rule, str(point))

    def test_mount_keeps_preexisting_empty_mountpoint(self):
        point = self.home / 'Desktop/google-plain'
        point.mkdir(parents=True)
        mounted = False
        process = Mock()
        process.poll.return_value = None
        def start(*_args, **_kwargs):
            nonlocal mounted
            mounted = True
            return process
        def stop():
            nonlocal mounted
            mounted = False
        process.terminate.side_effect = stop
        args = argparse.Namespace(target='google', area='plain', mountpoint=None)
        targets = ({'google': {'plain': 'localplain:MacBackup/plain', 'private': 'localcrypt:'}}, 25)
        with patch('subprocess.Popen', side_effect=start), \
             patch('os.path.ismount', side_effect=lambda _path: mounted), \
             patch('time.sleep', side_effect=KeyboardInterrupt), \
             patch.dict(M['mount_operation'].__globals__, {'load_targets': lambda *_args: targets}):
            self.assertEqual(M['mount_operation'](args, self.config, self.home), 0)
        self.assertTrue(point.is_dir())

    def test_external_eject_is_a_clean_shutdown(self):
        mounted = False
        process = Mock()
        def start(*_args, **_kwargs):
            nonlocal mounted
            mounted = True
            return process
        def poll():
            nonlocal mounted
            mounted = False
            return 0
        process.poll.side_effect = poll
        args = argparse.Namespace(target='google', area='plain', mountpoint=None)
        targets = ({'google': {'plain': 'localplain:MacBackup/plain', 'private': 'localcrypt:'}}, 25)
        with patch('subprocess.Popen', side_effect=start), \
             patch('os.path.ismount', side_effect=lambda _path: mounted), \
             patch.dict(M['mount_operation'].__globals__, {'load_targets': lambda *_args: targets}):
            self.assertEqual(M['mount_operation'](args, self.config, self.home), 0)
        process.terminate.assert_not_called()
        self.assertFalse((self.home / 'Desktop/google-plain').exists())

    def test_eject_during_mount_startup_is_clean_when_rclone_logged_unmount(self):
        process = Mock()
        process.poll.return_value = 0
        def start(*_args, **kwargs):
            kwargs['stdout'].write('NOTICE: Unmounted rclone mount\n')
            kwargs['stdout'].flush()
            return process
        args = argparse.Namespace(target='google', area='plain', mountpoint=None)
        targets = ({'google': {'plain': 'localplain:MacBackup/plain', 'private': 'localcrypt:'}}, 25)
        with patch('subprocess.Popen', side_effect=start), \
             patch('os.path.ismount', return_value=False), \
             patch.dict(M['mount_operation'].__globals__, {'load_targets': lambda *_args: targets}):
            self.assertEqual(M['mount_operation'](args, self.config, self.home), 0)
        self.assertFalse((self.home / 'Desktop/google-plain').exists())

    def test_unexpected_mount_exit_remains_an_error(self):
        mounted = False
        process = Mock()
        def start(*_args, **_kwargs):
            nonlocal mounted
            mounted = True
            return process
        def poll():
            nonlocal mounted
            mounted = False
            return 1
        process.poll.side_effect = poll
        args = argparse.Namespace(target='google', area='plain', mountpoint=None)
        targets = ({'google': {'plain': 'localplain:MacBackup/plain', 'private': 'localcrypt:'}}, 25)
        with patch('subprocess.Popen', side_effect=start), \
             patch('os.path.ismount', side_effect=lambda _path: mounted), \
             patch.dict(M['mount_operation'].__globals__, {'load_targets': lambda *_args: targets}):
            with self.assertRaisesRegex(M['TransportError'], 'codice 1'):
                M['mount_operation'](args, self.config, self.home)
        self.assertFalse((self.home / 'Desktop/google-plain').exists())

    def test_mount_all_combines_plain_and_private_in_one_protected_volume(self):
        mounted = False
        process = Mock()
        process.poll.return_value = None
        def start(command, **kwargs):
            nonlocal mounted
            mounted = True
            self.assertEqual(command[:2], ['rclone', 'nfsmount'])
            self.assertTrue(command[2].startswith('macbackup_mount_'))
            self.assertEqual(command[3], str(self.home / 'Desktop/google'))
            self.assertIn('--read-only', command)
            env = kwargs['env']
            self.assertIn('union', env.values())
            self.assertIn('current=', ' '.join(env.values()))
            self.assertIn('history=', ' '.join(env.values()))
            return process
        def stop():
            nonlocal mounted
            mounted = False
        process.terminate.side_effect = stop
        args = argparse.Namespace(target='google', area='all', mountpoint=None)
        targets = ({'google': {'plain': 'localplain:MacBackup/plain', 'private': 'localcrypt:'}}, 25)
        with patch('subprocess.Popen', side_effect=start), \
             patch('os.path.ismount', side_effect=lambda _path: mounted), \
             patch('time.sleep', side_effect=KeyboardInterrupt), \
             patch.dict(M['mount_operation'].__globals__,
                        {'load_targets': lambda *_args: targets,
                         'mount_current_conflicts': lambda *_args: None}):
            self.assertEqual(M['mount_operation'](args, self.config, self.home), 0)
        point = self.home / 'Desktop/google'
        self.assertFalse(point.exists())
        self.assertEqual(M['Policy'](self.config, self.home).decide(point / 'private/current/file').action,
                         'skip')

    def test_desktop_mounts_are_never_selected_for_backup(self):
        points = (self.home / 'Desktop/google', self.home / 'Desktop/google-plain')
        for point in points:
            (point / 'current').mkdir(parents=True)
            (point / 'current/file.txt').write_text('cloud file')
        (self.config / 'plain-paths.txt').write_text(
            str(self.home / 'Desktop') + '\n' + ''.join(str(point) + '\n' for point in points))
        policy = M['Policy'](self.config, self.home)
        scan = M['scan_policy'](policy)
        self.assertFalse(scan.errors, scan.errors)
        for point in points:
            self.assertNotIn(str(point / 'current/file.txt'), [entry.path for entry in scan.entries])
            self.assertEqual(policy.decide(point / 'current/file.txt').action, 'skip')

    @unittest.skipUnless(shutil.which('rclone'), 'rclone is needed for inventory checks')
    def test_merged_mount_refuses_same_current_file_in_plain_and_private(self):
        roots = {'plain': str(self.base / 'plain'), 'private': str(self.base / 'private')}
        for root in roots.values():
            folder = Path(root) / 'current/Users/test/project'
            folder.mkdir(parents=True)
            (folder / 'shared.txt').write_text('synthetic')
        point = self.home / 'Desktop/google'
        point.mkdir()
        (point / 'keep.txt').write_text('unrelated')
        args = argparse.Namespace(target='google', area='all', mountpoint=None)
        targets = ({'google': roots}, 25)
        with patch.dict(M['mount_operation'].__globals__,
                        {'load_targets': lambda *_args: targets}):
            with self.assertRaisesRegex(M['ConfigError'], 'Users/test/project/shared.txt'):
                M['mount_operation'](args, self.config, self.home)
        self.assertEqual((point / 'keep.txt').read_text(), 'unrelated')

    @unittest.skipUnless(shutil.which('rclone'), 'rclone is needed for inventory checks')
    def test_merged_mount_refuses_file_directory_collision(self):
        plain = self.base / 'plain/current/Users/test'
        private = self.base / 'private/current/Users/test'
        plain.mkdir(parents=True)
        (private / 'item').mkdir(parents=True)
        (plain / 'item').write_text('file')
        (private / 'item/child').write_text('child')
        with self.assertRaisesRegex(M['ConfigError'], 'Users/test/item'):
            M['mount_current_conflicts']({
                'plain': str(self.base / 'plain'),
                'private': str(self.base / 'private'),
            })
