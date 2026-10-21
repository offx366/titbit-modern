"""Recompute native foreground masks from the user's original 1024px TGA atlases.

Only geometry and thresholds are encoded here. No source RGB, generated pixels,
or precomputed mask data are embedded. PIL top-left coordinates throughout.
The caller must apply masks ONLY underneath each original mesh's UV faces.
"""
import math
from PIL import Image, ImageDraw, ImageFilter


def plant_mask(source):
    assert source.size == (1024, 1024)
    source = source.convert('RGB')
    rect = (1, 0, 548, 140)
    crop = source.crop(rect)
    mask = Image.new('L', crop.size)
    pixels, selected = crop.load(), mask.load()
    for y in range(crop.height):
        for x in range(crop.width):
            atlas_x = x + 1
            red, green, blue = pixels[x, y]
            # White bag at right, wall above foliage, and disconnected gray
            # floor speckle above left foliage are not parts of the plant.
            if atlas_x > 507 or (y < 24 and atlas_x > 9) or (atlas_x < 85 and 24 <= y < 49):
                continue
            leaf = green-red >= 6 and green-blue >= 10 and green >= 38
            flower = red-blue >= 17 and green-blue >= 16 and -12 <= red-green <= 24 and green >= 95
            if leaf or flower:
                selected[x, y] = 255
    # Eight-connected RGB noise components below four pixels are not foliage.
    seen = set()
    neighbors = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]
    for y in range(crop.height):
        for x in range(crop.width):
            if not selected[x,y] or (x,y) in seen:
                continue
            component = [(x,y)]
            seen.add((x,y))
            for cx,cy in component:
                for dx,dy in neighbors:
                    xx,yy = cx+dx,cy+dy
                    if 0 <= xx < crop.width and 0 <= yy < crop.height and selected[xx,yy] and (xx,yy) not in seen:
                        seen.add((xx,yy))
                        component.append((xx,yy))
            if len(component) < 4:
                for xx,yy in component:
                    selected[xx,yy] = 0
    # One original pixel includes dark/brown stem edges and antialias fringes.
    mask = mask.filter(ImageFilter.MaxFilter(3))
    result = Image.new('L', source.size)
    result.paste(mask, rect[:2])
    return result


def bicycle_mask(source):
    assert source.size == (1024, 1024)
    source = source.convert('RGB')
    result = Image.new('L', source.size)
    d = ImageDraw.Draw(result)
    outer = [(362+31*math.cos(t*math.pi/96),63.7+28.8*math.sin(t*math.pi/96)) for t in range(192)]
    inner = [(362+26.4*math.cos(t*math.pi/96),63.7+24.0*math.sin(t*math.pi/96)) for t in range(192)]
    d.polygon(outer, fill=255)
    d.polygon(inner, fill=0)
    # Source spokes: preserve thin dark edges alongside the blue source pixels.
    for end in [(336,53),(340,47),(349,41),(360,40),(370,42),(379,48),(386,55),(389,65),(386,75),(379,81),(368,87),(359,87),(349,83),(341,76),(336,66)]:
        d.line([(362,64),end],fill=255,width=2)
    d.polygon([(359,60),(365,60),(367,68),(362,71),(358,68)],fill=255)
    d.polygon([(367,5),(372,4),(380,6),(385,6),(390,10),(388,12),(382,12),(376,16),(368,15),(365,12)],fill=255)
    for points,width in [([(378,13),(382,26),(389,47),(396,62)],3), ([(383,27),(403,26)],3), ([(381,31),(367,52),(362,64)],3), ([(364,66),(389,66),(403,64)],4), ([(396,60),(403,57)],3)]:
        d.line(points,fill=255,width=width)
    d.polygon([(394,57),(400,55),(403,55),(403,71),(398,74),(392,71),(390,65)],fill=255)
    d.polygon([(335,88),(347,89),(363,91),(379,87),(390,83),(401,83),(402,87),(391,92),(372,96),(350,95),(336,93)],fill=255)
    for y in range(39,89):
        for x in range(334,391):
            if ((x-362)/27)**2+((y-63.7)/24.5)**2 > 1:
                continue
            red,green,blue = source.getpixel((x,y))
            if blue-red >= 16 and blue-green >= 10:
                result.putpixel((x,y),255)
    return result


RECIPES = {
    'vodokanal_01konoplia.meat': ('vodocanal_render_a_cc.tga', plant_mask),
    'vxodvelosiped.meat': ('clubvxod_render_a_cc.tga', bicycle_mask),
}
