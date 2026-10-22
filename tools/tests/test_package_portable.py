"""Publication boundary: unrelated game data and saves must never enter the ZIP."""
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import package_portable


class PortableBoundaryTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PyInstaller'), 'Install requirements-build.txt to test packaging')
    def test_existing_player_data_is_not_packaged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); game=root/'game'; game.mkdir(); tools=root/'tools';tools.mkdir()
            for name in ('TitbitModern.exe','TitbitSettings.exe'):
                (game/name).write_bytes(b'MZ synthetic game executable')
            for name in ('TitbitSetup.exe','TitbitStudio.exe','TitbitLauncher.exe'):
                (tools/name).write_bytes(b'MZ synthetic tool executable')
            for name in ('QUEST.ezd','intro.avi','save01.sav','private.txt','TitbitStudio.json'):
                (game/name).write_bytes(b'USER DATA MUST STAY LOCAL')
            archive=package_portable.assemble(game,tools,root/'out','boundary-test')
            with zipfile.ZipFile(archive) as z:
                names=z.namelist()
                self.assertFalse(any(Path(n).suffix.lower() in ('.ezd','.avi','.sav') for n in names))
                self.assertNotIn('TitbitModern/private.txt',names)
                self.assertNotIn('TitbitModern/TitbitStudio.json',names)
                self.assertIn('TitbitModern/editor/README.md',names)
                self.assertIn('TitbitModern/docs/GETTING_STARTED.md',names)
                self.assertFalse(json.loads(z.read('TitbitModern/package.json'))['originalDataIncluded'])
                self.assertEqual([n for n in names if Path(n).suffix=='.exe' and n.count('/')==1],['TitbitModern/Titbit.exe'])
                self.assertIn('TitbitModern/bin/TitbitGame.exe',names)
                self.assertNotIn('TitbitModern/TitbitSetup.exe',names)
                for n in names:
                    self.assertNotIn(b'USER DATA MUST STAY LOCAL',z.read(n))
            self.assertEqual((game/'save01.sav').read_bytes(),b'USER DATA MUST STAY LOCAL')


if __name__=='__main__':unittest.main()
