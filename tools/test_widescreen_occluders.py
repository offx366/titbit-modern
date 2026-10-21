"""Synthetic geometry/projection checks; no original game data required."""
import math
import unittest
import widescreen_occluders as ws


def quad():
    part=dict(positions=[-1,-1,0,1,-1,0,1,1,0,-1,1,0],normals=[],
              indices=[0,1,2,0,2,3],uv=[0,0,1,0,1,1,0,0,1,1,0,1],uv2=[],uv3=[],
              flags=1,faceMaterials=[0,0],vertexBones=[0]*4)
    return ws.write_meat(dict(version=20,slotCount=0,materialNames=['native'],parts=[part]))


def obj(z=0,rotation=(0,0,0)):
    return dict(bones=[dict(id=0,parent=-1,position=[0,0,z],rotation=rotation,scale=[1,1,1])])


class PosterSplitTests(unittest.TestCase):
    paper=((.2,.8),(.8,.75),(.75,.2),(.25,.25)) # source UV: TL,TR,BR,BL

    def test_outer_xyz_and_paper_uv_preserved_without_overlay_faces(self):
        source=quad()
        mapper=lambda xyz:((xyz[0]+1)/2,(xyz[1]+1)/2)
        data,proof=ws.split_poster_plane(source,self.paper,mapper,'wall',1366)
        mesh=ws.parse_meat(data);p=mesh['parts'][0]
        self.assertEqual(p['positions'][:12],ws.parse_meat(source)['parts'][0]['positions'])
        self.assertEqual(len(p['positions']),24)
        self.assertEqual(proof['newTriangles'],10)
        self.assertTrue(proof['topologyIntentionallySplit'])
        self.assertEqual(p['faceMaterials'][:2],[0,0])
        self.assertEqual(p['faceMaterials'][2:],[1]*8)
        expected=[self.paper[i] for i in (0,3,2,0,2,1)]
        for actual,want in zip(p['uv'][:12],[v for uv in expected for v in uv]):
            self.assertAlmostEqual(actual,want,places=6)
        # Original native quad was replaced, not hidden under coplanar overlays.
        self.assertNotEqual(p['indices'][:6],[0,1,2,0,2,3])

    def test_partition_covers_original_rectangle_once(self):
        data,_=ws.split_poster_plane(quad(),self.paper,lambda p:((p[0]+1)/2,(p[1]+1)/2),'wall',1366)
        p=ws.parse_meat(data)['parts'][0]
        area=0
        for i in range(0,len(p['indices']),3):
            points=[p['positions'][j*3:j*3+2] for j in p['indices'][i:i+3]]
            a,b,c=points
            signed=((b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]))/2
            self.assertGreater(signed,0)
            area+=signed
        self.assertAlmostEqual(area,4,places=6)
        for x,y in [(-.95,-.9),(-.7,.5),(0,0),(.9,.8),(.4,-.8)]:
            count=0
            for i in range(0,len(p['indices']),3):
                a,b,c=[p['positions'][j*3:j*3+2] for j in p['indices'][i:i+3]]
                cross=lambda q,r:(q[0]-x)*(r[1]-y)-(r[0]-x)*(q[1]-y)
                if min(cross(a,b),cross(b,c),cross(c,a))>1e-8:count+=1
            self.assertEqual(count,1)

    def test_source_camera_golden_projection_and_parallel_plane(self):
        camera=dict(rotation=[0,0,0],position=[0,0,-10],fov=45)
        bg=ws.parse_meat(quad())['parts'][0]
        mapper,proof=ws.source_background_mapper(camera,obj(2),obj(),bg)
        self.assertEqual(mapper([0,0,0]),(.5,.5))
        u,v=mapper([.5,-.5,0]);self.assertAlmostEqual(u,.8125);self.assertAlmostEqual(v,.1875)
        mapper([-.5,.5,0]);p=proof()
        self.assertLess(p['sourceCameraProjectionMaxPx'],1e-9)
        self.assertEqual(p['planeParallelRelativeError'],0)

    def test_nonparallel_plane_is_rejected(self):
        camera=dict(rotation=[0,0,0],position=[0,0,-10],fov=45)
        mapper,proof=ws.source_background_mapper(camera,obj(2,(0,20,0)),obj(),ws.parse_meat(quad())['parts'][0])
        mapper([-.5,0,0]);mapper([.5,0,0])
        with self.assertRaisesRegex(ValueError,'not parallel'):proof()

    def test_ratio_changes_only_border_u_mapping(self):
        mapper=lambda p:((p[0]+1)/2,(p[1]+1)/2)
        a,_=ws.split_poster_plane(quad(),self.paper,mapper,'wall',1366)
        b,_=ws.split_poster_plane(quad(),self.paper,mapper,'wall',1230)
        a,b=ws.parse_meat(a)['parts'][0],ws.parse_meat(b)['parts'][0]
        self.assertEqual(a['positions'],b['positions']);self.assertEqual(a['indices'],b['indices'])
        self.assertEqual(a['uv'][:12],b['uv'][:12])
        for i in range(12,len(a['uv']),2):
            self.assertAlmostEqual(a['uv'][i]-b['uv'][i],68/2048,places=6)
            self.assertEqual(a['uv'][i+1],b['uv'][i+1])

    def test_unrelated_scenes_do_not_trigger_registration(self):
        class EmptyArchive:
            def names(self):return []
            def read(self,name):raise AssertionError('should not read unrelated source')
        replacements,proof=ws.build_poster_replacements(EmptyArchive(),['street.xml'],{},1366)
        self.assertEqual(replacements,{})
        self.assertEqual(proof['repairs'],[])


if __name__=='__main__':unittest.main()
