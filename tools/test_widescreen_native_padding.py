import io
import unittest

from PIL import Image
from widescreen_native_overlays import pad_native_sampler
from formats import parse_meat, write_meat


def mesh():
    return write_meat(dict(version=20, slotCount=0, materialNames=['native'], parts=[dict(
        positions=[0., 0., 0., 1., 0., 0., 0., 1., 0.], normals=[], indices=[0, 1, 2],
        flags=1, vertexBones=[0, 0, 0], uv=[.4, .2, 1.3, .2, .7, .8],
        uv2=[], uv3=[], faceMaterials=[0])]))


class NativePadding(unittest.TestCase):
    def test_native_texels_and_triangle_interpolation_preserved(self):
        source = Image.new('RGBA', (1024, 1024), (10, 20, 30, 40))
        source.putpixel((1023, 100), (93, 44, 10, 254))
        stream = io.BytesIO(); source.save(stream, format='TGA')
        old = mesh()
        encoded, tga, proof = pad_native_sampler(old, stream.getvalue(), 0, 'padded')
        result = Image.open(io.BytesIO(tga)).convert('RGBA')
        self.assertEqual(result.crop((0, 0, 1024, 1024)).tobytes(), source.tobytes())
        for x in range(1024, 2048):
            self.assertEqual(result.crop((x, 0, x+1, 1024)).tobytes(), source.crop((1023, 0, 1024, 1024)).tobytes())
        a, b = parse_meat(old)['parts'][0], parse_meat(encoded)['parts'][0]
        for key in ['positions', 'indices', 'normals', 'vertexBones', 'faceMaterials']:
            self.assertEqual(a[key], b[key])
        self.assertEqual(a['uv'][1::2], b['uv'][1::2])
        # Interior samples crossing U=1 preserve affine interpolation. Vertex
        # clamping would change the native region even where U remains <1.
        weights = [.2, .3, .5]
        native_u = sum(w*u for w, u in zip(weights, a['uv'][::2]))
        padded_u = sum(w*u for w, u in zip(weights, b['uv'][::2]))
        self.assertAlmostEqual(native_u * 1024, padded_u * 2048)
        self.assertTrue(proof['originalTexturePixelsPreserved'])

    def test_other_material_triangle_keeps_its_original_uv(self):
        source = Image.new('RGBA', (1024, 1024)); stream = io.BytesIO(); source.save(stream, format='TGA')
        value = parse_meat(mesh()); value['materialNames'].append('other')
        part = value['parts'][0]
        part['indices'] += part['indices']; part['uv'] += part['uv']; part['faceMaterials'] += [1]
        encoded, _, _ = pad_native_sampler(write_meat(value), stream.getvalue(), 0, 'padded')
        result = parse_meat(encoded)['parts'][0]
        self.assertEqual(result['uv'][6:], part['uv'][6:])
        self.assertEqual(result['uv'][1:6:2], part['uv'][1:6:2])
        self.assertEqual(result['uv'][:6:2], [u/2 for u in part['uv'][:6:2]])

    def test_unexpected_uv_domain_is_rejected(self):
        source = Image.new('RGBA', (1024, 1024)); stream = io.BytesIO(); source.save(stream, format='TGA')
        value = parse_meat(mesh()); value['parts'][0]['uv'][2] = 2.1
        with self.assertRaises(ValueError):
            pad_native_sampler(write_meat(value), stream.getvalue(), 0, 'padded')


if __name__ == '__main__':
    unittest.main()
