"""Exercise real EZD/TGA/MEAT transformations, using synthetic private assets."""
import copy
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from PIL import Image
import widescreen as ws


def archive(rows):
    payloads=[(n,zlib.compress(data),len(data)) for n,data in rows]
    start=16+sum(len(n.encode('cp1251'))+18 for n,_,_ in payloads)
    size=start+sum(len(data) for _,data,_ in payloads)
    directory=bytearray(b'ezd\xff'+struct.pack('<III',len(rows),start,size));offset=start
    for name,data,plain in payloads:
        directory.extend(name.encode('cp1251')+b'\0\0'+struct.pack('<IIII',2,offset,plain,len(data)))
        offset+=len(data)
    return bytes(directory)+b''.join(data for _,data,_ in payloads)


def quad():
    return dict(positions=[-2,-1.5,0,2,-1.5,0,2,1.5,0,-2,1.5,0],normals=[],
        indices=[0,1,2,0,2,3],uv=[0,0,1,0,1,.75,0,0,1,.75,0,.75],uv2=[],uv3=[],
        flags=1,faceMaterials=[0,0],vertexBones=[0]*4)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.work=self.root/'build'
        image=Image.new('RGBA',(1024,1024),(20,190,70,255))
        image.paste((220,10,15,255),(0,256,1024,1024))
        image.putpixel((12,400),(220,10,15,0))
        out=io.BytesIO();image.save(out,format='TGA')
        self.texture=out.getvalue()
        self.mesh=dict(version=20,slotCount=0,materialNames=['back'],parts=[quad()])
        prop=copy.deepcopy(self.mesh);prop['parts'][0]['uv']=[v*.2 for v in quad()['uv']]
        mat=b'MAT'+struct.pack('<IIIIfffBBB',2,0,0,0,.1,0,1,1,0,0)+b'back.tga'.ljust(32,b'\0')
        scene=b'<scene><camera fov="45"/><static_objects><object name="land"><lod meatname="back.meat"/></object></static_objects></scene>'
        self.original=self.root/'QUEST.ezd'
        self.original.write_bytes(archive([('back.tga',self.texture),('back.mat',mat),
            ('back.meat',ws.write_meat(self.mesh)),('prop.meat',ws.write_meat(prop)),
            ('street.xml',scene),('untouched.bin',b'original arbitrary payload')]))
        self.hash=ws.file_hash(self.original)
        self.manifest=ws.extract(self.original,self.work);self.row=self.manifest['textures'][0]

    def tearDown(self):self.tmp.cleanup()

    def test_whole_frame_replacement_and_shared_atlas_users(self):
        center=Image.open(self.work/'source'/self.row['id']/'center.png')
        self.assertEqual(center.getpixel((0,0)),(220,10,15,255))
        generated=self.root/'generated.png';Image.new('RGB',(1366,768),(5,35,230)).save(generated)
        ws.accept(self.work,self.row['id'],generated)
        for ratio,width in ws.RATIOS.items():
            ws.pack(self.work,ratio,require_complete=True)
            mod=ws.Archive(self.work/'mod'/ratio/'QUEST.ezd')
            proof=ws.load(self.work/'mod'/ratio/'proof.json')
            texture_name=proof['dedicatedBackgroundTextures']['back.tga']
            atlas=Image.open(io.BytesIO(mod.read(texture_name))).convert('RGBA');left=(width-1024)//2
            # Full generated center; the reference red pixels must never be pasted back.
            self.assertEqual(atlas.getpixel((left+512,600)),(5,35,230,255))
            self.assertEqual(atlas.getpixel((left+12,400)),(5,35,230,0))
            self.assertEqual(atlas.getpixel((left+5,10)),(20,190,70,255))
            self.assertEqual(mod.read('untouched.bin'),b'original arbitrary payload')
            self.assertEqual(mod.read('back.tga'),self.texture)
            self.assertEqual(mod.read('back.mat'),ws.Archive(self.original).read('back.mat'))
            self.assertEqual(mod.read('prop.meat'),ws.Archive(self.original).read('prop.meat'))
            mesh=ws.parse_meat(mod.read('back.meat'))['parts'][0]
            self.assertEqual(mesh['positions'][:12],quad()['positions'])
            self.assertEqual(mesh['indices'][:6],quad()['indices'])
            self.assertEqual(len(mesh['indices']),18)
            prop=ws.parse_meat(mod.read('prop.meat'))['parts'][0]
            self.assertAlmostEqual(prop['uv'][0],0)
            self.assertAlmostEqual(prop['uv'][2],.2)
            self.assertEqual(len(prop['indices']),6)
            self.assertEqual((self.work/'mod'/ratio/'widescreen-scenes.txt').read_text().strip(),'street.xml')
        self.assertEqual(ws.file_hash(self.original),self.hash)

    def test_collapsed_double_sided_box_is_extended_both_sides(self):
        part=quad();part['positions']*=2;part['vertexBones']*=2
        part['indices'] += [4,6,5,4,7,6]
        part['uv'] += [0,0,1,.75,1,0,0,0,0,.75,1,.75]
        part['faceMaterials'] += [0,0]
        model=ws.plane_model(part);self.assertEqual(model['windings'],[-1,1])
        ws.expand_part(part,model,1366)
        self.assertEqual(len(part['indices']),36)
        self.assertEqual(len(part['uv']),72)

    def test_nonplanar_geometry_is_not_silently_extrapolated(self):
        part=quad();part['positions'][11]=1
        self.assertIsNone(ws.plane_model(part))

    def test_missing_generation_does_not_make_placeholder_mod(self):
        self.assertEqual(ws.pipeline(self.original,self.work,None),3)
        self.assertFalse((self.work/'mod').exists())
        with self.assertRaises(ValueError):ws.pack(self.work,'16x9',True)

    def test_modified_source_is_rejected(self):
        self.original.write_bytes(self.original.read_bytes()+b'x')
        with self.assertRaisesRegex(ValueError,'changed'):ws.pack(self.work,'16x9')

    def test_previous_capture_becomes_stale_after_art_edit_and_repack(self):
        generated=self.root/'generated.png';Image.new('RGB',(1366,768),'blue').save(generated)
        ws.accept(self.work,self.row['id'],generated);ws.pack(self.work,'16x9',True)
        proof=ws.load(self.work/'mod/16x9/proof.json')
        report=self.work/'validation/report.json'
        ws.save(report,dict(inputs=dict(archiveSha256=proof['modSha256'],aspect='16:9'),scenes=[dict(
            scene='street.xml',passed=True,worldExpanded=True,screenshot='scene.png')]))
        ws.import_captures(self.work,'16x9',report)
        self.assertIn('PASS load',(self.work/'report.md').read_text())
        Image.new('RGB',(1366,768),'yellow').save(generated)
        ws.accept(self.work,self.row['id'],generated)
        self.assertIn('STALE CAPTURE',(self.work/'report.md').read_text())
        ws.pack(self.work,'16x9',True)
        with self.assertRaisesRegex(ValueError,'stale'):ws.import_captures(self.work,'16x9',report)

    def test_extract_does_not_rebind_existing_generation_to_another_archive(self):
        another=self.root/'another.ezd';another.write_bytes(self.original.read_bytes()+b'different')
        with self.assertRaisesRegex(ValueError,'another archive'):ws.extract(another,self.work)

    def test_mod_target_cannot_overwrite_input_via_hardlink(self):
        import os
        generated=self.root/'generated.png';Image.new('RGB',(1366,768),'blue').save(generated)
        ws.accept(self.work,self.row['id'],generated)
        target=self.work/'mod/16x9/QUEST.ezd';target.parent.mkdir(parents=True)
        os.link(self.original,target)
        with self.assertRaisesRegex(ValueError,'overwrite the input'):ws.pack(self.work,'16x9',True)
        self.assertEqual(ws.file_hash(self.original),self.hash)

    def test_runtime_cannot_overwrite_input_via_hardlink(self):
        import os
        generated=self.root/'generated.png';Image.new('RGB',(1366,768),'blue').save(generated)
        ws.accept(self.work,self.row['id'],generated);ws.pack(self.work,'16x9',True)
        target=self.work/'runtime/16x9/QUEST.ezd';target.parent.mkdir(parents=True)
        os.link(self.original,target)
        with self.assertRaisesRegex(ValueError,'overwrite the input'):ws.runtime_copy(self.work,'16x9')
        self.assertEqual(ws.file_hash(self.original),self.hash)


if __name__=='__main__':unittest.main()
