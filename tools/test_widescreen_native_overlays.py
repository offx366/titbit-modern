import unittest
from widescreen_native_overlays import split_native_patch, retarget_projected_plane, retexture_dense_patch, _triangulate, _area
from formats import write_meat, parse_meat
from PIL import Image
import io


def fixture():
    p=dict(positions=[0.,0.,0., 1.,0.,0., 1.,1.,0., 0.,1.,0.],normals=[],
           indices=[0,1,2,0,2,3],flags=1,faceMaterials=[0,0],
           uv=[0.,0., 1.,0., 0.9,1., 0.,0., 0.9,1., 0.,1.],uv2=[],uv3=[],vertexBones=[0]*4)
    return write_meat(dict(version=20,slotCount=0,materialNames=['native'],parts=[p]))


class NativeOverlays(unittest.TestCase):
    def test_concave_contour_area(self):
        polygon=[(0,0),(4,0),(4,1),(1,1),(1,4),(0,4)]
        self.assertAlmostEqual(sum(abs(_area(t))for t in _triangulate(polygon)),7)

    def test_disconnected_overlap_union_and_non_affine_quad(self):
        src=fixture();polys=[[(100,100),(600,100),(600,500),(100,500)],
                             [(400,300),(800,300),(800,700),(400,700)],
                             [(100,800),(200,800),(200,900),(100,900)]]
        encoded,proof=split_native_patch(src,0,0,polys,lambda p:(p[0],p[1]),'generated',1366)
        p=parse_meat(encoded)['parts'][0];old=parse_meat(src)['parts'][0]
        self.assertEqual(p['positions'][:12],old['positions'])
        self.assertGreater(proof['ringTriangles'],0);self.assertGreater(proof['nativeTriangles'],0)
        self.assertAlmostEqual(proof['nativeUvArea'],(200000+160000-40000+10000)/1024**2,places=8)
        self.assertAlmostEqual(proof['sourceUvArea'],proof['nativeUvArea']+proof['ringUvArea'],places=9)
        for i in range(0,len(p['positions']),3):self.assertEqual(p['positions'][i+2],0.)
        # Retextured ring UV must be the real source-plane projection of XYZ.
        for fi,mi in enumerate(p['faceMaterials']):
            if mi!=1:continue
            for k in range(3):
                vi=p['indices'][fi*3+k];x,y,z=p['positions'][vi*3:vi*3+3]
                u,v=p['uv'][fi*6+k*2:fi*6+k*2+2]
                self.assertAlmostEqual(u,(x*1024+171)/2048,places=6)
                self.assertAlmostEqual(v,y,places=6)

    def test_opposite_winding_is_retained(self):
        mesh=parse_meat(fixture());p=mesh['parts'][0]
        for i in range(0,len(p['indices']),3):
            p['indices'][i+1],p['indices'][i+2]=p['indices'][i+2],p['indices'][i+1]
            uv=p['uv'][i*2:i*2+6];p['uv'][i*2:i*2+6]=uv[:2]+uv[4:]+uv[2:4]
        out,_=split_native_patch(write_meat(mesh),0,0,[[(200,200),(800,200),(800,800),(200,800)]],lambda p:(p[0],p[1]),'gen',1230)
        p=parse_meat(out)['parts'][0]
        for fi,mi in enumerate(p['faceMaterials']):
            xyz=[p['positions'][i*3:i*3+2]for i in p['indices'][fi*3:fi*3+3]]
            self.assertLess(_area(xyz),0)

    def test_projected_sign_keeps_geometry_and_existing_faces(self):
        src=fixture();out,proof=retarget_projected_plane(src,0,0,lambda p:(p[0],p[1]),'gen',1366)
        before=parse_meat(src)['parts'][0];after=parse_meat(out)['parts'][0]
        for k in ('positions','indices','vertexBones','normals'):self.assertEqual(before[k],after[k])
        self.assertEqual(after['faceMaterials'],[1,1]);self.assertTrue(proof['originalScriptsAndCullingUnchanged'])

    def test_degenerate_contour_rejected(self):
        with self.assertRaises(ValueError):split_native_patch(fixture(),0,0,[[(0,0),(0,0),(0,0)]],lambda p:(0,0),'g',1366)

    def test_dense_preserves_native_foreground_alpha_and_unused_region(self):
        src=Image.new('RGBA',(64,64),(11,22,33,211));mask=Image.new('L',(64,64),0)
        mask.paste(255,(10,10,30,30));gen=Image.new('RGB',(2048,1024),(100,120,140))
        def tga(im):
            b=io.BytesIO();im.save(b,format='TGA');return b.getvalue()
        out,proof=retexture_dense_patch(fixture(),0,0,tga(src),mask,tga(gen),lambda p:(p[0],p[1]),1366)
        im=Image.open(io.BytesIO(out)).convert('RGBA')
        self.assertEqual(im.getpixel((20,20)),(11,22,33,211))
        self.assertEqual(im.getpixel((40,20)),(100,120,140,211))
        self.assertEqual(im.getpixel((63,3)),(11,22,33,211)) # outside non-affine source quad
        self.assertTrue(proof['originalForegroundRGBAUnmodified']);self.assertEqual(proof['retainedForegroundPixels'],400)
        self.assertEqual(im.getchannel('A').tobytes(),src.getchannel('A').tobytes())

    def test_dense_rejects_wrong_mask_dimensions(self):
        b=io.BytesIO();Image.new('RGBA',(64,64)).save(b,format='TGA')
        g=io.BytesIO();Image.new('RGB',(2048,1024)).save(g,format='TGA')
        with self.assertRaises(ValueError):retexture_dense_patch(fixture(),0,0,b.getvalue(),Image.new('L',(4,4)),g.getvalue(),lambda p:(0,0),1366)


if __name__=='__main__':unittest.main()
