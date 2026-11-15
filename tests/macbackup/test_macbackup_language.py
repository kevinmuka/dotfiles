"""Language changes presentation without changing paths or data contracts."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[2] / 'home/.config/scripts/macbackup'
M = runpy.run_path(str(SCRIPT))


class LanguageTests(unittest.TestCase):
    def test_english_is_default_and_italian_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(M['localized']('Local check complete.'),
                             'Local check complete.')
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'it'}):
            self.assertEqual(M['localized']('Local check complete.'),
                             'Controllo locale completato.')

    def test_path_words_are_not_translated(self):
        line = 'WARNING: /Users/example/Verifica file/Avvio lavoro: symlink; target not traversed.'
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'it'}):
            result = M['localized'](line)
        self.assertIn('/Users/example/Verifica file/Avvio lavoro', result)
        self.assertIn('AVVISO:', result)
        self.assertIn('collegamento; destinazione non attraversata.', result)
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'it'}):
            preview = M['localized']('PLAIN /Users/example/Verifica file [file] — Plain inclusion.')
        self.assertIn('/Users/example/Verifica file', preview)
        self.assertIn('Inclusione normale.', preview)

    def test_json_keys_and_path_values_stay_stable(self):
        report = {'reason': 'Plain inclusion.', 'path': '/Users/example/Verifica file',
                  'archive_deleted': 2, 'note': 'Results separated by target and area.'}
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'it'}):
            result = M['localized_json'](report)
        self.assertEqual(set(result), set(report))
        self.assertEqual(result['path'], report['path'])
        self.assertEqual(result['archive_deleted'], 2)
        self.assertEqual(result['reason'], 'Inclusione normale.')

    def test_structured_warning_preserves_path_words(self):
        template = '{source}:{line}: {path} suspended by {other_source}:{other_line}: {other_path}.'
        values = {'source': 'plain-paths.txt', 'line': 1,
                  'path': '/Users/example/suspended by project',
                  'other_source': 'exclude-paths.txt', 'other_line': 2,
                  'other_path': '/Users/example/excluded'}
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'en'}):
            english = M['message'](template, **values)
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'it'}):
            italian = M['message'](template, **values)
        self.assertIn('/Users/example/suspended by project', english)
        self.assertIn('/Users/example/suspended by project', italian)
        self.assertIn('suspended by exclude-paths.txt:2:', english)
        self.assertIn('sospeso da exclude-paths.txt:2:', italian)

    def test_init_templates_use_selected_language(self):
        for language, expected in (
            ('en', '# Directories have trailing /'),
            ('it', '# Directory con / finale'),
        ):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / 'config'
                env = os.environ.copy() | {'MACBACKUP_LANG': language}
                result = subprocess.run([sys.executable, '-B', str(SCRIPT),
                                         '--config-dir', str(config), 'init'],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((config / 'plain-paths.txt').read_text().startswith(expected))

    def test_dynamic_messages_keep_existing_italian_wording(self):
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'it'}):
            self.assertEqual(M['localized']('Mount google/all failed: no response from rclone.'),
                             'Montaggio google/all fallito: nessuna risposta da rclone.')
            self.assertEqual(M['localized']('Archiving due to policy google/plain'),
                             'Archiviazione policy google/plain')
            self.assertEqual(M['localized']('Could not read metadata Icon'),
                             'Impossibile leggere il metadato Icon')
            self.assertEqual(M['localized']('Inventory google/plain: unexpected format.'),
                             'Inventario google/plain: formato inatteso.')
            self.assertEqual(M['localized']('rclone exited with code 1: see messages above.'),
                             'rclone è terminato con codice 1: vedere i messaggi sopra.')
            self.assertEqual(M['localized']('google/plain: 101 archives across files and icons '
                                            'exceed max_delete=100; no transfers started.'),
                             'google/plain: 101 archiviazioni tra file e icone '
                             'superano max_delete=100; nessun trasferimento avviato.')
            self.assertEqual(M['localized']('explicit-only-patterns.txt:1 (.git/) and '
                                            'settings.toml:[policy].private_directory_names '
                                            '(.git): redundant rules.'),
                             'explicit-only-patterns.txt:1 (.git/) e '
                             'settings.toml:[policy].private_directory_names '
                             '(.git): regole ridondanti.')

    def test_status_keeps_saved_language_and_no_report_uses_active_language(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            state = home / '.local/state/macbackup'
            state.mkdir(parents=True)
            report = {'ok': True, 'note': 'Esiti distinti per destinazione e area.'}
            file = state / 'last-run.json'
            file.write_text(json.dumps(report))
            env = os.environ.copy() | {'HOME': str(home), 'MACBACKUP_LANG': 'en'}
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), 'status'],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), report)
            self.assertEqual(json.loads(file.read_text()), report)
            file.unlink()
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), 'status'],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)['note'],
                             'No run recorded. No backup certified.')


if __name__ == '__main__':
    unittest.main()
