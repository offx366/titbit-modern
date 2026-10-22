"""Installer trust boundary, profile isolation and interrupted download behavior."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import titbit_mods as mods


class ModTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def fake_package(self,extra=None,corrupt=False):
        files={f'art/bg{i}.png':b'PNG '+str(i).encode() for i in range(38)}
        files['art/menu.png']=b'MENU'
        m=dict(schema=1,id=mods.MOD_ID,version=mods.VERSION,recipe=mods.RECIPE,
               baseSha256=mods.assets.manifest()['QUEST.ezd']['sha256'],retainedScenes=mods.RETAINED,
               backgrounds=[dict(id=f'bg{i}')for i in range(38)],
               files={k:dict(size=len(v),sha256=hashlib.sha256(v).hexdigest())for k,v in files.items()})
        if corrupt:files['art/menu.png']=b'EVIL'
        if extra:files.update(extra)
        path=self.root/'fake.titbitmod'
        with zipfile.ZipFile(path,'w') as z:
            for k,v in files.items():z.writestr(k,v)
            z.writestr('manifest.json',json.dumps(m))
        return path

    def test_zip_path_and_executable_rejected(self):
        for name in ('../outside.png','/outside.png','C:/outside.png','art\\outside.png','run.py'):
            with self.subTest(name=name),self.assertRaises(ValueError):mods.package_manifest(self.fake_package({name:b'payload'}))
        self.assertFalse((self.root.parent/'outside.png').exists())

    def test_tampered_payload_rejected(self):
        with self.assertRaisesRegex(ValueError,'Повреждён'):mods.package_manifest(self.fake_package(corrupt=True))

    def test_incomplete_and_duplicate_archive_rejected(self):
        p=self.fake_package()
        with zipfile.ZipFile(p,'a')as z:z.writestr('MANIFEST.JSON',b'{}')
        with self.assertRaises(ValueError):mods.package_manifest(p)

    def test_https_redirect_downgrade_rejected(self):
        for u in ('http://example.com/a','file:///tmp/p','https://user:pass@example.com/a'):
            with self.assertRaises(ValueError):mods.secure_url(u)
        with self.assertRaises(ValueError):mods.HTTPSOnly().redirect_request(None,None,302,'',{},'http://example.com')

    def test_bad_download_never_commits_cache(self):
        data=b'wrong bytes'
        record=dict(size=len(data),sha256='0'*64,urls=['https://example.com/mod'])
        response=io.BytesIO(data);response.url=record['urls'][0];response.headers={}
        with patch.object(mods.urllib.request,'build_opener')as factory:
            factory.return_value.open.return_value=response
            with self.assertRaisesRegex(ValueError,'Загрузка не удалась'):mods.download(record,self.root)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_cancel_download_has_no_partial_or_installed_profile(self):
        data=b'mod bytes';event=threading.Event()
        record=dict(size=len(data),sha256=hashlib.sha256(data).hexdigest(),urls=['https://example.com/mod'])
        response=io.BytesIO(data);response.url=record['urls'][0];response.headers={}
        with patch.object(mods.urllib.request,'build_opener')as factory:
            factory.return_value.open.return_value=response
            with self.assertRaises(mods.assets.ImportCancelled):
                mods.download(record,self.root,lambda *_:event.set(),event)
        self.assertFalse(any(self.root.glob('*.titbitmod')))
        self.assertFalse(any(self.root.glob('*.partial')))

    def test_verified_cache_needs_no_network(self):
        raw=b'valid data';h=hashlib.sha256(raw).hexdigest();p=self.root/(h+'.titbitmod');p.write_bytes(raw)
        with patch.object(mods.urllib.request,'build_opener',side_effect=AssertionError('network')):
            self.assertEqual(mods.download(dict(size=len(raw),sha256=h,urls=[]),self.root),p)

    def test_concurrent_writer_rejected(self):
        with mods.locked(self.root):
            with self.assertRaisesRegex(ValueError,'уже использует'):
                with mods.locked(self.root):pass
        with mods.locked(self.root):pass

    def test_remove_retains_saves_and_unknown_files(self):
        p=self.root/'profiles/widescreen-16x9';p.mkdir(parents=True)
        (p/'mod.json').write_text(json.dumps(dict(version=mods.VERSION,recipe=mods.RECIPE)))
        (p/'QUEST.ezd').write_bytes(b'generated');(p/'intro.avi').write_bytes(b'linked media')
        (p/'slot1.sav').write_bytes(b'MY SAVE');(p/'notes.txt').write_text('MY NOTES')
        backup=mods.remove(self.root,'16x9')
        self.assertEqual((backup/'slot1.sav').read_bytes(),b'MY SAVE')
        self.assertEqual((backup/'notes.txt').read_text(),'MY NOTES')
        self.assertFalse((backup/'QUEST.ezd').exists());self.assertFalse((backup/'intro.avi').exists())
        self.assertIsNone(mods.installed(self.root,'16x9'))


if __name__=='__main__':unittest.main()
