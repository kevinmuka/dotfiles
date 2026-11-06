"""Scoped forget plans against disposable local and crypt rclone remotes."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / 'home/.config/scripts/macbackup'


@unittest.skipUnless(shutil.which('rclone'), 'rclone is needed')
class ForgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.config = self.home / '.config/macbackup'
        self.config.mkdir(parents=True)
        for name in ('plain-paths.txt', 'private-paths.txt', 'exclude-paths.txt'):
            (self.config / name).write_text('')
        (self.config / 'explicit-only-patterns.txt').write_text('.env\n.env.*\n')
        (self.config / 'settings.toml').write_text(
            'schema_version = 1\nmax_delete = 25\n'
            '[targets.google]\nenabled = false\n'
            'plain = "localplain:MacBackup/plain"\nprivate = "localcrypt:"\n'
            '[targets.proton]\nenabled = false\n'
            'plain = "missing:MacBackup/plain"\nprivate = "missingcrypt:"\n'
        )
        password = subprocess.run(['rclone', 'obscure', 'synthetic-forget-password'],
                                  capture_output=True, text=True, check=True).stdout.strip()
        self.rclone_config = self.base / 'rclone.conf'
        self.rclone_config.write_text(
            '[localplain]\ntype = alias\nremote = ' + str(self.base / 'plain-store') + '\n'
            '[localcrypt]\ntype = crypt\nremote = ' + str(self.base / 'crypt-store') + '\n'
            'password = ' + password + '\nfilename_encryption = standard\n'
            'directory_name_encryption = true\n'
        )
        self.rclone_config.chmod(0o600)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('RCLONE_')}
        self.env.update(HOME=str(self.home), RCLONE_CONFIG=str(self.rclone_config))
        self.original = self.home / 'Desktop/project/secret.txt'
        self.plain = self.base / 'plain-store/MacBackup/plain'

    def cli(self, *args):
        return self.invoke('forget', *args)

    def invoke(self, command, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--config-dir', str(self.config),
                               command, *args], env=self.env, capture_output=True, text=True)

    def plan(self, path=None, area='plain', mode='trash'):
        result = self.cli(path or str(self.original), '--target', 'google', '--area', area,
                          '--mode', mode, '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def apply(self, plan):
        return self.cli('--plan', plan['plan_id'], '--apply', '--json')

    def make_plain(self, location='current', name=None, content='synthetic v1'):
        path = self.plain / location / (name or str(self.original).lstrip('/'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_plan_is_read_only_and_apply_removes_current_and_every_history(self):
        current = self.make_plain()
        old1 = self.make_plain('history/run-one')
        old2 = self.make_plain('history/run-two')
        other = self.make_plain(name=str(self.original.parent / 'other.txt').lstrip('/'))
        plan = self.plan()
        self.assertEqual(plan['count'], 3)
        self.assertTrue(all(path.exists() for path in (current, old1, old2, other)))
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['removed_from_active_backup']), 3)
        self.assertTrue(other.exists())
        self.assertFalse(any(path.exists() for path in (current, old1, old2)))
        self.assertNotEqual(self.apply(plan).returncode, 0)

    def test_new_or_changed_remote_copy_invalidates_plan_before_deletion(self):
        current = self.make_plain()
        plan = self.plan()
        current.write_text('a changed synthetic file with another size')
        result = self.apply(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(current.exists())
        self.assertIn('changed', result.stdout)

    def test_new_matching_history_invalidates_plan_before_deletion(self):
        current = self.make_plain()
        plan = self.plan()
        history = self.make_plain('history/new-run')
        result = self.apply(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(current.exists())
        self.assertTrue(history.exists())

    def test_expired_plan_does_not_delete_anything(self):
        current = self.make_plain()
        plan = self.plan()
        file = self.home / '.local/state/macbackup/forget-plans' / (plan['plan_id'] + '.json')
        data = json.loads(file.read_text())
        data['expires_at'] = 0
        file.write_text(json.dumps(data))
        result = self.apply(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(current.exists())
        self.assertIn('expired', result.stdout)

    def test_excluded_source_is_still_found(self):
        current = self.make_plain()
        (self.config / 'exclude-paths.txt').write_text(str(self.original.parent) + '\n')
        plan = self.plan()
        self.assertEqual(plan['count'], 1)
        self.assertFalse(plan['selected_locally'])
        self.assertTrue(current.exists())

    def test_subtree_is_boundary_safe_and_includes_icon_sidecars(self):
        current = self.make_plain()
        old = self.make_plain('history/run-one')
        sibling = self.make_plain(name=str(self.original.parent) + '-other/file.txt')
        icon = self.plain / 'macos-icons/current' / str(self.original.parent).lstrip('/') / 'icon.json'
        icon.parent.mkdir(parents=True)
        icon.write_text('{"synthetic":true}')
        plan = self.plan(str(self.original.parent) + '/')
        self.assertEqual(plan['count'], 3)
        self.assertEqual({item['kind'] for item in plan['items']}, {'files', 'macos-icons'})
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['empty_directory_roots_removed']), 3)
        self.assertFalse(current.parent.exists())
        self.assertFalse(old.parent.exists())
        self.assertFalse(icon.parent.exists())
        self.assertTrue(sibling.exists())

    def test_empty_directory_only_can_be_planned_and_removed(self):
        current = self.plain / 'current' / str(self.original.parent).lstrip('/')
        history = self.plain / 'history/run-one' / str(self.original.parent).lstrip('/')
        current.mkdir(parents=True)
        history.mkdir(parents=True)
        sibling = self.make_plain(name=str(self.original.parent) + '-other/file.txt')
        plan = self.plan(str(self.original.parent) + '/')
        self.assertEqual(plan['count'], 0)
        self.assertEqual(len(plan['cleanup_roots']), 2)
        self.assertIsNotNone(plan['plan_id'])
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(current.exists())
        self.assertFalse(history.exists())
        self.assertTrue(sibling.exists())

    def test_private_crypt_copy_is_deleted_without_touching_plain(self):
        plain = self.make_plain()
        source = self.base / 'private-source'
        source.write_text('synthetic private content')
        remote = 'localcrypt:current/' + str(self.original).lstrip('/')
        subprocess.run(['rclone', 'copyto', str(source), remote], env=self.env,
                       capture_output=True, text=True, check=True)
        plan = self.plan(area='private')
        self.assertEqual(plan['count'], 1)
        self.assertEqual(plan['items'][0]['area'], 'private')
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(plain.exists())
        self.assertEqual(self.plan(area='private')['count'], 0)

    def test_private_crypt_directory_cleanup_preserves_plain(self):
        plain = self.make_plain()
        source = self.base / 'private-source'
        source.write_text('synthetic private content')
        remote = 'localcrypt:current/' + str(self.original).lstrip('/')
        subprocess.run(['rclone', 'copyto', str(source), remote], env=self.env,
                       capture_output=True, text=True, check=True)
        plan = self.plan(str(self.original.parent) + '/', area='private')
        self.assertEqual(plan['count'], 1)
        result = self.apply(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(plain.exists())
        listing = subprocess.run(['rclone', 'lsjson', 'localcrypt:current/' +
                                  str(self.original.parent.parent).lstrip('/')],
                                 env=self.env, capture_output=True, text=True, check=True)
        self.assertNotIn(self.original.parent.name,
                         [item['Name'] for item in json.loads(listing.stdout)])

    def test_permanent_proton_and_broad_directory_without_slash_are_rejected(self):
        self.make_plain()
        self.original.parent.mkdir(parents=True)
        self.assertNotEqual(self.cli(str(self.original.parent), '--target', 'google',
                                     '--area', 'all', '--mode', 'trash').returncode, 0)
        self.assertNotEqual(self.cli(str(self.original), '--target', 'all',
                                     '--area', 'plain', '--mode', 'permanent').returncode, 0)
        self.assertNotEqual(self.cli(str(self.original), '--target', 'google',
                                     '--area', 'plain', '--mode', 'permanent').returncode, 0)

    def test_versions_and_restore_old_plain_file_without_overwriting_source(self):
        self.make_plain(content='synthetic current')
        self.make_plain('history/run-one', content='synthetic older')
        listing = self.invoke('versions', str(self.original), '--target', 'google', '--json')
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        versions = json.loads(listing.stdout)['versions']
        self.assertEqual({item['version'] for item in versions}, {'current', 'run-one'})
        destination = self.base / 'recovered.txt'
        result = self.invoke('restore', str(self.original), '--target', 'google',
                             '--area', 'plain', '--version', 'run-one', '--to', str(destination), '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(destination.read_text(), 'synthetic older')
        self.assertIn('hash_verified', json.loads(result.stdout))
        self.assertNotEqual(self.invoke('restore', str(self.original), '--target', 'google',
                         '--area', 'plain', '--version', 'current', '--to', str(destination)).returncode, 0)
        self.assertEqual(destination.read_text(), 'synthetic older')
        replaced = self.invoke('restore', str(self.original), '--target', 'google', '--area', 'plain',
                               '--version', 'current', '--to', str(destination), '--replace')
        self.assertEqual(replaced.returncode, 0, replaced.stdout + replaced.stderr)
        self.assertEqual(destination.read_text(), 'synthetic current')

    def test_versions_directory_groups_sparse_history_and_can_show_files(self):
        folder = self.original.parent
        folder.mkdir(parents=True)
        self.make_plain(content='current version')
        other = folder / 'other.txt'
        self.make_plain(name=str(other).lstrip('/'), content='other current')
        self.make_plain('history/run-one', content='old version')
        sibling = folder.parent / 'project-other/unrelated.txt'
        self.make_plain(name=str(sibling).lstrip('/'))
        icon = self.plain / 'macos-icons/current' / str(folder).lstrip('/') / 'icon.json'
        icon.parent.mkdir(parents=True)
        icon.write_text('{"synthetic":true}')

        listing = self.invoke('versions', str(folder), '--target', 'google',
                              '--area', 'plain', '--json')
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        data = json.loads(listing.stdout)
        self.assertEqual(data['kind'], 'directory')
        self.assertEqual([(group['version'], group['count']) for group in data['versions']],
                         [('current', 3), ('run-one', 1)])
        self.assertEqual({item['path'] for group in data['versions'] for item in group['items']},
                         {str(folder), str(self.original), str(other)})
        self.assertIn('not a full directory snapshot', data['note'])
        detailed = self.invoke('versions', str(folder), '--target', 'google',
                               '--area', 'plain', '--files')
        self.assertEqual(detailed.returncode, 0, detailed.stdout + detailed.stderr)
        self.assertIn(str(self.original), detailed.stdout)
        self.assertNotIn(str(other), detailed.stdout)
        self.assertNotIn(str(sibling), detailed.stdout)
        self.assertNotEqual(self.invoke('versions', str(self.original), '--target', 'google',
                                        '--files').returncode, 0)

        folder.rmdir()
        deleted = self.invoke('versions', str(folder) + '/', '--target', 'google',
                              '--area', 'plain', '--json')
        self.assertEqual(deleted.returncode, 0, deleted.stdout + deleted.stderr)
        self.assertEqual(len(json.loads(deleted.stdout)['versions']), 2)

    def test_versions_scopes_remote_queries_without_hashes(self):
        folder = self.original.parent
        folder.mkdir(parents=True)
        self.make_plain()
        self.make_plain('history/run-one')
        real_rclone = shutil.which('rclone')
        shim_dir = self.base / 'bin'
        shim_dir.mkdir()
        shim = shim_dir / 'rclone'
        log = self.base / 'rclone-queries.jsonl'
        shim.write_text(
            '#!' + sys.executable + '\n'
            'import json, os, subprocess, sys\n'
            "with open(os.environ['MACBACKUP_TEST_LOG'], 'a') as out:\n"
            '    out.write(json.dumps(sys.argv[1:]) + "\\n")\n'
            'raise SystemExit(subprocess.call([' + repr(real_rclone) + ', *sys.argv[1:]]))\n'
        )
        shim.chmod(0o755)
        self.env['PATH'] = str(shim_dir) + os.pathsep + self.env.get('PATH', '')
        self.env['MACBACKUP_TEST_LOG'] = str(log)
        result = self.invoke('versions', str(folder), '--target', 'google', '--area', 'plain')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        listings = [call for call in calls if 'lsjson' in call]
        self.assertTrue(listings)
        self.assertFalse(any('--hash' in call or '--original' in call for call in listings))
        self.assertIn('MacBackup/plain/current/' + str(folder).lstrip('/'),
                      '\n'.join(' '.join(call) for call in listings))
        self.assertIn('MacBackup/plain/history/run-one/' + str(folder).lstrip('/'),
                      '\n'.join(' '.join(call) for call in listings))
        self.assertFalse(any('MacBackup/plain/current' == argument for call in listings
                             for argument in call))

    def test_private_restore_and_destination_guards(self):
        source = self.base / 'private-source'
        source.write_text('synthetic private secret')
        remote = 'localcrypt:current/' + str(self.original).lstrip('/')
        subprocess.run(['rclone', 'copyto', str(source), remote], env=self.env,
                       capture_output=True, text=True, check=True)
        listing = self.invoke('versions', str(self.original), '--target', 'google', '--json')
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertEqual([(x['area'], x['version']) for x in json.loads(listing.stdout)['versions']],
                         [('private', 'current')])
        destination = self.base / 'private-recovered.txt'
        result = self.invoke('restore', str(self.original), '--target', 'google', '--area', 'private',
                             '--version', 'current', '--to', str(destination), '--json')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(destination.read_text(), 'synthetic private secret')
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(self.invoke('restore', str(self.original), '--target', 'google',
                         '--area', 'private', '--version', 'current', '--to', str(self.original)).returncode, 0)
        link = self.base / 'linked-dir'
        link.symlink_to(self.base, target_is_directory=True)
        self.assertNotEqual(self.invoke('restore', str(self.original), '--target', 'google',
                         '--area', 'private', '--version', 'current', '--to', str(link / 'bad.txt')).returncode, 0)

    def test_restore_symlink_requires_links_and_preserves_target(self):
        original = self.original.parent / 'config-link'
        stored = self.make_plain(name=str(original).lstrip('/') + '.rclonelink',
                                 content='../dotfiles/home/.config')
        destination = self.base / 'restored-link'
        plain = ('restore', str(original), '--target', 'google', '--area', 'plain',
                 '--version', 'current', '--to', str(destination))
        without = self.invoke(*plain)
        self.assertNotEqual(without.returncode, 0)
        self.assertFalse(destination.is_symlink())
        restored = self.invoke(*plain, '--links', '--json')
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(os.readlink(destination), '../dotfiles/home/.config')
        self.assertEqual(json.loads(restored.stdout)['kind'], 'symlink')
        self.assertTrue(stored.exists())
        self.assertNotEqual(self.invoke(*plain, '--links').returncode, 0)
        regular = self.base / 'regular.txt'
        regular.write_text('old')
        replaced = self.invoke('restore', str(original), '--target', 'google', '--area', 'plain',
                               '--version', 'current', '--to', str(regular), '--links', '--replace')
        self.assertEqual(replaced.returncode, 0, replaced.stdout + replaced.stderr)
        self.assertEqual(os.readlink(regular), '../dotfiles/home/.config')

    def test_restore_private_symlink_and_reject_links_for_regular_file(self):
        original = self.original.parent / 'private-link'
        source = self.base / 'target-text'
        source.write_text('/Users/kevinmuka/.dotfiles/home/.zsh')
        remote = 'localcrypt:current/' + str(original).lstrip('/') + '.rclonelink'
        subprocess.run(['rclone', 'copyto', str(source), remote], env=self.env,
                       capture_output=True, text=True, check=True)
        destination = self.base / 'private-link-restored'
        restored = self.invoke('restore', str(original), '--target', 'google', '--area', 'private',
                               '--version', 'current', '--to', str(destination), '--links')
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertEqual(os.readlink(destination), '/Users/kevinmuka/.dotfiles/home/.zsh')
        self.make_plain()
        self.assertNotEqual(self.invoke('restore', str(self.original), '--target', 'google',
                            '--area', 'plain', '--version', 'current', '--to', str(self.base / 'wrong'),
                            '--links').returncode, 0)
