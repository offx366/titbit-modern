"""Foreground geometry tests use synthetic meshes/textures, never game assets."""
import copy
import io
import unittest

from PIL import Image
import widescreen_foreground as fg


def fixture(version=20):
    # Rigid plane tilted in XYZ, with a known UV -> XYZ affine map.
    uv = [(.25,.25),(.6875,.25),(.6875,.625),(.25,.625)]
    origin,du,dv = [1,2,3],[2,1,.5],[-.25,3,.75]
    positions = [origin[k]+u*du[k]+v*dv[k] for u,v in uv for k in range(3)]
    indices = [0,1,2,0,2,3]
    part = dict(positions=positions,normals=[0,0,1]*4 if version==21 else [],
                indices=indices,uv=[x for i in indices for x in uv[i]],uv2=[],uv3=[],
                flags=1,faceMaterials=[0,0],vertexBones=[0]*4)
    mesh = fg.write_meat(dict(version=version,slotCount=0,materialNames=["native"],parts=[part]))
    image = Image.new("RGBA",(64,64),(10,20,30,0))
    image.paste((45,67,89,255),(16,24,51,55))
    image.paste((200,180,160,255),(0,0,64,8)) # unrelated atlas fragment
    out = io.BytesIO();image.save(out,format="TGA")
    return mesh,out.getvalue()


class ForegroundTests(unittest.TestCase):
    def test_preserves_original_prefix_and_covers_clipped_alpha(self):
        mesh,texture=fixture();fixed,proof=fg.extend_alpha_tail(mesh,texture)
        original=fg.parse_meat(mesh)["parts"][0];result=fg.parse_meat(fixed)["parts"][0]
        for key in ("positions","indices","uv","normals","vertexBones","faceMaterials"):
            self.assertEqual(result[key][:len(original[key])],original[key])
        self.assertEqual(proof["addedTriangles"],4)
        self.assertGreater(proof["clippedOpaquePixelsBefore"],0)
        self.assertEqual(proof["clippedOpaquePixelsAfter"],0)
        self.assertEqual(proof["newUV"][:1],proof["oldUV"][:1])
        self.assertEqual(proof["newUV"][3],proof["oldUV"][3])

    def test_repeating_repair_is_byte_identical(self):
        mesh,texture=fixture();fixed,_=fg.extend_alpha_tail(mesh,texture)
        again,proof=fg.extend_alpha_tail(fixed,texture)
        self.assertEqual(again,fixed)
        self.assertEqual(proof["addedTriangles"],0)
        self.assertEqual(proof["clippedOpaquePixelsBefore"],0)

    def test_tilted_plane_and_version21_normals_survive(self):
        mesh,texture=fixture(21);fixed,_=fg.extend_alpha_tail(mesh,texture)
        p=fg.parse_meat(fixed)["parts"][0]
        self.assertEqual(len(p["normals"]),len(p["positions"]))
        for corner,index in enumerate(p["indices"]):
            u,v=p["uv"][corner*2:corner*2+2]
            expected=[1+u*2-v*.25,2+u+v*3,3+u*.5+v*.75]
            for actual,want in zip(p["positions"][index*3:index*3+3],expected):
                self.assertAlmostEqual(actual,want,places=5)

    def test_non_affine_mesh_fails_before_output(self):
        mesh,texture=fixture();parsed=fg.parse_meat(mesh)
        parsed["parts"][0]["positions"][11]+=.5
        with self.assertRaisesRegex(ValueError,"not affine"):
            fg.extend_alpha_tail(fg.write_meat(parsed),texture)

    def test_archive_registration_is_scoped_and_no_texture_material_replacement(self):
        mesh,texture=fixture()
        rows={"club_disko02.xml":b"<scene/>","disko02stoika.meat":mesh,
              "club_dans_render_02.tga":texture,"disko_02_alfa.mat":b"native material payload"}
        class ReadOnlyArchive:
            def names(self):return list(rows)
            def read(self,name):return rows[name.lower()]
        before=copy.deepcopy(rows);archive=ReadOnlyArchive()
        replacements,proof=fg.build_foreground_replacements(archive,["CLUB_DISKO02.XML"])
        self.assertEqual(set(replacements),{"disko02stoika.meat"})
        self.assertEqual(rows,before)
        self.assertEqual(set(proof["unchangedResources"]),{"club_dans_render_02.tga","disko_02_alfa.mat"})
        self.assertEqual(fg.build_foreground_replacements(archive,["street.xml"])[0],{})
        self.assertEqual(fg.build_foreground_replacements(archive)[0],{})


if __name__=="__main__":unittest.main()
