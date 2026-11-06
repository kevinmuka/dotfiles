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
            self.assertEqual(M['localized']('Controllo locale completato.'),
                             'Local check complete.')
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'it'}):
            self.assertEqual(M['localized']('Controllo locale completato.'),
                             'Controllo locale completato.')

    def test_path_words_are_not_translated(self):
        line = 'AVVISO: /Users/example/Verifica file/Avvio lavoro: collegamento; destinazione non attraversata.'
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'en'}):
            result = M['localized'](line)
        self.assertIn('/Users/example/Verifica file/Avvio lavoro', result)
        self.assertIn('WARNING:', result)
        self.assertIn('symlink; target not traversed.', result)
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'en'}):
            preview = M['localized']('PLAIN /Users/example/Verifica file [file] — Inclusione normale.')
        self.assertIn('/Users/example/Verifica file', preview)
        self.assertIn('Plain inclusion.', preview)

    def test_json_keys_and_path_values_stay_stable(self):
        report = {'reason': 'Inclusione normale.', 'path': '/Users/example/Verifica file',
                  'archive_deleted': 2, 'note': 'Esiti distinti per destinazione e area.'}
        with patch.dict(os.environ, {'MACBACKUP_LANG': 'en'}):
            result = M['localized_json'](report)
        self.assertEqual(set(result), set(report))
        self.assertEqual(result['path'], report['path'])
        self.assertEqual(result['archive_deleted'], 2)
        self.assertEqual(result['reason'], 'Plain inclusion.')

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
