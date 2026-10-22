import io
import unittest
from PIL import Image
from widescreen_menu import glyph_mask,menu_images


class MenuImages(unittest.TestCase):
    def test_generated_background_and_original_ui_coordinates(self):
        source=Image.new('RGBA',(1024,1024),(110,40,20,255))
        items=Image.new('RGBA',(1024,1024),(110,40,20,255))
        for row in range(7):
            y=190+58*row
            source.paste((230,0,0,255),(110,y+8,130,y+24))
            top=320+63*row
            items.paste((230,0,0,255),(407,top+8,427,top+24))
        background=Image.new('RGBA',(1366,768),(20,100,180,255))
        for width in (1366,1230):
            main,plain,hover,counts=menu_images(background,source,items,width)
            main=Image.open(io.BytesIO(main));plain=Image.open(io.BytesIO(plain));hover=Image.open(io.BytesIO(hover))
            pad=(width-1024)//2
            self.assertEqual(main.getpixel((pad+115,200)),source.getpixel((115,200)))
            self.assertEqual(main.getpixel((pad+500,200)),background.getpixel((500,200)))
            self.assertEqual(plain.crop((0,0,width,768)).getextrema(),((20,20),(100,100),(180,180),(255,255)))
            self.assertEqual(hover.getpixel((412,330)),(255,190,0,255))
            self.assertEqual(hover.getpixel((300,330))[3],0)
            self.assertEqual(hover.getpixel((40,40)),items.getpixel((40,40)))
            self.assertEqual(counts,[320]*7)

    def test_native_face_and_grid_colors_are_not_glyphs(self):
        image=Image.new('RGBA',(10,10),(180,45,15,255))
        self.assertIsNone(glyph_mask(image,(0,0,10,10)).getbbox())

    def test_unrecognized_native_ui_fails_closed(self):
        with self.assertRaises(ValueError):
            menu_images(Image.new('RGBA',(1366,768)),Image.new('RGBA',(1024,1024)),Image.new('RGBA',(1024,1024)),1366)


if __name__=='__main__':unittest.main()
