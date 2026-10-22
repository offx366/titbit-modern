import copy
import io
import unittest

from PIL import Image
from widescreen_exits import dock_exit, projected_bounds, build_exit_replacements
from widescreen_native_overlays import sign_off_atlas


CAMERA=dict(position=[0,0,0],rotation=[0,0,0],fov=90)


def box(x,y,hx,hy):
    return dict(name='exit',lods=[],components=['position'],attributes={'scriptname':'exit.scv'},
                bones=[dict(parent=-1,position=[x,y,-384],rotation=[0,0,0],scale=[1,1,1],
                            center=[0,0,0],bbox=[hx,hy,.00001],radius=0)])


class BoundaryExits(unittest.TestCase):
    def test_left_and_right_keep_hit_width_and_y(self):
        for width in (1366,1230):
            for x,edge in ((-490,'left'),(490,'right')):
                obj=box(x,0,50,150);before=copy.deepcopy(obj)
                result,proof=dock_exit(CAMERA,obj,width)
                original=projected_bounds(CAMERA,obj);wide=proof['wideCanvasBounds']
                self.assertEqual(proof['edge'],edge)
                self.assertAlmostEqual(wide[2]-wide[0],original[2]-original[0],places=4)
                self.assertAlmostEqual(wide[1],original[1],places=4)
                self.assertEqual(obj,before)
                self.assertEqual(result['attributes'],obj['attributes'])
                self.assertLess(wide[0],0) if edge=='left' else self.assertGreater(wide[2],width)

    def test_bottom_covers_new_corners_without_raising_hit_band(self):
        obj=box(0,-355,520,40)
        for width in (1366,1230):
            result,proof=dock_exit(CAMERA,obj,width)
            bounds=proof['wideCanvasBounds'];original=projected_bounds(CAMERA,obj)
            self.assertLess(bounds[0],0);self.assertGreater(bounds[2],width)
            self.assertAlmostEqual(bounds[1],original[1],places=4)
            self.assertAlmostEqual(bounds[3],original[3],places=4)

    def test_doors_meshes_and_interior_boxes_unchanged(self):
        self.assertIsNone(dock_exit(CAMERA,box(-400,0,40,150),1366))
        self.assertIsNone(dock_exit(CAMERA,box(0,0,100,150),1366))
        obj=box(-490,0,50,150);obj['lods']=[{'meatname':'door.meat'}]
        self.assertIsNone(dock_exit(CAMERA,obj,1366))

    def test_scene_edit_preserves_all_other_source_bytes(self):
        raw=(b'<!-- original comments -->\r\n<scene><camera fov="90"/>'
             b'<dynamic_objects><object name="exit" scriptname="exit.scv" selectable="1">'
             b'<position bonecount="1"><bones><bone bone_id="0">'
             b'<position x="-490" y="0" z="-384"/>'
             b'<bbox x="50" y="150" z="0.00001"/>'
             b'</bone></bones></position></object>'
             b'<object name="door"><unknown keep="unchanged"/></object>'
             b'</dynamic_objects></scene>')
        class Source:
            def read(self,name):
                return b'scene.SetCursorType(6);' if name=='exit.scv' else raw
        replacements,proof=build_exit_replacements(Source(),['scene.xml'],1366)
        self.assertEqual(replacements['scene.xml'],raw.replace(b'x="-490"',b'x="-661"'))
        self.assertEqual(len(proof),1)

    def test_sign_dim_only_registered_pixels_preserve_alpha(self):
        for width in (1366,1230):
            im=Image.new('RGBA',(2048,1024),(20,30,40,111));pad=(width-1024)//2
            im.paste((240,10,10,222),(pad+320,475,pad+360,495))
            stream=io.BytesIO();im.save(stream,format='TGA')
            out,proof=sign_off_atlas(stream.getvalue(),width);result=Image.open(io.BytesIO(out))
            self.assertEqual(result.getpixel((pad+330,480)),(41,10,10,222))
            self.assertEqual(result.getpixel((pad+318,480)),im.getpixel((pad+318,480)))
            self.assertEqual(result.getchannel('A').tobytes(),im.getchannel('A').tobytes())
            self.assertTrue(proof['originalTimerAndRotationPreserved'])


if __name__=='__main__':unittest.main()
