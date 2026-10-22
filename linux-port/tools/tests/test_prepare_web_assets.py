import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_web_assets import download, prepare


class AssetDownloadTests(unittest.TestCase):
    def test_no_secret_keeps_file_selection_without_creating_data(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'data'
            prepare(target)
            self.assertFalse(target.exists())
            target.mkdir()
            with self.assertRaises(ValueError):
                prepare(target)

    def test_secret_is_stdin_only_and_removed_from_child_environment(self):
        secret = 'magnet:?xt=urn:btih:' + 'a' * 40
        with patch.dict(os.environ, {'TITBIT_GAME_MAGNET': secret}), \
             patch('prepare_web_assets.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            download(secret, Path('/tmp/download'))
        args, options = run.call_args
        self.assertNotIn(secret, str(args))
        self.assertEqual(options['input'], secret + '\n')
        self.assertNotIn('TITBIT_GAME_MAGNET', options['env'])
        self.assertEqual(options['stdout'], subprocess.DEVNULL)
        self.assertEqual(options['stderr'], subprocess.DEVNULL)

    def test_invalid_input_never_starts_downloader(self):
        with patch('prepare_web_assets.subprocess.run') as run:
            for value in ['https://example.com/game', 'magnet:?xt=a\nmalicious-option']:
                with self.assertRaises(ValueError):
                    download(value, Path('/tmp/download'))
            run.assert_not_called()
