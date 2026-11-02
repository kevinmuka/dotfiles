"""Safety contracts for the local selector; synthetic files only, no cloud."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "home/.config/scripts/macbackup"
MODULE = runpy.run_path(str(SCRIPT))
Policy = MODULE["Policy"]
ConfigError = MODULE["ConfigError"]
scan_policy = MODULE["scan_policy"]
split_layout = MODULE["split_layout"]
init_config = MODULE["init_config"]


class LocalSelectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        self.config = self.home / ".config/macbackup"
        init_config(self.config, self.home)
        self.project = self.home / "Desktop/project"
        self.project.mkdir(parents=True)
        self.normal = self.write(self.project / "main.txt")
        self.env = self.write(self.project / ".env")
        self.env_local = self.write(self.project / ".env.local")
        self.nested = self.write(self.project / "nested/.env")
        self.set_rules(plain=[self.project])

    def write(self, path, contents="synthetic test content"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def set_rules(self, plain=(), private=(), excluded=(), patterns=(".env", ".env.*")):
        for filename, values in [
            ("plain-paths.txt", plain), ("private-paths.txt", private),
            ("exclude-paths.txt", excluded), ("explicit-only-patterns.txt", patterns),
        ]:
            (self.config / filename).write_text("\n".join(map(str, values)) + "\n")

    def policy(self):
        return Policy(self.config, self.home)

    def scan(self):
        return scan_policy(self.policy())

    def action(self, path):
        return self.policy().decide(path).action

    def test_recursive_parent_does_not_authorize_any_env(self):
        for path in (self.env, self.env_local, self.nested):
            with self.subTest(path=path):
                self.assertEqual(self.action(path), "skip")
        self.assertEqual(self.action(self.normal), "plain")

    def test_exact_plain_entry_authorizes_only_one_file(self):
        self.set_rules(plain=[self.project, self.env])
        self.assertEqual(self.action(self.env), "plain")
        for path in (self.env_local, self.nested):
            self.assertEqual(self.action(path), "skip")

    def test_exact_private_entry_works_without_parent(self):
        self.set_rules(private=[self.env])
        self.assertEqual(self.action(self.env), "private")
        self.assertEqual(self.action(self.normal), "skip")

    def test_private_parent_alone_does_not_authorize_env(self):
        self.set_rules(private=[self.project])
        self.assertEqual(self.action(self.env), "skip")
        self.assertEqual(self.action(self.normal), "private")

    def test_private_wins_when_both_exact_entries_exist(self):
        self.set_rules(plain=[self.project, self.env], private=[self.env])
        self.assertEqual(self.action(self.env), "private")

    def test_exact_plain_entry_cannot_downgrade_private_parent(self):
        self.set_rules(plain=[self.env], private=[self.project])
        self.assertEqual(self.action(self.env), "private")

    def test_absolute_exclusion_wins_over_exact_entries(self):
        self.set_rules(plain=[self.env], private=[self.env], excluded=[self.project])
        self.assertEqual(self.action(self.env), "skip")
        self.assertFalse(self.scan().errors)

    def test_path_prefix_does_not_match_similarly_named_directory(self):
        other = self.write(self.home / "Desktop/project-old/readme")
        self.set_rules(plain=[self.home / "Desktop"], excluded=[self.project])
        self.assertEqual(self.action(other), "plain")
        self.assertEqual(self.action(self.normal), "skip")

    def test_brackets_and_asterisk_are_literal_in_path_lists(self):
        strange = self.write(self.home / "Desktop/proj[one]*/notes")
        other = self.write(self.home / "Desktop/projoABC/notes")
        self.set_rules(plain=[strange.parent])
        self.assertEqual(self.action(strange), "plain")
        self.assertEqual(self.action(other), "skip")

    def test_names_with_spaces_are_supported_without_quotes_in_lists(self):
        path = self.write(self.project / "folder with spaces/document.txt")
        self.set_rules(plain=[path])
        self.assertEqual(self.action(path), "plain")
        self.assertFalse(self.scan().errors)

    def test_guarded_patterns_cover_uppercase_and_example_variants(self):
        for name in ("uppercase/.ENV", ".env.example", "nested/.EnV.Production"):
            with self.subTest(name=name):
                path = self.write(self.project / name)
                self.assertEqual(self.action(path), "skip")

    def test_patterns_apply_to_directory_names_and_prune_descendants(self):
        path = self.write(self.project / ".env.folder/ordinary.txt")
        self.assertEqual(self.policy().decide(path.parent, directory=True).action, "skip")
        entries = {entry.path: entry for entry in self.scan().entries}
        self.assertEqual(entries[str(path.parent)].kind, "excluded-subtree")
        self.assertNotIn(str(path), entries)

    def test_generated_directory_names_are_protected_anywhere(self):
        files = [self.write(self.project / name / "package.txt")
                 for name in ("node_modules", ".venv", "venv", "myenv")]
        self.set_rules(plain=[self.project],
                       patterns=(".env", ".env.*", "node_modules", ".venv", "venv", "myenv"))
        entries = {entry.path: entry for entry in self.scan().entries}
        for file in files:
            with self.subTest(file=file):
                self.assertEqual(entries[str(file.parent)].kind, "excluded-subtree")
                self.assertNotIn(str(file), entries)
                self.assertEqual(self.action(file), "skip")
        self.assertEqual(entries[str(self.normal)].decision.action, "plain")

    def test_git_history_name_is_protected_without_hiding_working_tree(self):
        object_file = self.write(self.project / '.git/objects/ab/cdef')
        self.set_rules(plain=[self.project], patterns=('.env', '.env.*', '.git'))
        entries = {entry.path: entry for entry in self.scan().entries}
        self.assertEqual(entries[str(object_file.parent.parent.parent)].kind, 'excluded-subtree')
        self.assertNotIn(str(object_file), entries)
        self.assertEqual(entries[str(self.normal)].decision.action, 'plain')

    def test_git_directory_name_routes_private_and_env_inside_stays_protected(self):
        object_file = self.write(self.project / '.git/objects/ab/cdef')
        secret = self.write(self.project / '.git/.env')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'private_directory_names = []', 'private_directory_names = [".git"]'))
        self.set_rules(plain=[self.project], patterns=('.env', '.env.*', '.git'))
        entries = {entry.path: entry for entry in self.scan().entries}
        self.assertEqual(entries[str(object_file)].decision.action, 'private')
        self.assertEqual(self.action(object_file), 'private')
        self.assertNotIn(str(secret), [path for path, entry in entries.items()
                                         if entry.decision.action in ('plain', 'private')])
        self.assertEqual(entries[str(self.normal)].decision.action, 'plain')

    def test_ignored_file_name_skips_even_exact_inclusion_and_keeps_sibling(self):
        unwanted = self.write(self.project / '.DS_Store')
        spaced = self.write(self.project / ' ← ')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'ignored_file_names = [".DS_Store"]', 'ignored_file_names = [".DS_Store", " ← "]'))
        self.set_rules(plain=[self.project, unwanted])
        self.assertEqual(self.action(unwanted), 'skip')
        self.assertEqual(self.action(spaced), 'skip')
        entries = {entry.path: entry for entry in self.scan().entries}
        self.assertEqual(entries[str(unwanted)].decision.action, 'skip')
        self.assertEqual(entries[str(spaced)].decision.action, 'skip')
        self.assertEqual(entries[str(self.normal)].decision.action, 'plain')

    def test_invalid_ignored_file_names_fail_closed(self):
        settings = self.config / 'settings.toml'
        original = settings.read_text()
        for value in ('"a/b"', '"*"', '".."', '12'):
            with self.subTest(value=value):
                settings.write_text(original.replace('ignored_file_names = [".DS_Store"]',
                                                     'ignored_file_names = [' + value + ']'))
                with self.assertRaises(ConfigError):
                    self.policy()

    def test_layout_shows_private_git_boundary_without_listing_env(self):
        object_file = self.write(self.project / '.git/objects/ab/cdef')
        self.write(self.project / '.git/.env')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'private_directory_names = []', 'private_directory_names = [".git"]'))
        self.set_rules(plain=[self.project], patterns=('.env', '.env.*', '.git'))
        layout = split_layout(self.policy(), self.project)
        self.assertTrue(layout['ok'])
        self.assertEqual(layout['private_items'], 1)
        self.assertEqual(layout['private_subtrees'][0]['path'], str(self.project / '.git'))
        self.assertEqual(layout['private_subtrees'][0]['private_items'], 1)
        self.assertEqual(layout['private_subtrees'][0]['selected_bytes'], object_file.stat().st_size)
        self.assertNotIn('.env', json.dumps(layout['private_subtrees']))

    def test_layout_refuses_private_root(self):
        self.set_rules(private=[self.project])
        with self.assertRaises(ConfigError):
            split_layout(self.policy(), self.project)

    def test_layout_without_path_uses_current_directory(self):
        self.write(self.project / '.git/objects/ab/cdef')
        settings = self.config / 'settings.toml'
        settings.write_text(settings.read_text().replace(
            'private_directory_names = []', 'private_directory_names = [".git"]'))
        self.set_rules(plain=[self.project], patterns=('.env', '.env.*', '.git'))
        result = subprocess.run(
            [sys.executable, str(SCRIPT), '--config-dir', str(self.config), 'layout', '--json'],
            cwd=self.project, env={**os.environ, 'HOME': str(self.home)},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['path'], str(self.project))
        self.assertEqual(data['private_subtrees'][0]['path'], str(self.project / '.git'))

    def test_invalid_private_directory_names_fail_closed(self):
        settings = self.config / 'settings.toml'
        original = settings.read_text()
        for value in ('"a/b"', '"*"', '".."', '12'):
            with self.subTest(value=value):
                settings.write_text(original.replace('private_directory_names = []',
                                                     'private_directory_names = [' + value + ']'))
                with self.assertRaises(ConfigError):
                    self.policy()

    def test_exact_directory_inclusion_overrides_its_protected_name(self):
        file = self.write(self.project / "node_modules/package.txt")
        self.set_rules(plain=[self.project, file.parent], patterns=("node_modules",))
        entries = {entry.path: entry for entry in self.scan().entries}
        self.assertEqual(entries[str(file)].decision.action, "plain")
        self.assertEqual(self.action(file), "plain")

    def test_absolute_exclusion_still_wins_over_protected_directory_override(self):
        file = self.write(self.project / "node_modules/package.txt")
        self.set_rules(plain=[self.project, file.parent], excluded=[file.parent],
                       patterns=("node_modules",))
        entries = {entry.path: entry for entry in self.scan().entries}
        self.assertEqual(entries[str(file.parent)].kind, "excluded-subtree")
        self.assertNotIn(str(file), entries)

    def test_missing_pattern_file_fails_closed(self):
        (self.config / "explicit-only-patterns.txt").unlink()
        with self.assertRaises(ConfigError):
            self.policy()

    def test_invalid_patterns_are_rejected(self):
        for pattern in ("a/b", "**", "*.?", "[ab]", "{a,b}", "+ .env", "- .env", "a\\b"):
            with self.subTest(pattern=pattern):
                self.set_rules(patterns=[pattern])
                with self.assertRaises(ConfigError):
                    self.policy()

    def test_relative_dotdot_root_and_control_paths_are_rejected(self):
        for value in ("relative", "~/Desktop", "$HOME/Desktop", "/a/../b", "/", "/a\tb"):
            with self.subTest(value=value):
                self.set_rules(plain=[value])
                with self.assertRaises(ConfigError):
                    self.policy()

    def test_invalid_utf8_path_is_rejected_before_a_transfer_manifest(self):
        with self.assertRaises(ConfigError):
            MODULE["absolute_path"]("/invalid-\udcff-name")

    def test_missing_selected_root_blocks_scan(self):
        self.set_rules(plain=[self.home / "missing"])
        self.assertTrue(self.scan().errors)

    def test_missing_excluded_root_does_not_block_scan(self):
        missing = self.home / "missing"
        self.set_rules(plain=[missing], excluded=[missing])
        self.assertFalse(self.scan().errors)

    def test_symlink_directory_is_preserved_and_never_traversed(self):
        outside = self.write(self.home / "outside/sensitive.txt")
        link = self.project / "linked-directory"
        link.symlink_to(outside.parent, target_is_directory=True)
        scan = self.scan()
        entries = {entry.path: entry for entry in scan.entries}
        self.assertFalse(scan.errors)
        self.assertEqual(entries[str(link)].kind, "symlink")
        self.assertNotIn(str(link / outside.name), entries)
        self.assertTrue(scan.warnings)

    def test_selected_broken_symlink_is_preserved_without_following(self):
        link = self.project / "broken"
        link.symlink_to(self.home / "absent-target")
        self.set_rules(plain=[link])
        scan = self.scan()
        self.assertFalse(scan.errors)
        self.assertEqual(len(scan.entries), 1)
        self.assertEqual(scan.entries[0].kind, "symlink")

    def test_env_symlink_is_guarded_before_any_rclone_suffix(self):
        link = self.project / "linked/.env"
        link.parent.mkdir()
        link.symlink_to(self.normal)
        self.assertEqual(self.action(link), "skip")
        scan = self.scan()
        self.assertEqual(next(entry for entry in scan.entries if entry.path == str(link)).decision.action, "skip")

    def test_hardlink_cannot_expose_private_file_through_plain_name(self):
        key = self.write(self.home / "private/credential")
        alias = self.project / "credential-copy"
        os.link(key, alias)
        self.set_rules(plain=[self.project], private=[key])
        self.assertTrue(any("normale e privato" in error for error in self.scan().errors))

    def test_observed_protected_file_cannot_escape_via_hardlink_name(self):
        os.link(self.env, self.project / "innocent-name")
        self.assertTrue(any("alias di un file con nome protetto" in error for error in self.scan().errors))

    def test_state_is_implicitly_excluded_even_with_exact_entry(self):
        state = self.write(self.home / ".local/state/macbackup/plan.json")
        self.set_rules(plain=[state], private=[state])
        self.assertEqual(self.action(state), "skip")

    def test_rclone_configuration_must_be_private_or_excluded(self):
        credential = self.write(self.home / ".config/rclone/rclone.conf")
        self.set_rules(plain=[credential.parent])
        self.assertEqual(self.action(credential), "error")
        self.assertTrue(self.scan().errors)
        self.set_rules(plain=[credential.parent], private=[credential.parent])
        self.assertEqual(self.action(credential), "private")
        self.assertFalse(self.scan().errors)

    def test_rclone_guard_also_covers_symlinked_config_target(self):
        credential = self.write(self.home / ".dotfiles/rclone/rclone.conf")
        alias = self.home / ".config/rclone"
        alias.symlink_to(credential.parent, target_is_directory=True)
        self.set_rules(plain=[credential.parent])
        self.assertEqual(self.action(credential), "error")

    def test_individual_rclone_file_can_be_private_under_normal_parent(self):
        credential = self.write(self.home / ".config/rclone/rclone.conf")
        self.set_rules(plain=[credential.parent], private=[credential])
        self.assertFalse(self.scan().errors)

    def test_unreadable_file_blocks_scan(self):
        original = os.access
        with patch.object(os, "access", side_effect=lambda path, mode: False if path == self.normal else original(path, mode)):
            self.assertTrue(any("non leggibile" in error for error in self.scan().errors))

    def test_symlink_loop_does_not_get_traversed(self):
        link = self.project / "loop"
        link.symlink_to(link)
        scan = self.scan()
        self.assertFalse(scan.errors)
        self.assertEqual(next(entry for entry in scan.entries if entry.path == str(link)).kind, "symlink")

    def test_directory_replaced_with_symlink_during_scan_is_rejected(self):
        candidate = self.project / "swappable"
        candidate.mkdir()
        outside = self.write(self.home / "outside/not-selected.txt")
        original = os.open
        replaced = False

        def replace_before_open(path, flags, *args, **kwargs):
            nonlocal replaced
            if path == "swappable" and not replaced:
                replaced = True
                candidate.rename(self.project / "old-directory")
                candidate.symlink_to(outside.parent, target_is_directory=True)
            return original(path, flags, *args, **kwargs)

        with patch.object(os, "open", side_effect=replace_before_open):
            scan = self.scan()
        self.assertTrue(replaced)
        self.assertTrue(scan.errors)
        self.assertFalse(any(entry.path.endswith("swappable/not-selected.txt") for entry in scan.entries))

    def test_reserved_rclonelink_filename_blocks_scan(self):
        self.write(self.project / "real-file.rclonelink")
        self.assertTrue(any("nome riservato" in error for error in self.scan().errors))

    def test_special_file_is_skipped_and_explicit_special_root_is_error(self):
        fifo = self.project / "pipe"
        os.mkfifo(fifo)
        scan = self.scan()
        self.assertFalse(scan.errors)
        self.assertTrue(scan.warnings)
        self.set_rules(plain=[fifo])
        self.assertTrue(self.scan().errors)

    def test_preview_does_not_read_source_file_contents(self):
        original = Path.open
        source_paths = {self.normal, self.env, self.env_local, self.nested}

        def checked_open(path, *args, **kwargs):
            if path in source_paths:
                raise AssertionError("Source contents must not be opened")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", checked_open):
            self.assertFalse(self.scan().errors)

    def test_init_never_overwrites_partial_or_existing_configuration(self):
        sentinel = (self.config / "plain-paths.txt").read_bytes()
        with self.assertRaises(ConfigError):
            init_config(self.config, self.home)
        self.assertEqual((self.config / "plain-paths.txt").read_bytes(), sentinel)

    def test_init_creates_empty_selections_and_restrictive_permissions(self):
        path = self.home / "new-config"
        init_config(path, self.home)
        policy = Policy(path, self.home)
        self.assertEqual(policy.roots, [])
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for filename in MODULE["CONFIG_FILES"]:
            self.assertEqual((path / filename).stat().st_mode & 0o777, 0o600)

    def cli(self, *args):
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--config-dir", str(self.config), *args],
            capture_output=True, text=True, env=env,
        )

    def test_cli_explain_reports_the_blocking_pattern(self):
        result = self.cli("explain", str(self.env), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["action"], "skip")
        self.assertEqual(data["protected_pattern"], ".env")

    def test_cli_preview_fails_closed_on_missing_root(self):
        self.set_rules(plain=[self.project, self.home / "missing"])
        result = self.cli("preview", "--local", "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["entries"], [])
        self.assertFalse(data["ok"])

    def test_cli_preview_requires_explicit_local_mode(self):
        self.assertEqual(self.cli("preview").returncode, 2)

    def test_cli_unimplemented_cloud_commands_are_unavailable(self):
        for name in ("forget", "restore", "verify"):
            with self.subTest(name=name):
                self.assertEqual(self.cli(name).returncode, 2)

    def test_cli_run_requires_explicit_target(self):
        self.assertEqual(self.cli("run").returncode, 2)

    def test_cli_missing_pattern_file_returns_structured_error(self):
        (self.config / "explicit-only-patterns.txt").unlink()
        result = self.cli("check", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_cli_preview_routes_exact_env_privately_without_duplicate_plain_copy(self):
        self.set_rules(plain=[self.project], private=[self.env])
        result = self.cli("preview", "--local", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = json.loads(result.stdout)["entries"]
        matches = [entry for entry in entries if entry["path"] == str(self.env)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["action"], "private")


if __name__ == "__main__":
    unittest.main()
