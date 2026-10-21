"""Validate capture provenance without starting a game or an X server."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PIL import Image

SCRIPT=Path(__file__).resolve().parents[1]/'widescreen_validate.py'
spec=importlib.util.spec_from_file_location('widescreen_validate_under_test',SCRIPT)
subject=importlib.util.module_from_spec(spec);spec.loader.exec_module(subject)


class CaptureProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'data';self.data.mkdir()
        (self.data/'QUEST.ezd').write_bytes(b'archive-A')
        self.exe=self.root/'titbit';self.exe.write_bytes(b'exe-A')
        self.scenes=self.root/'scenes.txt';self.scenes.write_text('one.XML\ntwo.XML\n')
        self.allowlist=self.root/'allowlist.txt';self.allowlist.write_text('one.XML\ntwo.XML\n')
        self.out=self.root/'captures';self.calls=[]

    def probe(self,command,**kwargs):
        self.calls.append(command)
        def value(name):return command[command.index(name)+1]
        directory=Path(value('--out'));directory.mkdir(parents=True,exist_ok=True)
        scene=value('--scene')
        Image.new('RGB',(4,4),'white').save(directory/'frame-00000008.ppm')
        evidence={'passed':True,'exitCode':0,'executableSha256':subject.file_digest(self.exe),
                  'privateXvfb':True,'widescreen':value('--widescreen'),'validationScene':scene,
                  'requiredScenesLoaded':True,'scenesLoaded':[scene],'worldExpanded':True,
                  'images':[{'nonblackPixels':16}]}
        (directory/'report.json').write_text(json.dumps(evidence))
        return SimpleNamespace(returncode=0)

    def run_main(self,resume=False,probe=None):
        arguments=[str(SCRIPT),'--data',str(self.data),'--exe',str(self.exe),'--scenes',str(self.scenes),
                   '--allowlist',str(self.allowlist),'--out',str(self.out)]
        if resume:arguments.append('--resume')
        with patch.object(sys,'argv',arguments),patch.object(subject.subprocess,'run',probe or self.probe),contextlib.redirect_stdout(io.StringIO()):
            return subject.main()

    def summary(self):return json.loads((self.out/'report.json').read_text())

    def test_unchanged_completed_attempts_resume_without_launch(self):
        self.assertEqual(self.run_main(),0);self.assertEqual(len(self.calls),2)
        self.assertEqual(self.run_main(resume=True),0);self.assertEqual(len(self.calls),2)
        self.assertTrue(all(row['resumed'] for row in self.summary()['scenes']))

    def test_changed_nonresume_interrupted_then_resume_does_not_reuse_old_scene(self):
        self.assertEqual(self.run_main(),0)
        self.exe.write_bytes(b'exe-B')
        def interrupted(command,**kwargs):
            if command[command.index('--scene')+1]=='two.XML':raise KeyboardInterrupt
            return self.probe(command,**kwargs)
        with self.assertRaises(KeyboardInterrupt):self.run_main(probe=interrupted)
        self.calls.clear()
        self.assertEqual(self.run_main(resume=True),0)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][self.calls[0].index('--scene')+1],'two.XML')
        rows=self.summary()['scenes'];self.assertTrue(rows[0]['resumed']);self.assertFalse(rows[1]['resumed'])
        for row in rows:
            report=json.loads((self.out/row['evidence']).read_text())
            self.assertEqual(report['executableSha256'],subject.file_digest(self.exe))
        self.assertEqual(len(list((self.out/'02-two.XML/runs').iterdir())),3)

    def test_failed_subprocess_cannot_reuse_a_success_looking_report(self):
        def failed(command,**kwargs):
            self.probe(command,**kwargs);return SimpleNamespace(returncode=7)
        self.assertEqual(self.run_main(probe=failed),1)
        self.assertTrue(all(not row['passed'] for row in self.summary()['scenes']))
        self.calls.clear();self.assertEqual(self.run_main(resume=True),0);self.assertEqual(len(self.calls),2)

    def test_missing_report_cannot_pick_an_older_attempt(self):
        self.assertEqual(self.run_main(),0)
        self.assertEqual(self.run_main(probe=lambda *args,**kwargs:SimpleNamespace(returncode=1)),1)
        self.assertTrue(all(not row['passed'] and row['screenshot'] is None for row in self.summary()['scenes']))

    def test_changed_cached_report_is_retried(self):
        self.assertEqual(self.run_main(),0)
        first=self.summary()['scenes'][0]
        report=self.out/first['evidence'];report.write_text(report.read_text()+' ')
        self.calls.clear();self.assertEqual(self.run_main(resume=True),0);self.assertEqual(len(self.calls),1)

    def test_changed_cached_screenshot_is_retried(self):
        self.assertEqual(self.run_main(),0)
        first=self.summary()['scenes'][0]
        screenshot=self.out/first['screenshot'];screenshot.write_bytes(b'changed')
        self.calls.clear();self.assertEqual(self.run_main(resume=True),0);self.assertEqual(len(self.calls),1)


if __name__=='__main__':unittest.main()
