"""Local-only, resumable background outpainting preparation and mod assembly.

Generation is performed by an image editing service, never by mirroring/stretching.
The whole visible background is regenerated. Original atlas-only regions and
the original archive are preserved; no original center is pasted into a frame.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "editor"))
from formats import Archive, asset_key, parse_mat, parse_meat, parse_scene, write_meat
from PIL import Image, ImageDraw

RATIOS = {"16x9": 1366, "16x10": 1230}
RECIPE = "whole-frame-v2-atlas-bottom768"
PACK_RECIPE = "isolated-background-native-overlays-v8"
CLEAN_PLATES = {"club_dans_render_02.tga": ["club_disko02.xml"]}
EXCLUDE = {"startup.xml", "menu.xml", "map.xml", "chemodan.xml", "shiva.xml",
           "trax.xml", "gameboom.xml", "gameover.xml", "happyend.xml", "intro.xml",
           "intro2.xml", "introvzlab.xml"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slug(name):
    # Archive names never become filesystem paths; suffix prevents collisions.
    return re.sub(r"[^A-Za-z0-9_.-]", "_", PureWindowsPath(name).stem) + "-" + digest(asset_key(name).encode())[:8]


def prompt(name):
    if asset_key(name)=='vorota_h.tga':
        return ('Create a complete 1366x768 soft white/gray cloud background, matching only '
                'the original perimeter cloud style and lighting. The gate spokes, stained glass, '
                'angel, devil, computer and text are separately rendered native 3D objects: '
                'do NOT paint them into the background. Fill the entire frame with continuous '
                'clouds and pale blue atmospheric gaps, no central hole, text or borders. '
                'The engine applies the original alpha matte and native geometry afterwards.')
    return (f"Reference: {name}, a 1024x768 prerendered location background from the "
            "early-2000s adventure game Nuclear Titbit. Regenerate the COMPLETE scene "
            "as a seamless 16:9 background, output 1366x768. Preserve the original "
            "camera, vertical field of view, geometry, object placement and lighting; "
            "the old 4:3 view should correspond to the central 1024 pixels. Extend "
            "horizontally without zooming/cropping or stretching the original scene. Continue existing "
            "architecture/ground and vanishing lines naturally. Match original low-poly "
            "prerendered textures, lighting, shadows, color and fixed perspective. "
            "No new characters, interactive objects, signs, text, watermark or borders. "
            "Extend the same room/location rather than inventing a different scene.")


def plane_model(part):
    """Fit XYZ = origin + U*du + V*dv, reject atlas fragments/non-planar geometry."""
    if not (12 <= len(part["positions"]) <= 24) or not part["uv"]:
        return None
    uv = part["uv"]
    us, vs = uv[::2], uv[1::2]
    if not (.9 < max(us)-min(us) < 1.02 and .65 < max(vs)-min(vs) < .85):
        return None
    ii = part["indices"][:3]
    p = [part["positions"][3*i:3*i+3] for i in ii]
    u0, v0, u1, v1, u2, v2 = uv[:6]
    det = (u1-u0)*(v2-v0)-(u2-u0)*(v1-v0)
    if abs(det) < 1e-8:
        return None
    du = [((p[1][k]-p[0][k])*(v2-v0)-(p[2][k]-p[0][k])*(v1-v0))/det for k in range(3)]
    dv = [((u1-u0)*(p[2][k]-p[0][k])-(u2-u0)*(p[1][k]-p[0][k]))/det for k in range(3)]
    origin = [p[0][k]-u0*du[k]-v0*dv[k] for k in range(3)]
    scale = max(1., *(abs(v) for v in part["positions"]))
    for j, index in enumerate(part["indices"]):
        for k in range(3):
            expected = origin[k]+uv[2*j]*du[k]+uv[2*j+1]*dv[k]
            if abs(expected-part["positions"][3*index+k]) > scale*1e-5:
                return None
    # Four corners, sometimes exported as a zero-thickness double-sided box.
    unique={tuple(round(x,3) for x in part['positions'][i:i+3])
            for i in range(0,len(part['positions']),3)}
    if len(unique)!=4:return None
    windings=set()
    for i in range(0,len(uv),6):
        a,b,c,d,e,f=uv[i:i+6];area=(c-a)*(f-b)-(e-a)*(d-b)
        if abs(area)>1e-6:windings.add(1 if area>0 else -1)
    # A single unskinned plane. Preserve all original winding directions.
    if len(set(part.get("vertexBones", [0]))) != 1 or part["flags"] != 1:
        return None
    return dict(origin=origin, du=du, dv=dv, u=[min(us), max(us)], v=[min(vs), max(vs)],
                windings=sorted(windings))


def extract(archive_path, work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    archive_path = Path(archive_path).resolve()
    if (work/'manifest.json').exists():
        previous=load(work/'manifest.json')
        if previous['archiveSha256']!=file_hash(archive_path):
            raise ValueError('Workspace belongs to another archive; use another --work')
    archive = Archive(archive_path)
    textures, meshes, materials, scenes, warnings = {}, {}, {}, [], []
    for name in sorted(set(archive.names()), key=str.casefold):
        if name.lower().endswith(".mat"):
            try:
                materials[asset_key(name)] = parse_mat(archive.read(name), name)
            except ValueError as e:
                warnings.append(f"{name}: {e}")
    for name in sorted(set(archive.names()), key=str.casefold):
        if not name.lower().endswith(".xml"):
            continue
        scene = parse_scene(archive.read(name), name)
        record = dict(name=name, camera=scene["camera"], excluded=asset_key(name) in EXCLUDE,
                      backgrounds=[], unresolved=[])
        for obj in scene["objects"]:
            if obj["group"] == "interface_objects":
                continue
            for lod in obj["lods"]:
                mn = lod.get("meatname", "").replace(" ", "")
                if not mn:
                    continue
                try:
                    if asset_key(mn) not in meshes:
                        meshes[asset_key(mn)] = parse_meat(archive.read(mn), mn)
                    mesh = meshes[asset_key(mn)]
                except (ValueError, FileNotFoundError) as e:
                    warnings.append(f"{name}/{mn}: {e}")
                    continue
                for pi, part in enumerate(mesh["parts"]):
                    if not part["uv"]:
                        continue
                    us, vs = part["uv"][::2], part["uv"][1::2]
                    if not (.9 < max(us)-min(us) < 1.02 and .65 < max(vs)-min(vs) < .85):
                        continue
                    ids = set(part["faceMaterials"])
                    if len(ids) != 1:
                        continue
                    mt = mesh["materialNames"][next(iter(ids))]
                    mt = mt if mt.lower().endswith(".mat") else mt+".mat"
                    mat = materials.get(asset_key(mt))
                    if not mat or not mat["textures"] or mat["flags"] != 1:
                        continue
                    tn = mat["textures"][0]
                    try:
                        data = archive.read(tn)
                        im = Image.open(io.BytesIO(data))
                    except (ValueError, FileNotFoundError):
                        continue
                    if im.size != (1024, 1024):
                        continue
                    key = asset_key(tn)
                    if key not in textures:
                        ident = slug(tn)
                        directory = work/"source"/ident
                        directory.mkdir(parents=True, exist_ok=True)
                        (directory/"original.tga").write_bytes(data)
                        center = im.convert("RGBA").crop((0, 256, 1024, 1024))
                        center.save(directory/"center.png")
                        (directory/"prompt.txt").write_text(prompt(tn)+"\n", encoding="utf-8")
                        textures[key] = dict(name=tn, id=ident, sourceSha256=digest(data),
                            centerRgbaSha256=digest(center.tobytes()), scenes=[], references=[])
                    row = textures[key]
                    if name not in row["scenes"]:
                        row["scenes"].append(name)
                    planar = plane_model(part) is not None
                    ref = dict(scene=name, object=obj["name"], mesh=mn, part=pi,
                               material=mt, extendable=planar)
                    if ref not in row["references"]:
                        row["references"].append(ref)
                    if key not in record["backgrounds"]:
                        record["backgrounds"].append(key)
                    if not planar:
                        record["unresolved"].append(f"Non-quad/non-planar background {mn}:{pi}")
        scenes.append(record)
    manifest = dict(version=1, recipe=RECIPE, archive=str(archive_path), archiveSha256=file_hash(archive_path),
                    textures=list(textures.values()), scenes=scenes, warnings=sorted(set(warnings)),
                    generation=dict(canvas=[1366, 768], originalReferenceRectangle=[171, 0, 1024, 768],
                        mode="complete regenerated wide frame; no original center compositing",
                        sourceCrop=[0, 256, 1024, 768], ratios=RATIOS))
    save(work/"manifest.json", manifest)
    (work/'scenes.txt').write_text('\n'.join(s['name'] for s in scenes)+'\n',encoding='utf-8')
    required={key for s in scenes if not s['excluded'] for key in s['backgrounds']}
    save(work/'generation-jobs.json', [dict(id=t['id'], texture=t['name'],
         reference=str((work/'source'/t['id']/'center.png').resolve()),
         prompt=str((work/'source'/t['id']/'prompt.txt').resolve()),
         output=str((work/'incoming'/(t['id']+'.png')).resolve()))
         for t in manifest['textures'] if asset_key(t['name']) in required])
    export_masks(work,manifest,archive)
    contact_sources(work, manifest)
    make_report(work)
    print(f"Extracted {len(textures)} candidate backgrounds for {len(scenes)} scenes to {work}")
    return manifest


def export_masks(work, manifest=None, archive=None):
    """Technical masks, not generated art or proof of occlusion correctness.

    UV coverage is computed from actual background triangle coordinates. Alpha
    remains a separate guide: the game can use it for prop cutouts even when
    its background material ignores alpha entirely.
    """
    work=Path(work);manifest=manifest or load(work/'manifest.json')
    if file_hash(manifest['archive'])!=manifest['archiveSha256']:
        raise ValueError('Mask source archive changed')
    archive=archive or Archive(manifest['archive'])
    for row in manifest['textures']:
        folder=work/'source'/row['id']
        image=Image.open(folder/'original.tga').convert('RGBA')
        image.getchannel('A').crop((0,256,1024,1024)).save(folder/'atlas-alpha-mask.png')
        coverage=Image.new('L',(1024,768));draw=ImageDraw.Draw(coverage)
        for ref in row['references']:
            mesh=parse_meat(archive.read(ref['mesh']),ref['mesh']);uv=mesh['parts'][ref['part']]['uv']
            for i in range(0,len(uv),6):
                triangle=[(uv[i+k]*1024,768-uv[i+k+1]*1024)for k in (0,2,4)]
                draw.polygon(triangle,fill=255)
        coverage.save(folder/'background-uv-mask.png')
        sides=Image.new('L',(1366,768),255)
        ImageDraw.Draw(sides).rectangle((171,0,1194,767),fill=0)
        sides.save(folder/'side-regions-mask.png')
        # Whole-frame mode explicitly keeps the entire image editable.
        Image.new('L',(1366,768),255).save(folder/'generation-mask.png')
        save(folder/'masks.json',dict(alpha='atlas-alpha-mask.png',geometryUv='background-uv-mask.png',
             sideGuide='side-regions-mask.png',generation='generation-mask.png',
             mode='whole-frame editable; masks are guides, never old-center compositing',
             geometrySpace='background texture UVs, not world-space character collision/occlusion',
             sourceTextureSha256=row['sourceSha256']))


def contact_sources(work, manifest):
    rows = manifest["textures"]
    for page in range(0, len(rows), 16):
        items = rows[page:page+16]
        out = Image.new("RGB", (4*280, math.ceil(len(items)/4)*235), "#142025")
        draw = ImageDraw.Draw(out)
        for i, row in enumerate(items):
            im = Image.open(work/"source"/row["id"]/"center.png").convert("RGB")
            im.thumbnail((272, 204))
            x, y = i%4*280+4, i//4*235+4
            out.paste(im, (x,y));draw.text((x,y+206), row["name"], fill="white")
        out.save(work/f"source-contact-{page//16+1:02d}.jpg")


def align_frame(frame, original):
    """Optional geometric registration of generated pixels; originals are never warped.

    Dependencies are isolated/optional. Reject weak or implausible matches rather
    than guessing that generator redraws are aligned to the old camera.
    """
    import cv2
    import numpy as np
    reference=np.array(original.convert("RGB"))
    source=np.array(frame.convert("RGB"))
    sift=cv2.SIFT_create(nfeatures=6000)
    kr,dr=sift.detectAndCompute(cv2.cvtColor(reference,cv2.COLOR_RGB2GRAY),None)
    ks,ds=sift.detectAndCompute(cv2.cvtColor(source,cv2.COLOR_RGB2GRAY),None)
    if dr is None or ds is None:raise ValueError("Registration has no image features")
    pairs=cv2.BFMatcher().knnMatch(ds,dr,k=2)
    matches=[p[0] for p in pairs if len(p)==2 and p[0].distance<.7*p[1].distance]
    if len(matches)<30:raise ValueError("Registration has too few reliable matches")
    src=np.float32([ks[m.queryIdx].pt for m in matches])
    dst=np.float32([[kr[m.trainIdx].pt[0]+171,kr[m.trainIdx].pt[1]] for m in matches])
    matrix,inliers=cv2.findHomography(src,dst,cv2.RANSAC,3.)
    count=int(inliers.sum()) if inliers is not None else 0
    if matrix is None or count<25 or count/len(matches)<.35:
        raise ValueError("Generated center changed too much for reliable registration")
    corners=np.float32([[[171,0],[1195,0],[1195,768],[171,768]]])
    projected=cv2.perspectiveTransform(corners,matrix)[0]
    if np.max(np.abs(projected-corners[0]))>150:
        raise ValueError("Generator reframed the camera too far; regenerate")
    rgba=np.array(frame.convert("RGBA"))
    warped=cv2.warpPerspective(rgba,matrix,(1366,768),flags=cv2.INTER_LANCZOS4,
                               borderMode=cv2.BORDER_CONSTANT,borderValue=(0,0,0,0))
    missing=int(np.count_nonzero(warped[:,:,3]<255))
    # Cover registration-border holes using only the same generated frame.
    # No original reference pixels enter the resulting image.
    result=frame.convert('RGBA');result.alpha_composite(Image.fromarray(warped))
    return result,dict(method="SIFT/RANSAC homography of generated pixels only",
        matches=len(matches),inliers=count,matrix=matrix.tolist(),uncoveredPixels=missing,
        requiresEdgeReview=True)


def accept(work, ident, generated, align=False, native_foreground=False, source_aligned=False):
    work = Path(work)
    manifest = load(work/"manifest.json")
    row = next(t for t in manifest["textures"] if t["id"] == ident or asset_key(t["name"]) == asset_key(ident))
    native_scenes=CLEAN_PLATES.get(asset_key(row['name']),[]) if native_foreground else []
    if native_foreground and not native_scenes:
        raise ValueError('No registered native foreground for this clean plate')
    generated = Path(generated).resolve()
    # Services may emit a larger raster of the requested composition.
    # Normalize the generated frame; the reference is only used for comparison.
    with Image.open(generated) as im:
        im = im.convert("RGBA")
        generated_size=im.size
        if im.size != (1366, 768):
            if abs(im.width/im.height-1366/768)>.004:
                raise ValueError(f"Expected 16:9 composition, got {im.size}; manual alignment required")
            im=im.resize((1366,768), Image.Resampling.LANCZOS)
        original = Image.open(work/"source"/row["id"]/"center.png").convert("RGBA")
        registration=None
        if align:im,registration=align_frame(im,original)
        proofs = {}
        for ratio, width in RATIOS.items():
            left = (width-1024)//2
            # The 16:10 variant is a centered crop of the same regenerated scene.
            final = im.crop((171-left, 0, 171-left+width, 768))
            folder = work/"out"/ratio
            folder.mkdir(parents=True, exist_ok=True)
            target = folder/(row["id"]+".png")
            final.save(target)
            proofs[ratio] = dict(path=str(target.relative_to(work)), sha256=file_hash(target),
                                 wholeFrameRegenerated=True, originalCenterComposited=False,
                                 size=[width,768], left=left)
        provenance = dict(inputSha256=file_hash(generated), inputPath=str(generated), inputSize=generated_size,
                          sourceArchiveSha256=manifest['archiveSha256'], sourceTextureSha256=row['sourceSha256'],
                          sourceReferenceSha256=row['centerRgbaSha256'], recipe=RECIPE,
                          generator="external image outpainting; see incoming provenance", registration=registration,
                          nativeForegroundScenes=native_scenes,
                          sourceAlignedSceneArt=bool(source_aligned or align),
                          edgeReview="pending: generator seams and new geometry need visual inspection",variants=proofs)
        save(work/"out"/(row["id"]+".json"), provenance)
    before = Image.new("RGBA", (1366,768), (12,18,20,255));before.paste(original,(171,0))
    comparison=Image.new("RGB", (1366,2*800),(12,18,20))
    comparison.paste(before.convert("RGB"),(0,24));comparison.paste(im.convert("RGB"),(0,824))
    draw=ImageDraw.Draw(comparison)
    draw.text((10,5),row["name"]+" - original center", fill="white")
    draw.text((10,805),"Complete regenerated widescreen frame - no original center overlay", fill="white")
    comparison.save(work/"out"/(row["id"]+"-comparison.jpg"))
    make_report(work)
    print("Accepted complete regenerated frame:",row["name"])


def incoming_options(raw):
    """Optional per-frame metadata travels with user-supplied generated art."""
    path=Path(raw).with_suffix('.json')
    if not path.exists():return False,False
    metadata=load(path)
    for key in ('nativeForeground','sourceAlignedSceneArt'):
        if key in metadata and not isinstance(metadata[key],bool):
            raise ValueError('Expected boolean incoming metadata: '+key)
    return metadata.get('nativeForeground',False),metadata.get('sourceAlignedSceneArt',False)


def original_scenes(work, manifest):
    """Explicit local exceptions; never silently hide unfinished world scenes."""
    path=Path(work)/'original-scenes.txt'
    if not path.exists():return set()
    selected={asset_key(line.strip()) for line in path.read_text(encoding='utf-8-sig').splitlines()
              if line.strip() and not line.lstrip().startswith('#')}
    world={asset_key(s['name']):s for s in manifest['scenes'] if not s['excluded']}
    if not selected<=world.keys():
        raise ValueError('Unknown/non-world original-scene exception: '+str(sorted(selected-world.keys())))
    kept={bg for name in selected for bg in world[name]['backgrounds']}
    required={bg for name,s in world.items() if name not in selected for bg in s['backgrounds']}
    if kept&required:
        raise ValueError('Original-scene exceptions share backgrounds with widened scenes; list every alias')
    return selected


def required_backgrounds(manifest, retained):
    return {key for s in manifest['scenes'] if not s['excluded'] and asset_key(s['name']) not in retained
            for key in s['backgrounds']}


def expand_part(part, model, width):
    """Append wing triangles; leave all original vertices/faces intact."""
    left = (width-1024)//2
    right = width-1024-left
    lo, hi = model["u"]
    v0,v1 = model["v"]
    span = hi-lo
    for a,b in ((lo-span*left/1024,lo),(hi,hi+span*right/1024)):
        points = [(a,v0),(b,v0),(b,v1),(a,v1)]
        offset = len(part["positions"])//3
        for u,v in points:
            part["positions"].extend(model["origin"][k]+u*model["du"][k]+v*model["dv"][k] for k in range(3))
        if part["normals"]:
            part["normals"].extend(part["normals"][:3]*4)
        part["vertexBones"].extend([part["vertexBones"][0]]*4)
        local=[]
        for winding in model['windings']:
            local.extend([0,1,2,0,2,3] if winding>0 else [0,2,1,0,3,2])
        part["indices"].extend(offset+i for i in local)
        part["faceMaterials"].extend([part["faceMaterials"][0]]*(len(local)//3))
        for i in local:
            part["uv"].extend(points[i])


def pack(work, ratio, require_complete=False):
    work = Path(work)
    manifest = load(work/"manifest.json")
    archive_path = Path(manifest["archive"])
    if file_hash(archive_path) != manifest["archiveSha256"]:
        raise ValueError("Source archive changed; extract again to a different workspace")
    archive = Archive(archive_path)
    width=RATIOS[ratio];left=(width-1024)//2
    retained=original_scenes(work,manifest)
    required=required_backgrounds(manifest,retained)
    ready={};native_scenes=set();aligned_scenes=set()
    for row in manifest["textures"]:
        if asset_key(row['name']) not in required:continue
        path=work/"out"/ratio/(row["id"]+".png")
        if not path.exists():
            continue
        im=Image.open(path).convert("RGBA")
        if im.size!=(width,768):
            raise ValueError(f"Wrong output size: {path}")
        proof=load(work/'out'/(row['id']+'.json'))
        if proof.get('sourceArchiveSha256')!=manifest['archiveSha256'] or proof.get('sourceTextureSha256')!=row['sourceSha256'] or proof.get('recipe')!=RECIPE:
            raise ValueError(f'Outdated generation acceptance: {path}')
        if proof['variants'][ratio].get('originalCenterComposited') is not False:
            raise ValueError(f"Old composited output must be accepted again: {path}")
        if file_hash(path)!=proof['variants'][ratio]['sha256']:
            raise ValueError(f"Accepted output changed: {path}")
        requested={asset_key(n) for n in proof.get('nativeForegroundScenes',[])}
        if not requested<=set(CLEAN_PLATES.get(asset_key(row['name']),[])):
            raise ValueError('Unsupported clean-plate foreground provenance: '+row['name'])
        if all(r["extendable"] for r in row["references"]):
            ready[asset_key(row["name"])]=(row,im)
            native_scenes.update(requested)
            if proof.get('sourceAlignedSceneArt'):
                aligned_scenes.update(asset_key(n) for n in row['scenes'])
    if require_complete and set(ready)!=required:
        raise ValueError(f"Only {len(ready)}/{len(required)} world backgrounds generated and extendable")
    if not ready:
        raise ValueError("No accepted extendable outpaint backgrounds; no placeholder mod will be built")
    replacements={};mesh_extensions={};background_textures={}
    for key,(row,im) in ready.items():
        source=Image.open(io.BytesIO(archive.read(row["name"]))).convert("RGBA")
        atlas=Image.new("RGBA",(2048,1024),(0,0,0,0))
        atlas.paste(source,(left,0))
        atlas.paste(im,(0,256))
        # Reuse only the original alpha matte. RGB is entirely the new frame.
        # Transparent background layers (e.g. clouds around the 3D gate) must
        # not become opaque and cover the native interactive geometry.
        alpha=atlas.getchannel('A');alpha.paste(source.getchannel('A'),(left,0));atlas.putalpha(alpha)
        if atlas.crop((left,0,left+1024,256)).tobytes()!=source.crop((0,0,1024,256)).tobytes():
            raise AssertionError("Original atlas-only region changed")
        texture_name='wb_'+digest(key.encode())[:16]+'.tga'
        out=io.BytesIO();atlas.save(out,format="TGA");replacements[texture_name]=out.getvalue()
        background_textures[key]=texture_name
        for ref in row["references"]:
            mesh_extensions.setdefault(asset_key(ref["mesh"]),set()).add(ref["part"])
    # Generated RGB cannot replace shared prop atlases: it destroys their alpha
    # masks and moves the authored cutout coordinates. Give background faces
    # dedicated materials/textures; original 3D props keep their exact resources.
    affected=[]
    for name in sorted(set(archive.names()),key=asset_key):
        if not name.lower().endswith(".meat"):
            continue
        mesh=parse_meat(archive.read(name),name);changed=False
        for pi,part in enumerate(mesh["parts"]):
            if pi in mesh_extensions.get(asset_key(name),set()):
                model=plane_model(part)
                if model is None:raise ValueError("Background no longer planar: "+name)
                old_index=part['faceMaterials'][0]
                old_name=mesh['materialNames'][old_index]
                old_name=old_name if old_name.lower().endswith('.mat') else old_name+'.mat'
                original_material=archive.read(old_name)
                material=parse_mat(original_material,old_name)
                if material['flags']!=1:raise ValueError('Multilayer background needs UV review: '+name)
                texture_name=background_textures[asset_key(material['textures'][0])]
                clone='wm_'+digest((asset_key(old_name)+'|'+texture_name).encode())[:16]
                replacements[clone+'.mat']=original_material[:-32]+texture_name.encode('cp1251').ljust(32,b'\0')
                parse_mat(replacements[clone+'.mat'],clone+'.mat')
                new_index=len(mesh['materialNames']);mesh['materialNames'].append(clone)
                expand_part(part,model,width);changed=True
                part['faceMaterials']=[new_index]*len(part['faceMaterials'])
                for face in range(len(part['faceMaterials'])):
                    for corner in range(3):
                        index=face*6+corner*2
                        part["uv"][index]=(part["uv"][index]*1024+left)/2048
        if changed:
            replacements[name]=write_meat(mesh);affected.append(name)
    from widescreen_foreground import build_foreground_replacements
    foreground,foreground_proof=build_foreground_replacements(archive,native_scenes)
    if set(map(asset_key,foreground))&set(map(asset_key,replacements)):
        raise ValueError('Foreground repair overlaps a background replacement')
    replacements.update(foreground)
    from widescreen_occluders import build_poster_replacements
    posters,poster_proof=build_poster_replacements(archive,aligned_scenes,background_textures,width)
    if set(map(asset_key,posters))&set(map(asset_key,replacements)):
        raise ValueError('Poster repair overlaps another replacement')
    replacements.update(posters)
    from widescreen_native_overlays import build_native_overlay_replacements, NATIVE_PATCHES
    from widescreen_native_masks import RECIPES
    config=load(ROOT/'tools/widescreen_native_contours.json')
    overlay_scenes={asset_key(n) for row,_ in ready.values() for n in row['scenes']}
    registry=dict(NATIVE_PATCHES)
    for name,rule in config['patches'].items():
        if asset_key(rule['texture']) not in background_textures or not set(map(asset_key,rule['scenes'])).intersection(overlay_scenes):
            continue
        rule=dict(rule)
        if rule.get('maskRecipe'):
            mask_recipe=rule.pop('maskRecipe')
            if mask_recipe=='background':
                source=Image.open(io.BytesIO(archive.read(rule['texture'])))
                rule['foregroundMaskImage']=Image.new('L',source.size,0)
            elif mask_recipe=='polygons':
                from PIL import ImageDraw
                source=Image.open(io.BytesIO(archive.read(rule['texture'])))
                mask=Image.new('L',source.size,0)
                draw=ImageDraw.Draw(mask)
                for polygon in rule['polygons']:draw.polygon([tuple(p) for p in polygon],fill=255)
                rule['foregroundMaskImage']=mask
            else:
                texture,recipe=RECIPES[mask_recipe]
                if asset_key(texture)!=asset_key(rule['texture']):
                    raise ValueError('Native foreground mask recipe texture mismatch: '+name)
                rule['foregroundMaskImage']=recipe(Image.open(io.BytesIO(archive.read(texture))))
        registry[name]=rule
    overlays,overlay_proof=build_native_overlay_replacements(
        archive,overlay_scenes,background_textures,width,registry=registry,
        generated_payloads=replacements)
    if set(map(asset_key,overlays))&set(map(asset_key,replacements)):
        raise ValueError('Native overlay repair overlaps another replacement')
    replacements.update(overlays)
    from widescreen_native_overlays import build_sampler_clamp_replacements
    sampler,sampler_proof=build_sampler_clamp_replacements(archive,overlay_scenes,config.get('samplerClamps',{}))
    if set(map(asset_key,sampler))&set(map(asset_key,replacements)):
        raise ValueError('Native sampler repair overlaps another replacement')
    replacements.update(sampler)
    folder=work/"mod"/ratio;folder.mkdir(parents=True,exist_ok=True)
    # Archive.build also retains unchanged compressed payloads/duplicate ordering.
    data=archive.build(replacements)
    target=folder/"QUEST.ezd"
    if target.resolve()==archive_path.resolve() or (target.exists() and target.samefile(archive_path)):
        raise ValueError('Refusing to overwrite the input archive, including through a hard link')
    # Publish only after validation. Existing readers/hard-linked immutable QA
    # copies retain their previous inode while the owner builds the next mod.
    staging=None
    try:
        with tempfile.NamedTemporaryFile(mode='wb',dir=folder,prefix='.QUEST-',suffix='.tmp',delete=False) as stream:
            staging=Path(stream.name)
            stream.write(data)
        check=Archive(staging)
        for name,payload in replacements.items():
            if check.read(name)!=payload:raise AssertionError("Mod roundtrip failed: "+name)
        os.replace(staging,target)
    finally:
        if staging is not None and staging.exists():staging.unlink()
    ready_keys=set(ready)
    allowed=[s["name"] for s in manifest["scenes"] if not s["excluded"] and asset_key(s['name']) not in retained and s["backgrounds"] and
             not s["unresolved"] and set(s["backgrounds"])<=ready_keys]
    (folder/"widescreen-scenes.txt").write_text("\n".join(allowed)+"\n",encoding="utf-8")
    proof=dict(ratio=ratio,sourceSha256=manifest["archiveSha256"],modSha256=file_hash(target),
               recipe=PACK_RECIPE,generatedOutputs={row['id']:file_hash(work/'out'/ratio/(row['id']+'.png')) for row,_ in ready.values()},
               dedicatedBackgroundTextures=background_textures,originalPropResourcesPreserved=not (foreground or posters or overlays),
               originalPropTexturesAndMaterialsPreserved=True,nativeForeground=foreground_proof,
               modifiedForegroundMeshes=sorted(foreground),posterOccluders=poster_proof,
               nativeOverlays=overlay_proof,intrinsicNativePlanesPreserved=config['preserved'],
               nativeSamplerClamps=sampler_proof,
               originalAlphaMattesPreserved=True,originalCenterRgbComposited=False,
               generatedBackgrounds=len(ready),eligibleScenes=allowed,modifiedMeshes=sorted(affected),
               completeRequestedWorldBackgrounds=set(ready)==required,
               completeWorldBackgrounds=set(ready)==required and not retained,
               userSelectedOriginalScenes=sorted(retained),originalCenterComposited=False,
               replacedMembers=sorted(replacements),originalUnchanged=file_hash(archive_path)==manifest["archiveSha256"])
    save(folder/"proof.json",proof);make_report(work)
    print(f"Built {target}: {len(ready)} backgrounds, {len(allowed)} eligible scenes")


def runtime_copy(work, ratio):
    """Only immutable AVI media are copied; saves and settings are independent."""
    work=Path(work);manifest=load(work/'manifest.json')
    folder=work/'runtime'/ratio;folder.mkdir(parents=True,exist_ok=True)
    for media in Path(manifest['archive']).parent.iterdir():
        if media.is_file() and media.suffix.lower()=='.avi':
            target=folder/media.name
            if not target.exists():shutil.copy2(media,target)
    for name in ('QUEST.ezd','widescreen-scenes.txt'):
        destination=folder/name
        original=Path(manifest['archive'])
        if destination.resolve()==original.resolve() or (destination.exists() and destination.samefile(original)):
            raise ValueError('Refusing to overwrite the input archive through the runtime directory')
        shutil.copy2(work/'mod'/ratio/name,destination)
    (folder/'titbit_compat.ini').write_text(
        '[compat]\ndisplay=windowed\nresolution='+str(RATIOS[ratio])+'x768\naspect=widescreen\n'
        'widescreen_ratio='+ratio.replace('x',':')+'\nsetup=modern\ncd=folder\nvideo=auto\n',encoding='ascii')
    return folder


def linux_path(path):
    path=str(Path(path).resolve())
    if os.name=='nt':
        drive,tail=os.path.splitdrive(path)
        return '/mnt/'+drive[0].lower()+tail.replace('\\','/')
    return path


def import_captures(work, ratio, report):
    work=Path(work);report=Path(report);data=load(report)
    proof=load(work/'mod'/ratio/'proof.json')
    actual=file_hash(work/'mod'/ratio/'QUEST.ezd')
    allowlist=file_hash(work/'mod'/ratio/'widescreen-scenes.txt')
    if (actual!=proof['modSha256'] or data['inputs']['archiveSha256']!=actual or
            data['inputs']['aspect']!=ratio.replace('x',':') or data['inputs'].get('allowlistSha256')!=allowlist):
        raise ValueError('Capture inputs do not match current mod/aspect; screenshots are stale')
    captures=load(work/'captures.json') if (work/'captures.json').exists() else {}
    for row in data['scenes']:
        entry=captures.setdefault(row['scene'],{})
        image=report.parent/row['screenshot'] if row.get('screenshot') else None
        entry[ratio]=dict(status='PASS load' if row['passed'] else 'FAIL load',
            screenshot=os.path.relpath(image,work).replace('\\','/') if image else None,
            expanded=row['worldExpanded'],inputs=data['inputs'],edgeReview='pending')
    save(work/'captures.json',captures);make_report(work)


def pipeline(archive, work, incoming, linux_exe=None, partial=False, align=False):
    work=Path(work);archive=Path(archive).resolve()
    if not (work/'manifest.json').exists():extract(archive,work)
    manifest=load(work/'manifest.json')
    if file_hash(archive)!=manifest['archiveSha256']:
        raise ValueError('Archive fingerprint differs from saved workspace; choose another --work')
    required=required_backgrounds(manifest,original_scenes(work,manifest))
    missing=[]
    incoming=Path(incoming or work/'incoming')
    for row in manifest['textures']:
        if asset_key(row['name']) not in required:continue
        raw=incoming/(row['id']+'.png')
        proof=work/'out'/(row['id']+'.json')
        previous=load(proof) if proof.exists() else {}
        native_foreground,source_aligned=incoming_options(raw)
        fresh=(raw.exists() and previous.get('inputSha256')==file_hash(raw) and
               previous.get('sourceArchiveSha256')==manifest['archiveSha256'] and
               previous.get('sourceTextureSha256')==row['sourceSha256'] and previous.get('recipe')==RECIPE and
               previous.get('variants',{}).get('16x9',{}).get('originalCenterComposited') is False and
               bool(previous.get('registration'))==align and
               bool(previous.get('nativeForegroundScenes'))==native_foreground and
               bool(previous.get('sourceAlignedSceneArt'))==bool(source_aligned or align))
        if raw.exists() and not fresh:accept(work,row['id'],raw,align,native_foreground,source_aligned)
        elif not raw.exists():missing.append(row['id'])
    if missing and not partial:
        save(work/'pending-generation.json',missing)
        print(f'{len(missing)} image jobs pending. Generate generation-jobs.json references into {incoming}.')
        print('No placeholder/repeated-edge backgrounds are substituted. Run this command again to resume.')
        return 3
    for ratio in RATIOS:
        pack(work,ratio,not partial)
        data=runtime_copy(work,ratio)
        if linux_exe:
            report=work/('final-linux-'+ratio)
            command=(["wsl.exe","-d","Ubuntu-24.04","--exec","python3"] if os.name=='nt' else [sys.executable])
            command += [linux_path(ROOT/'linux-port/tools/widescreen_validate.py'),
                        '--data',linux_path(data),'--exe',linux_path(linux_exe),
                        '--scenes',linux_path(work/'scenes.txt'),'--allowlist',linux_path(data/'widescreen-scenes.txt'),
                        '--aspect',ratio.replace('x',':'),'--frames','80','--out',linux_path(report)]
            result=subprocess.run(command,check=False)
            if (report/'report.json').exists():import_captures(work,ratio,report/'report.json')
            if result.returncode:return result.returncode
    return 0


def make_report(work):
    work=Path(work);manifest=load(work/"manifest.json")
    retained=original_scenes(work,manifest)
    captures=load(work/"captures.json") if (work/"captures.json").exists() else {}
    reviews=load(work/"reviews.json") if (work/"reviews.json").exists() else {}
    accepted={t["name"] for t in manifest["textures"] if (work/"out"/(t["id"]+".json")).exists()}
    current={};current_allowlists={}
    for ratio in RATIOS:
        proofpath=work/'mod'/ratio/'proof.json'
        if not proofpath.exists():continue
        proof=load(proofpath)
        actual=file_hash(work/'mod'/ratio/'QUEST.ezd') if captures else proof['modSha256']
        assets_fresh=all((work/'out'/ratio/(ident+'.png')).exists() and
                         file_hash(work/'out'/ratio/(ident+'.png'))==value
                         for ident,value in proof.get('generatedOutputs',{}).items())
        if (actual==proof['modSha256'] and assets_fresh and proof.get('recipe')==PACK_RECIPE and
                proof.get('userSelectedOriginalScenes',[])==sorted(original_scenes(work,manifest))):
            current[ratio]=actual
            current_allowlists[ratio]=file_hash(work/'mod'/ratio/'widescreen-scenes.txt')
    lines=["# Widescreen validation", "", f"Source archive SHA256: `{manifest['archiveSha256']}`", "",
           f"Scenes inventoried: {len(manifest['scenes'])}. Background candidates: {len(manifest['textures'])}. "
           f"Generated/accepted: {len(accepted)}.", "",
           "A capture proves loading only. Edge/occlusion/walking/camera checks require explicit review; "
           "missing evidence stays UNTESTED. Original bugs and cutscene/minigame exceptions are listed separately.", "",
           "| Scene | Background / geometry | Runtime capture | Edge review |", "|---|---|---|---|"]
    for scene in manifest["scenes"]:
        name=scene["name"]
        state="4:3 UI/cutscene/minigame" if scene["excluded"] else "; ".join(scene["unresolved"]) or ("background mapped" if scene["backgrounds"] else "no full-plane background; review needed")
        if asset_key(name) in retained:state='4:3 original: explicit user exception'
        captured=captures.get(name,{})
        runs=[]
        for ratio in RATIOS:
            evidence=captured.get(ratio,{})
            screenshot=evidence.get('screenshot')
            status=evidence.get('status','UNTESTED')
            if evidence and (evidence.get('inputs',{}).get('archiveSha256')!=current.get(ratio) or
                    evidence.get('inputs',{}).get('allowlistSha256')!=current_allowlists.get(ratio)):
                status='STALE CAPTURE: rerun required'
            if evidence and not evidence.get('expanded'):status+=' central fallback'
            runs.append(f"{ratio}: [{status}]({screenshot})" if screenshot else f'{ratio}: {status}')
        runtime='<br>'.join(runs)
        review=reviews.get(name,{}).get("notes","UNREVIEWED: crop, occlusion, walk boundary, moving camera")
        if reviews.get(name,{}).get('knownRuntimeIssue'):
            review+=' Runtime limitation: '+reviews[name]['knownRuntimeIssue']
        lines.append(f"| {name} | {state} | {runtime} | {review} |")
    (work/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,default=ROOT/"build/widescreen")
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("extract");p.add_argument("--archive",type=Path,required=True)
    p=sub.add_parser("accept");p.add_argument("texture");p.add_argument("generated",type=Path)
    p.add_argument("--align",action="store_true",help="Register generated frame with optional OpenCV; inspect seams afterwards")
    p.add_argument('--native-foreground',action='store_true',help='Registered clean plate omits booth/platform; restore its native foreground silhouette')
    p.add_argument('--source-aligned',action='store_true',help='Generated RGB was already registered to the source camera; enable matching native poster/wall separation')
    p=sub.add_parser("pack");p.add_argument("--ratio",choices=RATIOS,default="16x9");p.add_argument("--require-complete",action="store_true")
    p=sub.add_parser('run');p.add_argument('--archive',type=Path,required=True);p.add_argument('--incoming',type=Path)
    p.add_argument('--linux-exe',type=Path);p.add_argument('--partial',action='store_true');p.add_argument('--align',action='store_true')
    p=sub.add_parser('capture-results');p.add_argument('--ratio',choices=RATIOS,required=True);p.add_argument('report',type=Path)
    sub.add_parser("report")
    sub.add_parser('masks')
    a=parser.parse_args()
    if not a.work.resolve().is_relative_to((ROOT/'build').resolve()):
        parser.error('--work must stay inside this repository build/ directory')
    if a.command=="extract":extract(a.archive,a.work)
    elif a.command=="accept":accept(a.work,a.texture,a.generated,a.align,a.native_foreground,a.source_aligned)
    elif a.command=="pack":pack(a.work,a.ratio,a.require_complete)
    elif a.command=='run':return pipeline(a.archive,a.work,a.incoming,a.linux_exe,a.partial,a.align)
    elif a.command=='capture-results':import_captures(a.work,a.ratio,a.report)
    elif a.command=='masks':export_masks(a.work)
    else:make_report(a.work)


if __name__=="__main__":raise SystemExit(main())
