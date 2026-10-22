import sys
from pathlib import Path
import tempfile
import unittest
import hashlib
import json
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import titbit_assets
from package_web import RUNTIME, package


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / 'build'
        self.build.mkdir()
        for name in RUNTIME:
            (self.build / name).write_bytes(name.encode())

    def test_only_runtime_is_published(self):
        for name in ('QUEST.ezd', 'intro.avi', 'slot1.sav', 'build.log', 'toolchain.json'):
            (self.build / name).write_bytes(b'private fixture')
        target = self.root / 'site'
        package(self.build, target)
        self.assertEqual({p.name for p in target.iterdir()}, set(RUNTIME) | {'index.html', '.nojekyll'})
        self.assertEqual((target / 'index.html').read_bytes(), (self.build / 'game.html').read_bytes())
        self.assertFalse(any(p.is_symlink() for p in target.iterdir()))

    def test_rejects_existing_output_or_build_directory(self):
        target = self.root / 'site'
        target.mkdir()
        (target / 'slot1.sav').write_bytes(b'private fixture')
        with self.assertRaises(ValueError):
            package(self.build, target)
        with self.assertRaises(ValueError):
            package(self.build, self.build / 'site')

    def test_missing_runtime_fails_before_creating_site(self):
        (self.build / 'titbit.wasm').unlink()
        target = self.root / 'site'
        with self.assertRaises(FileNotFoundError):
            package(self.build, target)
        self.assertFalse(target.exists())

    def fixture_assets(self):
        data = self.root / 'game'
        data.mkdir()
        records = {}
        for name in ['QUEST.ezd'] + [f'video{i}.avi' for i in range(18)]:
            content = name.encode()
            (data / name).write_bytes(content)
            records[name] = dict(size=len(content), sha256=hashlib.sha256(content).hexdigest())
        manifest = self.root / 'assets.json'
        manifest.write_text(json.dumps(dict(version=1, files=records)))
        return data, manifest

    def test_explicit_bundle_copies_only_verified_game_files(self):
        data, manifest = self.fixture_assets()
        (data / 'slot1.sav').write_bytes(b'private fixture')
        target = self.root / 'site'
        with patch.object(titbit_assets, 'MANIFEST', manifest):
            package(self.build, target, data)
        files = json.loads((target / 'game-assets.json').read_text())['files']
        self.assertEqual(len(files), 19)
        self.assertEqual({p.name for p in (target / 'assets').iterdir()}, {f['name'] for f in files})
        self.assertFalse((target / 'assets/slot1.sav').exists())

    def test_corrupt_game_data_is_not_published(self):
        data, manifest = self.fixture_assets()
        (data / 'QUEST.ezd').write_bytes(b'corrupt')
        target = self.root / 'site'
        with patch.object(titbit_assets, 'MANIFEST', manifest), self.assertRaises(ValueError):
            package(self.build, target, data)
        self.assertFalse(target.exists())
