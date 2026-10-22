"""Local menu-art acceptance and isolated mod resources; native button metrics.

The generated image contains no text. Original menu glyphs are runtime/UI
resources, kept separately from the generated art; no original center is pasted.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'editor'))
from formats import Archive
from PIL import Image,ImageFilter

RECIPE='generated-wide-menu-native-glyphs-v1'
ROOT=Path(__file__).resolve().parents[1]


def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(image):
    stream=io.BytesIO();image.save(stream,format='TGA');return stream.getvalue()


def glyph_mask(image, box):
    """Identify the original red UI ink, never the orange/yellow face art."""
    mask=Image.new('L',image.size,0);pixels=image.load();dest=mask.load()
    for y in range(box[1],box[3]):
        for x in range(box[0],box[2]):
            r,g,b,a=pixels[x,y]
            if r>=100 and g<=12 and b<=12:dest[x,y]=255
    return mask


def menu_images(background,source,items,width):
    if background.size!=(1366,768) or width not in (1366,1230):
        raise ValueError('Menu artwork must be 1366x768')
    offset=(1366-width)//2;pad=(width-1024)//2
    plain=background.crop((offset,0,offset+width,768)).convert('RGBA')
    main=plain.copy();hover=items.copy();glyph_counts=[]
    for row in range(7):
        y=190+58*row
        mask=glyph_mask(source,(100,y,724,y+34))
        count=sum(mask.histogram()[1:])
        if count<200:raise ValueError('Original menu glyph row not recognized')
        glyph_counts.append(count)
        ink=Image.new('RGBA',source.size,(0,0,0,0))
        ink.paste((0,0,0,220),(0,0,source.width,source.height),mask.filter(ImageFilter.MaxFilter(3)))
        ink.paste(source,(0,0),mask)
        main.alpha_composite(ink.crop((0,0,1024,768)),(pad,0))
        # Hover rows originally include an opaque rectangle of the old artwork.
        # Keep only their original glyph shape; amber distinguishes focus while
        # its source metrics, per-pixel alpha and original script stay aligned.
        top=320+63*row
        tile=items.crop((297,top,1021,top+62))
        alpha=glyph_mask(tile,(100,0,724,34));tile=Image.new('RGBA',tile.size,(255,190,0,0));tile.putalpha(alpha)
        hover.paste(tile,(297,top))
    def atlas(image):
        result=Image.new('RGBA',(2048,1024),(0,0,0,0));result.paste(image,(0,0));return result
    return encoded(atlas(main)),encoded(atlas(plain)),encoded(hover),glyph_counts


def build_menu_replacements(archive,work,width):
    folder=Path(work)/'menu';marker=folder/'accepted.json'
    if not marker.exists():return {},None
    accepted=json.loads(marker.read_text(encoding='utf8'));data=(folder/'background.png').read_bytes()
    source=archive.read('inter_face.tga');items=archive.read('items.tga')
    if accepted['recipe']!=RECIPE or sha(data)!=accepted['sha256'] or sha(source)!=accepted['sourceAtlasSha256'] or sha(items)!=accepted['sourceItemsSha256']:
        raise ValueError('Menu acceptance/source fingerprints changed')
    background=Image.open(io.BytesIO(data)).convert('RGBA')
    main,plain,hover,counts=menu_images(background,Image.open(io.BytesIO(source)).convert('RGBA'),Image.open(io.BytesIO(items)).convert('RGBA'),width)
    result={'wmenu_main.tga':main,'wmenu_plain.tga':plain,'wmenu_hover.tga':hover}
    def replace(raw,old,new,count=1):
        if raw.count(old)!=count:raise ValueError('Unexpected source menu script')
        return raw.replace(old,new)
    du=format(width/2048,'.12g').encode('ascii')
    raw=archive.read('mainmenu.scv')
    raw=replace(raw,b'uvsize.Assign(1, -0.75, 0);',b'uvsize.Assign('+du+b', -0.75, 0);')
    raw=replace(raw,b'"inter_face.tga"',b'"wmenu_main.tga"')
    raw=replace(raw,b'"items.tga"',b'"wmenu_hover.tga"',7)
    result['mainmenu.scv']=raw
    for name in ['settings.scv','savegame.scv','loadgame.scv']:
        raw=archive.read(name)
        raw=replace(raw,b'uvposition.Assign(0.613,0.85,0);',b'uvposition.Assign(0,1,0);')
        raw=replace(raw,b'uvsize.Assign(0.382,-0.354,0);',b'uvsize.Assign('+du+b',-0.75,0);')
        result[name]=replace(raw,b'"inter_face.tga"',b'"wmenu_plain.tga"')
    return result,dict(recipe=RECIPE,generatedArtSha256=sha(data),glyphPixelCounts=counts,
                       sourceAtlasSha256=sha(source),sourceItemsSha256=sha(items),
                       nativeButtonGeometryAndHitCoordinatesUnchanged=True,originalCenterComposited=False,
                       changedScripts=['mainmenu.scv','settings.scv','savegame.scv','loadgame.scv'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=ROOT/'build/widescreen')
    parser.add_argument('--generated',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    args=parser.parse_args();archive=Archive(args.archive);folder=args.work/'menu';folder.mkdir(parents=True,exist_ok=True)
    image=Image.open(args.generated).convert('RGB')
    if abs(image.width/image.height-16/9)>.02:raise ValueError('Expected 16:9 generated menu artwork')
    image.resize((1366,768),Image.Resampling.LANCZOS).save(folder/'background.png')
    record=dict(recipe=RECIPE,sha256=sha((folder/'background.png').read_bytes()),generatedInputSha256=sha(args.generated.read_bytes()),
                sourceAtlasSha256=sha(archive.read('inter_face.tga')),sourceItemsSha256=sha(archive.read('items.tga')))
    (folder/'accepted.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    print('Accepted generated menu artwork in',folder)


if __name__=='__main__':main()
