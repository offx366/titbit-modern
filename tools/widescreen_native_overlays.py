"""Inspect original shared-background atlas users; local mod repairs preserve props.

Original archives are read-only. This module never launches the game or writes a
shared mod. Unsupported animated/skinned transforms are reported, never guessed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'editor'))
from formats import Archive, asset_key, parse_mat, parse_meat, parse_scene, write_meat
from widescreen_occluders import _object_point, _rotation, _apply, source_background_mapper
from PIL import Image


def sha(data): return hashlib.sha256(data).hexdigest()


def inventory(archive, manifest, output=None):
    """Read all scene users of background atlases, including interface objects."""
    if not hasattr(archive, 'read'): archive = Archive(archive)
    names = {asset_key(n): n for n in archive.names()}
    textures = {asset_key(t['name']): t for t in manifest['textures']}
    meshes, mats, images = {}, {}, {}
    rows = []
    for sn in sorted(n for n in names if n.endswith('.xml')):
        scene = parse_scene(archive.read(names[sn]), sn)
        bgrefs = [(t, r) for t in textures.values() for r in t['references']
                  if asset_key(r['scene']) == sn]
        if not bgrefs: continue
        for obj in scene['objects']:
            for lod in obj['lods']:
                mn = lod.get('meatname', '').replace(' ', '')
                if not mn: continue
                try:
                    mesh = meshes.setdefault(asset_key(mn), parse_meat(archive.read(mn), mn))
                except (ValueError, FileNotFoundError): continue
                for pi, part in enumerate(mesh['parts']):
                    if not part['uv']: continue
                    for mi in sorted(set(part['faceMaterials'])):
                        mt = mesh['materialNames'][mi]
                        if not mt.lower().endswith('.mat'): mt += '.mat'
                        try: mat = mats.setdefault(asset_key(mt), parse_mat(archive.read(mt), mt))
                        except (ValueError, FileNotFoundError): continue
                        if not mat['textures'] or asset_key(mat['textures'][0]) not in textures: continue
                        tn = asset_key(mat['textures'][0]); tex = textures[tn]
                        if tn not in images:
                            images[tn] = Image.open(io.BytesIO(archive.read(mat['textures'][0]))).convert('RGBA')
                        image = images[tn]; w, h = image.size
                        faces = [i for i, m in enumerate(part['faceMaterials']) if m == mi]
                        uv = [part['uv'][i*6+j] for i in faces for j in range(6)]
                        bounds = [min(uv[::2])*w, (1-max(uv[1::2]))*h,
                                  max(uv[::2])*w, (1-min(uv[1::2]))*h]
                        box = [max(0, math.floor(bounds[0])), max(0, math.floor(bounds[1])),
                               min(w, math.ceil(bounds[2])), min(h, math.ceil(bounds[3]))]
                        alpha = image.getchannel('A').crop(box).getextrema() if box[2]>box[0] and box[3]>box[1] else None
                        isbg = any(asset_key(r['mesh']) == asset_key(mn) and r['part'] == pi for _,r in bgrefs)
                        row = dict(scene=sn, object=obj['name'], group=obj['group'], mesh=mn,
                                   part=pi, material=mt, materialIndex=mi, texture=tex['name'],
                                   uvPixelBounds=bounds, alphaExtrema=alpha, blend=mat['blend'],
                                   boneCount=len(obj['bones']), triangles=len(faces),
                                   script=obj['attributes'].get('scriptname'), background=isbg,
                                   sourceMeshSha256=sha(archive.read(mn)), sourceMaterialSha256=sha(archive.read(mt)))
                        row['classification'] = 'background' if isbg else ('interface' if obj['group']=='interface_objects' else 'native_atlas_user')
                        if not isbg and obj['group'] != 'interface_objects':
                            selfrefs = [r for t,r in bgrefs if asset_key(t['name']) == tn and r.get('extendable')]
                            if selfrefs and len(obj['bones']) == 1:
                                ref=selfrefs[0]; bg=next(o for o in scene['objects'] if o['name']==ref['object'])
                                bp=parse_meat(archive.read(ref['mesh']))['parts'][ref['part']]
                                try:
                                    mapper, proof=source_background_mapper(scene['camera'],obj,bg,bp)
                                    errors=[]; screen=[]
                                    for fi in faces:
                                        for corner in range(3):
                                            vi=part['indices'][fi*3+corner]; point=part['positions'][vi*3:vi*3+3]
                                            pu,pv=mapper(point); u,v=part['uv'][fi*6+corner*2:fi*6+corner*2+2]
                                            errors.append(math.hypot((pu-u)*w,(pv-v)*h))
                                            screen.append((pu*w,(1-pv)*h-256))
                                    row.update(projectionUvMaxPx=max(errors), screenBounds4x3=[min(p[0]for p in screen),min(p[1]for p in screen),max(p[0]for p in screen),max(p[1]for p in screen)], projectionProof=proof())
                                    if max(errors)<1.5:
                                        row['classification']='background_occluder_same_uv'
                                    elif bounds[3]<=256 and alpha and alpha[0]==255 and not mat['blend']:
                                        row['classification']='opaque_atlas_prop_patch'
                                    elif bounds[3]<=256:
                                        row['classification']='native_atlas_prop'
                                    elif mat['blend']:
                                        row['classification']='native_alpha_foreground'
                                    else:
                                        row['classification']='opaque_lower_atlas_patch_review'
                                except (ValueError,StopIteration) as exc: row['projectionUnsupported']=str(exc)
                        rows.append(row)
    result=dict(version=1, sourceArchiveSha256=sha(Path(archive.path).read_bytes()),
                backgroundTextureCount=len(textures), users=rows,
                classificationCounts={k:sum(r['classification']==k for r in rows) for k in sorted({r['classification']for r in rows})})
    if output:
        output=Path(output);output.mkdir(parents=True,exist_ok=True)
        (output/'inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for tn,image in images.items():
            safe=Path(textures[tn]['id']); image.crop((0,0,image.width,min(256,image.height))).save(output/(str(safe)+'-top.png'))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True,type=Path);p.add_argument('--manifest',type=Path,default=Path('build/widescreen/manifest.json'));p.add_argument('--output',type=Path,default=Path('build/widescreen/bugs-v7/overlays'))
    args=p.parse_args();r=inventory(args.archive,json.loads(args.manifest.read_text(encoding='utf-8')),args.output)
    print(json.dumps(r['classificationCounts'],indent=2))


def _area(poly):
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))/2


def _side(a,b,p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])


def _clip(poly,a,b,inside=True):
    """Clip a convex polygon to an oriented half-plane; no raster masks."""
    if not poly:return []
    result=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        dp,dq=_side(a,b,p),_side(a,b,q)
        pin=dp>=-1e-12 if inside else dp<=1e-12
        qin=dq>=-1e-12 if inside else dq<=1e-12
        if pin:result.append(p)
        if pin!=qin:
            t=dp/(dp-dq)
            result.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
    clean=[]
    for p in result:
        if not clean or math.dist(clean[-1],p)>1e-10:clean.append(p)
    if len(clean)>1 and math.dist(clean[0],clean[-1])<1e-10:clean.pop()
    return clean if len(clean)>=3 and abs(_area(clean))>1e-13 else []


def _triangulate(polygon):
    """Ear-clip a simple concave contour. Disjoint/overlap unions handled later."""
    p=[tuple(map(float,v)) for v in polygon]
    if len(p)>1 and p[0]==p[-1]:p.pop()
    if len(p)<3 or abs(_area(p))<1e-12:raise ValueError('Degenerate native contour')
    if _area(p)<0:p.reverse()
    out=[]
    while len(p)>3:
        for i in range(len(p)):
            a,b,c=p[i-1],p[i],p[(i+1)%len(p)]
            if _side(a,b,c)<=1e-12:continue
            others=[p[j] for j in range(len(p)) if j not in ((i-1)%len(p),i,(i+1)%len(p))]
            if any(min(_side(a,b,q),_side(b,c,q),_side(c,a,q))>=-1e-12 for q in others):continue
            out.append([a,b,c]);p.pop(i);break
        else:raise ValueError('Native contour is self-intersecting or numerically degenerate')
    out.append(p)
    return out


def _partition(poly,convex):
    """Return inside, outside-pieces, a non-overlapping area partition."""
    remaining=poly;outside=[]
    for a,b in zip(convex,convex[1:]+convex[:1]):
        cut=_clip(remaining,a,b,False)
        if cut:outside.append(cut)
        remaining=_clip(remaining,a,b,True)
        if not remaining:break
    return remaining,outside


def split_native_patch(mesh_bytes,part_index,material_index,polygons,background_uv,
                       generated_material,ratio_width,texture_size=(1024,1024)):
    """Split a native atlas patch into exact-art polygons and generated BG ring.

    Contours are absolute source-atlas pixel polygons (top-left origin). Multiple
    concave/disconnected/overlapping contours form a union. Barycentric original
    face interpolation handles non-affine quad UVs. No RGB/alpha is ever edited.
    """
    if ratio_width not in (1366,1230):raise ValueError('Unsupported widescreen width')
    mesh=parse_meat(mesh_bytes);part=mesh['parts'][part_index];old=copy.deepcopy(part)
    if part['flags']!=1 or len(set(part['vertexBones']))!=1:
        raise ValueError('Native patch must be rigid with one UV layer')
    w,h=texture_size
    native_triangles=[]
    for polygon in polygons:
        if any(len(p)!=2 or not all(math.isfinite(v)for v in p)for p in polygon):raise ValueError('Invalid native polygon')
        native_triangles.extend(_triangulate([(x/w,1-y/h)for x,y in polygon]))
    if not native_triangles:raise ValueError('No native contour specified')
    new_index=len(mesh['materialNames']);mesh['materialNames'].append(generated_material)
    part['indices']=[];part['uv']=[];part['faceMaterials']=[]
    total_area=native_area=ring_area=0.;count_native=count_ring=0
    left=(ratio_width-1024)//2
    for fi,mi in enumerate(old['faceMaterials']):
        indices=old['indices'][fi*3:fi*3+3];flat=old['uv'][fi*6:fi*6+6]
        tri=[tuple(flat[i:i+2])for i in (0,2,4)]
        if mi!=material_index:
            part['indices'].extend(indices);part['uv'].extend(flat);part['faceMaterials'].append(mi);continue
        signed=_area(tri)
        if abs(signed)<1e-13:raise ValueError('Degenerate source UV triangle')
        total_area+=abs(signed);remaining=[tri];kept=[]
        for contour in native_triangles:
            next_remaining=[]
            for polygon in remaining:
                inside,outside=_partition(polygon,contour)
                if inside:kept.append(inside)
                next_remaining.extend(outside)
            remaining=next_remaining
        def emit(poly,native):
            nonlocal native_area,ring_area,count_native,count_ring
            area=abs(_area(poly))
            if native:native_area+=area
            else:ring_area+=area
            # Preserve the original front/back winding for every source face.
            if _area(poly)*signed<0:poly=list(reversed(poly))
            new=[]
            a,b,c=tri;den=_side(a,b,c)
            for u,v in poly:
                weights=(_side(b,c,(u,v))/den,_side(c,a,(u,v))/den,_side(a,b,(u,v))/den)
                xyz=[sum(weights[j]*old['positions'][indices[j]*3+k]for j in range(3))for k in range(3)]
                index=len(part['positions'])//3;new.append(index);part['positions'].extend(xyz)
                part['vertexBones'].append(old['vertexBones'][indices[0]])
                if part['normals']:
                    part['normals'].extend(sum(weights[j]*old['normals'][indices[j]*3+k]for j in range(3))for k in range(3))
            for j in range(1,len(poly)-1):
                for k in (0,j,j+1):
                    part['indices'].append(new[k]);u,v=poly[k]
                    if native:part['uv'].extend((u,v))
                    else:
                        bu,bv=background_uv(part['positions'][new[k]*3:new[k]*3+3])
                        part['uv'].extend(((bu*1024+left)/2048,bv))
                part['faceMaterials'].append(material_index if native else new_index)
                if native:count_native+=1
                else:count_ring+=1
        for poly in kept:emit(poly,True)
        for poly in remaining:emit(poly,False)
    if abs(total_area-native_area-ring_area)>max(1e-10,total_area*1e-8):
        raise AssertionError('Native/ring partition changed original footprint')
    if native_area<=0:raise ValueError('Native contours do not intersect the original patch')
    encoded=write_meat(mesh);new=parse_meat(encoded)['parts'][part_index]
    if new['positions'][:len(old['positions'])]!=old['positions']:raise AssertionError('Original XYZ prefix changed')
    return encoded,dict(recipe='native-prop-generated-ring-v1',sourceMeshSha256=sha(mesh_bytes),
                        meshSha256=sha(encoded),polygons=polygons,nativeTriangles=count_native,
                        ringTriangles=count_ring,sourceUvArea=total_area,nativeUvArea=native_area,
                        ringUvArea=ring_area,originalXYZPrefixPreserved=True,
                        originalOuterFootprintAndDepthPreserved=True,originalPropRGBAlphaUnmodified=True,
                        topologyIntentionallySplit=True,sourceCameraProjectionOnly=True)


def retarget_projected_plane(mesh_bytes,part_index,material_index,background_uv,
                             generated_material,ratio_width):
    """Retexture an authored plane at rest; keep XYZ, culling and animation."""
    mesh=parse_meat(mesh_bytes);part=mesh['parts'][part_index];old=copy.deepcopy(part)
    new_index=len(mesh['materialNames']);mesh['materialNames'].append(generated_material)
    left=(ratio_width-1024)//2
    for fi,mi in enumerate(part['faceMaterials']):
        if mi!=material_index:continue
        for k in range(3):
            vi=part['indices'][fi*3+k];u,v=background_uv(part['positions'][vi*3:vi*3+3])
            part['uv'][fi*6+k*2:fi*6+k*2+2]=[(u*1024+left)/2048,v]
        part['faceMaterials'][fi]=new_index
    encoded=write_meat(mesh);new=parse_meat(encoded)['parts'][part_index]
    for k in ('positions','indices','vertexBones','normals'):
        if new[k]!=old[k]:raise AssertionError('Projected retexture changed '+k)
    return encoded,dict(recipe='native-plane-generated-at-rest-v1',sourceMeshSha256=sha(mesh_bytes),
                        meshSha256=sha(encoded),originalGeometryAndBonesPreserved=True,
                        originalScriptsAndCullingUnchanged=True,generatedBackgroundOnly=True)


NATIVE_PATCHES = {
    'podvorotniaplastinka.meat':dict(
        scenes=['podvorotnia1.xml','podvorotnia2.xml'],texture='podvor_render_cc.tga',
        meshSha256='b2fe356013d98e4652c0ac557e5a8b604468f29c84b1e834401c8dada6929299',
        textureSha256='20b81e7eb061f8c30afdff806d0766034257aa25e10db0283d50b62dc8454719',
        polygons=[[(67,24),(74,21),(77,17),(82,14),(86,16),(88,19),(95,20),
                   (101,21),(104,24),(103,28),(99,30),(92,33),(83,34),(74,32),(68,29)]]),
    'podvorotniamontirovka.meat':dict(
        scenes=['podvorotnia1.xml'],texture='podvor_render_cc.tga',
        meshSha256='afdc6857aabe9fec75360e6c09f870f9adf8e7ebbab8d060950eac54dc7cb59c',
        textureSha256='20b81e7eb061f8c30afdff806d0766034257aa25e10db0283d50b62dc8454719',
        polygons=[[(116,44),(120,42),(198,26),(200,23),(204,23),(207,26),(216,24),
                   (224,24),(232,25),(237,29),(237,32),(233,30),(228,29),(224,31),
                   (222,35),(214,36),(207,36),(197,38),(124,50),(117,49)]])
}
PROJECTED_PLANES = {'vxodsuki.meat':dict(scenes=['sumerki_entrance.xml'],texture='clubvxod_render_a_cc.tga',
    meshSha256='4fa6053ef4cfada3978e9a420f16ae2aadff8b3f4ea458bfc8a15abe9cd3f543',
    textureSha256='8d67a685899279d233dc58420301a321658feb5df20c2f944d6831ab7df90c6a')}


def retexture_dense_patch(mesh_bytes,part_index,material_index,texture_bytes,foreground_mask,
                          generated_bytes,background_uv,ratio_width):
    """Return a cloned TGA whose prop foreground RGBA is byte-for-byte native.

    Only pixel centers actually covered by selected source UV triangles and not
    in the white foreground mask are replaced. Their alpha stays native too.
    The original mesh geometry and UV are not changed. Mask accepts a PIL image,
    PNG bytes, or path; public recipes can compute it from user's original TGA.
    """
    if ratio_width not in (1366,1230):raise ValueError('Unsupported widescreen width')
    mesh=parse_meat(mesh_bytes);part=mesh['parts'][part_index]
    if part['flags']!=1 or len(set(part['vertexBones']))!=1:raise ValueError('Dense patch must be rigid with one UV layer')
    source=Image.open(io.BytesIO(texture_bytes)).convert('RGBA')
    if isinstance(foreground_mask,Image.Image):mask=foreground_mask.convert('L')
    else:mask=Image.open(io.BytesIO(foreground_mask)if isinstance(foreground_mask,bytes)else foreground_mask).convert('L')
    if mask.size!=source.size:raise ValueError('Foreground mask must match full native atlas dimensions')
    generated=Image.open(io.BytesIO(generated_bytes)).convert('RGB')
    if generated.size!=(2048,1024):raise ValueError('Expected dedicated generated2048x1024 atlas')
    output=source.copy();w,h=source.size;left=(ratio_width-1024)//2
    pixels=output.load();sp=source.load();mp=mask.load();gp=generated.load()
    seen=set();changed=0;fg=0
    def sample(x,y):
        if not(-.5<=x<=2047.5 and -.5<=y<=1023.5):raise ValueError('Dense ring projects outside generated texture')
        x=max(0,min(2047,x));y=max(0,min(1023,y));x0,y0=math.floor(x),math.floor(y)
        x1,y1=min(2047,x0+1),min(1023,y0+1);tx,ty=x-x0,y-y0
        return tuple(round((1-ty)*((1-tx)*gp[x0,y0][k]+tx*gp[x1,y0][k])+ty*((1-tx)*gp[x0,y1][k]+tx*gp[x1,y1][k]))for k in range(3))
    for fi,mi in enumerate(part['faceMaterials']):
        if mi!=material_index:continue
        indices=part['indices'][fi*3:fi*3+3];uv=part['uv'][fi*6:fi*6+6]
        a,b,c=[(uv[j]*w,(1-uv[j+1])*h)for j in (0,2,4)];den=_side(a,b,c)
        if abs(den)<1e-10:raise ValueError('Dense patch has degenerate UV triangle')
        box=(max(0,math.floor(min(a[0],b[0],c[0]))),max(0,math.floor(min(a[1],b[1],c[1]))),
             min(w,math.ceil(max(a[0],b[0],c[0]))),min(h,math.ceil(max(a[1],b[1],c[1]))))
        for y in range(box[1],box[3]):
            for x in range(box[0],box[2]):
                if (x,y)in seen:continue
                q=(x+.5,y+.5);weights=(_side(b,c,q)/den,_side(c,a,q)/den,_side(a,b,q)/den)
                if min(weights)<-1e-8:continue
                seen.add((x,y))
                if mp[x,y]>=128:fg+=1;continue
                xyz=[sum(weights[j]*part['positions'][indices[j]*3+k]for j in range(3))for k in range(3)]
                bu,bv=background_uv(xyz);rgb=sample(bu*1024+left-.5,(1-bv)*1024-.5)
                pixels[x,y]=rgb+(sp[x,y][3],);changed+=1
    foreground_before=bytearray();foreground_after=bytearray()
    for y in range(h):
        for x in range(w):
            if mp[x,y]>=128:
                foreground_before.extend(sp[x,y]);foreground_after.extend(pixels[x,y])
    if foreground_before!=foreground_after:raise AssertionError('Dense repair changed native foreground RGBA')
    if output.getchannel('A').tobytes()!=source.getchannel('A').tobytes():raise AssertionError('Dense repair changed atlas alpha')
    out=io.BytesIO();output.save(out,format='TGA');data=out.getvalue()
    return data,dict(recipe='native-prop-generated-ring-dense-v1',sourceTextureSha256=sha(texture_bytes),
                     textureSha256=sha(data),foregroundMaskRawSha256=sha(mask.tobytes()),
                     nativeForegroundRGBASha256=sha(bytes(foreground_before)),
                     retainedForegroundPixels=fg,retexturedBackgroundPixels=changed,
                     originalTextureAlphaUnmodified=True,originalForegroundRGBAUnmodified=True,
                     originalGeometryAndUVUnmodified=True)


def build_native_overlay_replacements(archive,scenes,background_textures,ratio_width,registry=None,projected_registry=None,generated_payloads=None):
    """Return isolated mod replacements/proof; never mutate shared/source data.

    Registry: mesh -> {scenes:[names],texture:name,polygons:[[[x,y],...],...]}.
    Polygon coordinates are absolute native atlas pixels. Optional source hashes
    meshSha256/textureSha256 reject another build. Each mesh has one repair;
    scene aliases must agree on both mesh and cloned texture bytes. Specify
    object when the scene uses the same mesh for several object transforms.
    """
    if not hasattr(archive,'read'):archive=Archive(archive)
    selected={asset_key(s)for s in scenes};textures={asset_key(k):v for k,v in background_textures.items()}
    names={asset_key(n):n for n in archive.names()};rules=[]
    for mode,items in [('split',NATIVE_PATCHES if registry is None else registry),('projected',PROJECTED_PLANES if projected_registry is None else projected_registry)]:
        for mn,rr in items.items():
            if isinstance(rr,list) and len(rr)!=1:raise ValueError('Exactly one repair per native overlay mesh is supported: '+mn)
            for r in (rr if isinstance(rr,list)else [rr]):rules.append((mode,mn,r))
    replacements={};proof=dict(recipe='native-overlay-separation-v1',repairs=[],unchangedResources={})
    for mode,mn,rule in rules:
        tn=asset_key(rule['texture'])
        if tn not in textures:continue
        eligible=selected.intersection(map(asset_key,rule['scenes']))
        for sn in sorted(eligible):
            scene=parse_scene(archive.read(names[sn]),sn)
            objects=[o for o in scene['objects'] if any(asset_key(l.get('meatname','').replace(' ',''))==asset_key(mn)for l in o['lods'])]
            if rule.get('object'):objects=[o for o in objects if o['name']==rule['object']]
            if len(objects)>1:raise ValueError('Native overlay needs an explicit object transform: '+sn+'/'+mn)
            obj=objects[0] if objects else None
            if obj is None:raise ValueError('Registered native overlay mesh absent from scene: '+sn+'/'+mn)
            pi=int(rule.get('part',0));mi=int(rule.get('material',0));data=archive.read(mn)
            if rule.get('meshSha256') and sha(data)!=rule['meshSha256']:raise ValueError('Native overlay source mesh hash mismatch: '+mn)
            if rule.get('textureSha256') and sha(archive.read(rule['texture']))!=rule['textureSha256']:raise ValueError('Native overlay source texture hash mismatch: '+mn)
            bg=None;bp=None
            for candidate in scene['objects']:
                for lod in candidate['lods']:
                    bn=lod.get('meatname','').replace(' ','')
                    if not bn or asset_key(bn)==asset_key(mn):continue
                    try:bm=parse_meat(archive.read(bn),bn)
                    except (ValueError,FileNotFoundError):continue
                    for part in bm['parts']:
                        if not part['uv'] or max(part['uv'][::2])-min(part['uv'][::2])<.9:continue
                        for mt in bm['materialNames']:
                            if not mt.lower().endswith('.mat'):mt+='.mat'
                            try:mat=parse_mat(archive.read(mt),mt)
                            except (ValueError,FileNotFoundError):continue
                            if mat['textures'] and asset_key(mat['textures'][0])==tn:bg,bp=candidate,part;break
                        if bg:break
                    if bg:break
                if bg:break
            if not bg:raise ValueError('No original camera background plane for '+sn+'/'+mn)
            mapper,projection=source_background_mapper(scene['camera'],obj,bg,bp)
            mesh=parse_meat(data);mt=mesh['materialNames'][mi]
            if not mt.lower().endswith('.mat'):mt+='.mat'
            matdata=archive.read(mt);mat=parse_mat(matdata,mt)
            if mat['flags']!=1 or asset_key(mat['textures'][0])!=tn:raise ValueError('Unsupported overlay material: '+mn)
            dense=mode=='split' and any(k in rule for k in ('foregroundMask','foregroundMaskBytes','foregroundMaskImage'))
            generated=textures[tn];clone='wn_'+sha((asset_key(mt)+'|'+generated+'|'+mode+('dense|'+asset_key(mn)if dense else '')).encode())[:16]
            if len(generated.encode('cp1251'))>31:raise ValueError('Generated texture name too long')
            replacement_texture=generated
            if dense:
                payloads={asset_key(k):v for k,v in (generated_payloads or {}).items()}
                if asset_key(generated)not in payloads:raise ValueError('Dense repair needs generated_payloads['+generated+']')
                fm=rule.get('foregroundMaskImage',rule.get('foregroundMaskBytes',rule.get('foregroundMask')))
                native_tga=archive.read(rule['texture'])
                tga,row=retexture_dense_patch(data,pi,mi,native_tga,fm,payloads[asset_key(generated)],mapper,ratio_width)
                replacement_texture=clone+'.tga'
                if replacement_texture in replacements and replacements[replacement_texture]!=tga:
                    raise ValueError('Scene aliases require incompatible dense textures: '+mn)
                replacements[replacement_texture]=tga
                dm=copy.deepcopy(mesh);dm['materialNames'][mi]=clone
                encoded=write_meat(dm)
                row.update(sourceMeshSha256=sha(data),meshSha256=sha(encoded))
            replacements[clone+'.mat']=matdata[:-32]+replacement_texture.encode('cp1251').ljust(32,b'\0')
            current=replacements.get(mn,data)
            if not dense:
                if mode=='split':encoded,row=split_native_patch(current,pi,mi,rule['polygons'],mapper,clone,ratio_width)
                else:encoded,row=retarget_projected_plane(current,pi,mi,mapper,clone,ratio_width)
            if mn in replacements:
                # Scene aliases must produce identical bytes. Do not re-split a
                # mesh that was already transformed for a previous alias.
                if not dense:
                    if mode=='split':encoded,row=split_native_patch(data,pi,mi,rule['polygons'],mapper,clone,ratio_width)
                    else:encoded,row=retarget_projected_plane(data,pi,mi,mapper,clone,ratio_width)
                if replacements[mn]!=encoded:raise ValueError('Scene aliases require incompatible overlay repair: '+mn)
            replacements[mn]=encoded
            row.update(scene=sn,mesh=mn,projectionObject=obj['name'],sourceTexture=rule['texture'],generatedTexture=generated,
                       originalMaterial=mt,generatedMaterial=clone+'.mat',**projection())
            proof['repairs'].append(row);proof['unchangedResources'][mt]=sha(matdata)
            proof['unchangedResources'][rule['texture']]=sha(archive.read(rule['texture']))
    return replacements,proof


if __name__=='__main__':main()
