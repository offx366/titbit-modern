"""Automatic mod selection, migration and saves across monitor changes."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import titbit_mods as mods
import titbit_profiles as profiles
import titbit_launcher as launcher


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base=self.root/'game';self.base.mkdir()
        self.store=self.root/'data';self.engine=self.root/'engine.exe';self.engine.write_bytes(b'MZ engine')
        (self.base/'QUEST.ezd').write_bytes(b'ORIGINAL');(self.base/'intro.avi').write_bytes(b'VIDEO')
        (self.base/'slot1.sav').write_bytes(b'BASE SAVE')
        manifest={p.name:dict(size=p.stat().st_size,sha256=mods.sha(p)) for p in self.base.iterdir() if p.suffix!='.sav'}
        p=patch.object(mods.assets,'manifest',return_value=manifest);p.start();self.addCleanup(p.stop)
        p=patch.object(mods,'catalog',return_value=dict(testedEngines={'windows':mods.sha(self.engine),'linux':mods.sha(self.engine)}));p.start();self.addCleanup(p.stop)
        self.variant('16x9',b'WIDE NINE');self.variant('16x10',b'WIDE TEN')

    def variant(self,ratio,data):
        p=self.store/'profiles'/('widescreen-'+ratio);p.mkdir(parents=True)
        (p/'QUEST.ezd').write_bytes(data);(p/'widescreen-scenes.txt').write_text('street.XML')
        (p/'slot1.sav').write_bytes(b'OLD VARIANT SAVE')
        mods.write_json(p/'mod.json',dict(version=mods.VERSION,recipe=mods.RECIPE,archiveSha256=mods.sha(p/'QUEST.ezd')))
        return p

    def test_automatic_shape_uses_monitor_or_explicit_resolution(self):
        for wh,result in [((1920,1080),'16x9'),((1920,1200),'16x10'),((3440,1440),'16x9'),((1280,1024),'16x10')]:
            self.assertEqual(profiles.automatic_ratio(*wh),result)
        self.assertEqual(profiles.automatic_ratio(1920,1080,'1920x1200'),'16x10')

    def test_preferences_migrate_without_touching_old_file(self):
        mods.write_json(self.store/'launcher.json',dict(mode='16x10',data=str(self.base),display='windowed'))
        before=(self.store/'launcher.json').read_bytes()
        self.assertEqual(profiles.preferences(self.store,self.base)['enabledMods'],['widescreen'])
        self.assertEqual((self.store/'launcher.json').read_bytes(),before)
        mods.write_json(self.store/'launcher.json',dict(enabledMods=['future','widescreen','future']))
        self.assertEqual(profiles.preferences(self.store,self.base)['enabledMods'],['future','widescreen'])

    def test_saves_survive_ratio_switch_and_original_stays_untouched(self):
        one=profiles.prepare(self.base,self.store,self.engine,['widescreen'],'16x9','windowed')
        profile=Path(one['profile']);self.assertEqual(profile.name,'widescreen')
        self.assertEqual((profile/'slot1.sav').read_bytes(),b'OLD VARIANT SAVE')
        (profile/'slot1.sav').write_bytes(b'LATEST PLAYER SAVE')
        two=profiles.prepare(self.base,self.store,self.engine,['widescreen'],'16x10','windowed')
        self.assertEqual(one['profile'],two['profile'])
        self.assertEqual((profile/'QUEST.ezd').read_bytes(),b'WIDE TEN')
        self.assertEqual((profile/'slot1.sav').read_bytes(),b'LATEST PLAYER SAVE')
        self.assertEqual((self.base/'QUEST.ezd').read_bytes(),b'ORIGINAL')
        self.assertEqual((self.base/'slot1.sav').read_bytes(),b'BASE SAVE')
        original=profiles.prepare(self.base,self.store,self.engine,[],'16x10','windowed')
        self.assertNotEqual(original['profile'],two['profile'])
        self.assertEqual((Path(original['profile'])/'slot1.sav').read_bytes(),b'BASE SAVE')

    def test_remove_and_reinstall_restores_active_saves_before_old_variants(self):
        launch=profiles.prepare(self.base,self.store,self.engine,['widescreen'],'16x9','windowed')
        (Path(launch['profile'])/'slot1.sav').write_bytes(b'LATEST PLAYER SAVE')
        backups=profiles.remove_widescreen(self.store)
        self.assertEqual(len(backups),3)
        self.assertFalse(profiles.has_widescreen(self.store))
        self.assertTrue(any((b/'slot1.sav').read_bytes()==b'LATEST PLAYER SAVE' for b in backups))
        self.variant('16x9',b'WIDE NINE')
        launch=profiles.prepare(self.base,self.store,self.engine,['widescreen'],'16x9','windowed')
        self.assertEqual((Path(launch['profile'])/'slot1.sav').read_bytes(),b'LATEST PLAYER SAVE')

    def test_unknown_mod_is_not_silently_omitted(self):
        with self.assertRaisesRegex(ValueError,'future-mod'):
            profiles.prepare(self.base,self.store,self.engine,['widescreen','future-mod'],'16x9')

    def test_single_entry_layout_and_legacy_preferences(self):
        bundle=self.root/'player';(bundle/'bin').mkdir(parents=True)
        (bundle/'bin/TitbitGame.exe').write_bytes(b'MZ engine')
        with patch.object(launcher,'BUNDLE',bundle):
            if launcher.os.name=='nt':
                data,store,engine=launcher.defaults()
                self.assertEqual(engine,bundle/'bin/TitbitGame.exe');self.assertEqual(store,bundle/'data')
                (bundle/'TitbitLauncher-data').mkdir()
                self.assertEqual(launcher.defaults()[1],bundle/'TitbitLauncher-data')


if __name__=='__main__':unittest.main()
