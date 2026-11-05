"""Exercise actual Zsh TAB completion in an isolated pseudo-terminal."""

import errno
import fcntl
import os
from pathlib import Path
import pty
import re
import runpy
import select
import shlex
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest


REPO = Path(__file__).resolve().parents[2]
INTEGRATION = REPO / "home/.zsh/integrations/macbackup.zsh"
COMPLETION = REPO / "home/.zsh/completions/_macbackup"
ZSH = shutil.which("zsh")


class ZshSession:
    def __init__(self, home: Path, integration_before_compinit: bool = True):
        self.home = home
        self.pending = b""
        (home / ".zsh").symlink_to(REPO / "home/.zsh", target_is_directory=True)
        (home / "bin").mkdir()
        self.canary = home / "command-was-executed"
        for name in ("macbackup", "rclone"):
            executable = home / "bin" / name
            executable.write_text("#!/bin/sh\nprintf 'unexpected execution' > " + shlex.quote(str(self.canary)) + "\n")
            executable.chmod(0o700)
        init = "autoload -Uz compinit\ncompinit -D -i\n"
        source = "source " + shlex.quote(str(INTEGRATION)) + "\n"
        setup = home / "setup.zsh"
        setup.write_text(
            "PROMPT='__MACBACKUP_PROMPT__ '\nRPROMPT=''\nbindkey -e\nunsetopt beep\n"
            "zstyle ':completion:*' menu no\n"
            + (source + init if integration_before_compinit else init + source)
            + """
_macbackup_capture_test_buffer() {
  print -r -- ''
  print -r -- "__MACBACKUP_BUFFER_START__${BUFFER}__MACBACKUP_BUFFER_END__"
  zle reset-prompt
}
zle -N _macbackup_capture_test_buffer
bindkey '^X^B' _macbackup_capture_test_buffer
_macbackup_clear_test_buffer() { BUFFER=''; CURSOR=0; }
zle -N _macbackup_clear_test_buffer
bindkey '^X^K' _macbackup_clear_test_buffer
print -r -- '__MACBACKUP_SETUP_DONE__'
"""
        )
        pid, self.fd = pty.fork()
        if pid == 0:
            env = os.environ.copy()
            env.pop('NO_COLOR', None)
            env.update(HOME=str(home), TERM="xterm-256color", PATH=str(home / "bin") + ":" + env.get("PATH", ""))
            os.execve(ZSH, [ZSH, "-f"], env)
        self.pid = pid
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 180, 0, 0))
        os.write(self.fd, ("source " + shlex.quote(str(setup)) + "\r").encode())
        try:
            self.read_match(rb"__MACBACKUP_SETUP_DONE__\r?\n")
        except BaseException:
            self.close()
            raise

    def read_match(self, pattern, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            match = re.search(pattern, self.pending, re.DOTALL)
            if match:
                self.pending = self.pending[match.end():]
                return match
            readable, _, _ = select.select([self.fd], [], [], max(0, deadline - time.monotonic()))
            if readable:
                try:
                    chunk = os.read(self.fd, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                self.pending += chunk
        raise AssertionError("Zsh completion timed out; output=" + repr(self.pending[-6000:]))

    def complete(self, line):
        # Clear the full buffer even when completion left the cursor in quotes.
        # The custom capture widget prints the resulting buffer without executing it.
        os.write(self.fd, b"\x18\x0b" + line.encode() + b"\t\x18\x02")
        match = self.read_match(rb"__MACBACKUP_BUFFER_START__(.*?)__MACBACKUP_BUFFER_END__")
        return match.group(1).decode()

    def close(self):
        try:
            os.write(self.fd, b"\x18\x0bexit\r")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                done, _ = os.waitpid(self.pid, os.WNOHANG)
                if done:
                    return
                select.select([], [], [], 0.02)
            os.kill(self.pid, signal.SIGKILL)
            os.waitpid(self.pid, 0)
        finally:
            os.close(self.fd)


@unittest.skipUnless(ZSH, "Zsh is required for native completion tests")
class MacbackupCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.temp.name).resolve() / "home with spaces"
        cls.home.mkdir()
        cls.config = cls.home / "configuration directory"
        cls.config.mkdir()
        cls.document = cls.home / "document with spaces.txt"
        cls.document.write_text("synthetic")
        cls.session = ZshSession(cls.home)

    @classmethod
    def tearDownClass(cls):
        cls.session.close()
        assert not cls.session.canary.exists(), "Completion executed macbackup or rclone"
        cls.temp.cleanup()

    def test_subcommands_complete(self):
        for prefix, command in (("in", "init"), ("ch", "check"), ("ex", "explain"), ("lay", "layout"), ("pr", "preview"), ("ru", "run"), ("mou", "mount"), ("st", "status"), ('fo', 'forget'), ('vers', 'versions'), ('veri', 'verify')):
            with self.subTest(command=command):
                self.assertEqual(self.session.complete("macbackup " + prefix).strip(), "macbackup " + command)

    def test_every_cli_option_has_a_completion_description(self):
        script = REPO / 'home/.config/scripts/macbackup'
        parser = runpy.run_path(str(script))['make_parser']()
        source = COMPLETION.read_text()
        subparsers = next(action for action in parser._actions
                          if hasattr(action, 'choices') and isinstance(action.choices, dict)
                          and 'run' in action.choices)
        for command, subparser in subparsers.choices.items():
            match = re.search(r'^      ' + re.escape(command) + r'\)\n(.*?)^        ;;',
                              source, re.MULTILINE | re.DOTALL)
            self.assertIsNotNone(match, command)
            for action in subparser._actions:
                for option in action.option_strings:
                    with self.subTest(command=command, option=option):
                        if option in ('-h', '--help'):
                            self.assertIn('{-h,--help}', match.group(1))
                        else:
                            self.assertTrue(any(option + suffix in match.group(1)
                                                for suffix in ('[', '=[')))

    def test_global_options_complete(self):
        for prefix, option in (("--ver", "--version"), ("--he", "--help")):
            with self.subTest(option=option):
                self.assertEqual(self.session.complete("macbackup " + prefix).strip(), "macbackup " + option)
        self.assertTrue(self.session.complete("macbackup --conf").strip().startswith("macbackup --config-dir"))

    def test_global_options_are_one_colored_compact_group(self):
        with tempfile.TemporaryDirectory() as temp:
            session = ZshSession(Path(temp).resolve())
            try:
                session.pending = b''
                os.write(session.fd, b'\x18\x0bmacbackup -\t')
                output = b''
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if select.select([session.fd], [], [], 0.2)[0]:
                        output += os.read(session.fd, 65536)
                    elif output:
                        break
                for option in (b'--config-dir', b'--help', b'--version'):
                    self.assertEqual(output.count(option), 1, option)
                self.assertIn(b'\x1b[1;34m', output)
                self.assertIn(b'\x1b[2m', output)
            finally:
                session.close()

    def test_subcommand_specific_flags_complete(self):
        for command, prefix, flag in (("check", "--j", "--json"), ("explain", "--j", "--json"), ("layout", "--j", "--json"), ("preview", "--lo", "--local"), ("preview", "--j", "--json"), ("run", "--progress-d", "--progress-depth="), ("init", "--he", "--help")):
            with self.subTest(command=command, flag=flag):
                self.assertEqual(self.session.complete(f"macbackup {command} {prefix}").strip(), f"macbackup {command} {flag}")

    def test_icon_restore_flags_and_paths_complete(self):
        for prefix, option in (('--rep', '--replace'), ('--j', '--json')):
            self.assertEqual(self.session.complete('macbackup restore-icon ' + prefix).strip(), 'macbackup restore-icon ' + option)
        partial = str(self.home / 'document').replace(' ', '\\ ')
        self.assertEqual(shlex.split(self.session.complete('macbackup restore-icon --file ' + partial)),
                         ['macbackup', 'restore-icon', '--file', str(self.document)])
        partial = str(self.home / 'configuration').replace(' ', '\\ ')
        self.assertEqual(shlex.split(self.session.complete('macbackup restore-icon --folder ' + partial))[-1].rstrip('/'), str(self.config))

    def test_mount_options_and_values_complete(self):
        self.assertEqual(self.session.complete('macbackup mount --ar').strip(),
                         'macbackup mount --area=')
        self.assertEqual(self.session.complete('macbackup mount --area pri').strip(),
                         'macbackup mount --area private')
        self.assertEqual(self.session.complete('macbackup mount --target g').strip(),
                         'macbackup mount --target google')

    def test_forget_flags_and_values_complete(self):
        for prefix, option in (('--app', '--apply'), ('--j', '--json'), ('--pl', '--plan')):
            self.assertTrue(self.session.complete('macbackup forget ' + prefix).strip().startswith('macbackup forget ' + option))
        self.assertEqual(self.session.complete('macbackup forget --area pla').strip(), 'macbackup forget --area plain')
        self.assertEqual(self.session.complete('macbackup forget --target g').strip(), 'macbackup forget --target google')
        self.assertEqual(self.session.complete('macbackup forget --mode t').strip(), 'macbackup forget --mode trash')

    def test_versions_and_restore_flags_complete(self):
        self.assertEqual(self.session.complete('macbackup versions --target g').strip(),
                         'macbackup versions --target google')
        self.assertEqual(self.session.complete('macbackup versions --fi').strip(),
                         'macbackup versions --files')
        self.assertEqual(self.session.complete('macbackup restore --rep').strip(),
                         'macbackup restore --replace')
        self.assertEqual(self.session.complete('macbackup restore --lin').strip(),
                         'macbackup restore --links')
        self.assertTrue(self.session.complete('macbackup restore --to ').strip().startswith('macbackup restore --to'))
        self.assertEqual(self.session.complete('macbackup verify --down').strip(),
                         'macbackup verify --download')

    def test_global_flags_are_not_suggested_after_subcommand(self):
        for command in ("check", "explain", "preview", "init"):
            line = f"macbackup {command} --conf"
            with self.subTest(command=command):
                self.assertEqual(self.session.complete(line).strip(), line)

    def test_init_does_not_offer_json_or_cloud_commands(self):
        for line in ("macbackup init --j", "macbackup xx"):
            with self.subTest(line=line):
                self.assertEqual(self.session.complete(line).strip(), line)

    def test_targets_complete_for_remote_commands(self):
        for command in ("preview", "run", "check --remote"):
            with self.subTest(command=command):
                self.assertEqual(self.session.complete(f"macbackup {command} --target g").strip(), f"macbackup {command} --target google")

    def test_local_preview_does_not_offer_remote_target(self):
        line = "macbackup preview --local --tar"
        self.assertEqual(self.session.complete(line).strip(), line)

    def test_flags_still_complete_after_another_subcommand_flag(self):
        self.assertEqual(self.session.complete("macbackup preview --local --j").strip(), "macbackup preview --local --json")

    def test_commands_and_flags_complete_after_global_option_with_spaces(self):
        base = "macbackup --config-dir " + shlex.quote(str(self.config))
        self.assertEqual(shlex.split(self.session.complete(base + " ch")), ["macbackup", "--config-dir", str(self.config), "check"])
        self.assertEqual(shlex.split(self.session.complete(base + " preview --lo")), ["macbackup", "--config-dir", str(self.config), "preview", "--local"])

    def test_commands_complete_after_equals_form_of_global_option(self):
        line = "macbackup --config-dir=" + shlex.quote(str(self.config)) + " ex"
        self.assertEqual(shlex.split(self.session.complete(line)), ["macbackup", "--config-dir=" + str(self.config), "explain"])

    def test_config_directory_value_completes_and_quotes_spaces(self):
        partial = str(self.home / "configuration")
        completed = self.session.complete("macbackup --config-dir " + shlex.quote(partial))
        self.assertEqual(shlex.split(completed)[-1].rstrip("/"), str(self.config))

    def test_config_directory_value_does_not_complete_files(self):
        line = "macbackup --config-dir " + str(self.home / "document").replace(" ", "\\ ")
        self.assertEqual(shlex.split(self.session.complete(line)), shlex.split(line))

    def test_explain_file_path_completes_and_quotes_spaces(self):
        line = "macbackup explain " + str(self.home / "document").replace(" ", "\\ ")
        self.assertEqual(shlex.split(self.session.complete(line)), ["macbackup", "explain", str(self.document)])

    def test_empty_explain_path_starts_at_root(self):
        self.assertEqual(self.session.complete("macbackup explain "), "macbackup explain /")

    def test_integration_can_be_loaded_after_compinit_for_existing_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp).resolve()
            session = ZshSession(home, integration_before_compinit=False)
            try:
                self.assertEqual(session.complete("macbackup ch").strip(), "macbackup check")
            finally:
                session.close()
            self.assertFalse(session.canary.exists())

    def test_zsh_files_pass_syntax_check(self):
        for path in (INTEGRATION, COMPLETION):
            with self.subTest(path=path):
                result = subprocess.run([ZSH, "-n", str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
