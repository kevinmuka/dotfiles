"""Terminal presentation stays interactive without leaking input into the shell."""

import io
import os
from pathlib import Path
import pty
import runpy
import select
import termios
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / 'home/.config/scripts/macbackup'
M = runpy.run_path(str(SCRIPT))


class UiTests(unittest.TestCase):
    def test_activity_shows_bar_discards_keys_and_restores_terminal(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, slave)
        self.addCleanup(os.close, master)
        original = termios.tcgetattr(slave)
        with os.fdopen(os.dup(slave), 'rb', buffering=0) as stdin, \
             os.fdopen(os.dup(slave), 'w', buffering=1) as stderr, \
             patch('sys.stdin', stdin), patch('sys.stderr', stderr):
            with M['operation_activity']('Prova scansione'):
                active = termios.tcgetattr(slave)
                self.assertFalse(active[3] & termios.ECHO)
                self.assertTrue(active[3] & termios.ISIG)
                os.write(master, b'unwanted command\n')
                time.sleep(0.45)
                self.assertFalse(select.select([stdin.fileno()], [], [], 0)[0])
        self.assertEqual(termios.tcgetattr(slave), original)
        output = b''
        while select.select([master], [], [], 0)[0]:
            output += os.read(master, 4096)
        self.assertIn(b'Prova scansione', output)
        self.assertIn(b'complete', output)
        self.assertNotIn(b'unwanted command', output)

    def test_color_is_only_for_supported_terminals(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        terminal = Terminal()
        with patch.dict(os.environ, {'TERM': 'xterm-256color', 'NO_COLOR': '',
                                     'PYTHON_COLORS': ''}):
            self.assertIn('\x1b[1;31m', M['ui']('ERRORE:', 'error', terminal))
            self.assertEqual(M['ui']('ERRORE:', 'error', io.StringIO()), 'ERRORE:')
        with patch.dict(os.environ, {'NO_COLOR': '1', 'PYTHON_COLORS': ''}):
            self.assertEqual(M['ui']('ERRORE:', 'error', terminal), 'ERRORE:')

    def test_run_dashboard_highlights_speed_without_changing_plain_output(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        lines = ['macbackup  google/plain', 'SPEED  1.0 MiB/s',
                 'Active files:', '  Users/kevinmuka/Desktop/file.txt',
                 '    [######------]  1 MB / 2 MB', 'Keys  [u] Switch units',
                 'Current units: binary', 'Legend (current phase)',
                 '  Data: transferred volume']
        with patch.dict(os.environ, {'TERM': 'xterm-256color', 'NO_COLOR': '',
                                     'PYTHON_COLORS': ''}):
            rendered = M['styled_progress_lines'](lines, Terminal())
            self.assertIn('\x1b[1;32mSPEED\x1b[0m  1.0 MiB/s', rendered)
            self.assertIn('\x1b[1;36mActive files:\x1b[0m', rendered)
            self.assertIn('  \x1b[2;90mUsers/kevinmuka/Desktop/file.txt\x1b[0m', rendered)
            self.assertIn('    [######------]  1 MB / 2 MB', rendered)
            self.assertIn('\x1b[2;90mKeys  [u] Switch units\x1b[0m', rendered)
            self.assertIn('\x1b[2;90mCurrent units: binary\x1b[0m', rendered)
            self.assertIn('\x1b[2;90m  Data: transferred volume\x1b[0m', rendered)
            self.assertEqual(M['styled_progress_lines'](lines, io.StringIO()),
                             '\n'.join(lines))

    def test_warning_keeps_label_distinct_from_file_path(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        with patch('sys.stdout', Terminal()), \
             patch.dict(os.environ, {'TERM': 'xterm-256color', 'NO_COLOR': '',
                                     'PYTHON_COLORS': ''}):
            line = M['issue_line']('AVVISO:', '/Users/example/.zshrc: collegamento',
                                   'warning')
            self.assertIn('\x1b[1;33mAVVISO:\x1b[0m', line)
            self.assertIn('\x1b[2m/Users/example/.zshrc\x1b[0m', line)
        with patch('sys.stdout', io.StringIO()):
            self.assertEqual(M['issue_line']('AVVISO:', '/tmp/a: collegamento', 'warning'),
                             'AVVISO: /tmp/a: collegamento')

    def test_secondary_text_is_gray_only_on_color_terminal(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        with patch.dict(os.environ, {'TERM': 'xterm-256color', 'NO_COLOR': '',
                                     'PYTHON_COLORS': '', 'ZSH_THEME_MODE': 'light'}):
            self.assertEqual(M['ui']('google/plain current', 'subtle', Terminal()),
                             '\x1b[2;90mgoogle/plain current\x1b[0m')
            self.assertEqual(M['ui']('google/plain current', 'remote', Terminal()),
                             '\x1b[1;38;2;37;86;152mgoogle/plain current\x1b[0m')
            self.assertEqual(M['ui']('google/plain current', 'subtle', io.StringIO()),
                             'google/plain current')
        with patch.dict(os.environ, {'TERM': 'xterm-256color', 'NO_COLOR': '',
                                     'PYTHON_COLORS': '', 'ZSH_THEME_MODE': 'dark'}):
            self.assertEqual(M['ui']('google/plain current', 'remote', Terminal()),
                             '\x1b[1;38;2;139;181;236mgoogle/plain current\x1b[0m')


if __name__ == '__main__':
    unittest.main()
