"""Explicit local-mod poster/wall separation without editing native artwork.

Two authored opaque atlas sprites include a dark wall border around the paper.
Split their planar quad into native paper and a generated-wall ring. The outer
footprint/depth and original four XYZ stay unchanged; topology intentionally
changes. Original TGA/MAT members, paper RGB/alpha and object scripts are intact.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"editor"))
from formats import Archive, asset_key, parse_mat, parse_meat, parse_scene, write_meat
from widescreen_foreground import _affine_plane


# Original atlas paper rim: robust source-pixel gradient fits, 0.04–0.09px RMS.
# Clockwise image-space TL,TR,BR,BL; no generated pixels define these contours.
POSTERS = (
 dict(scenes=("podjezd.xml","podjezd_n.xml"),object="podezd_poster",mesh="podezd_poster2.meat",
      background="podezd_all",texture="podezd_all.tga",
      textureSha256="d4e3f3a7510ab129972c1fa53b4a567330ce479db55ec6d0ea3dea4a33cb2d45",
      meshSha256="a312889606cad9dfc2d8fff2fd7370ab5508ecac2fcf97d0ac31840f663c8390",
      polygon=((5.328852,3.625650),(79.950246,9.198250),(81.010399,107.290448),(5.330810,102.817706))),
 dict(scenes=("podjezd_door13.xml","podjezd_door13_n.xml"),object="podezd_poster",mesh="podezd_poster.meat",
      background="podezd_13",texture="podezd_13.tga",
      textureSha256="d4fcd2fddf57c61283a46c3371949ac7813c874bd26072cb6bf201a8bd08fade",
      meshSha256="14f6189711538ca593ca012f430538abbfc6ac80f16f9d07e0e75dcaba105db0",
      polygon=((3.076107,17.098155),(281.075887,12.182433),(306.513154,209.216592),(60.433248,200.455318))),
)


def _sha(data):return hashlib.sha256(data).hexdigest()
def _dot(a,b):return sum(x*y for x,y in zip(a,b))
def _sub(a,b):return [x-y for x,y in zip(a,b)]
def _cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def _rotation(degrees):
    x,y,z=map(math.radians,degrees)
    cx,sx,cy,sy,cz,sz=math.cos(x),math.sin(x),math.cos(y),math.sin(y),math.cos(z),math.sin(z)
    return [[cz*cy,cz*sy*sx-sz*cx,cz*sy*cx+sz*sx],
            [sz*cy,sz*sy*sx+cz*cx,sz*sy*cx-cz*sx],[-sy,cy*sx,cy*cx]]
def _apply(matrix,point):return [_dot(row,point) for row in matrix]
def _object_point(obj,point):
    # This registry contains rigid, single-bone authored planes only.
    if len(obj["bones"])!=1 or obj["bones"][0].get("parent",-1)>=0:
        raise ValueError("Poster registry expects a rigid root transform")
    b=obj["bones"][0];rotated=_apply(_rotation(b["rotation"]),point)
    return [rotated[k]*b["scale"][k]+b["position"][k] for k in range(3)]


def source_background_mapper(camera,poster_object,background_object,background_part):
    """Map poster-local XYZ to background source UV through the original camera.

    Cast from the actual camera center through the foreground point and intersect
    the original background plane. Parallel authored planes make this affine;
    nonparallel cases are rejected rather than approximated by a homography.
    """
    origin,du,dv,_=_affine_plane(background_part)
    bo=_object_point(background_object,origin)
    bu=_sub(_object_point(background_object,[origin[k]+du[k] for k in range(3)]),bo)
    bv=_sub(_object_point(background_object,[origin[k]+dv[k] for k in range(3)]),bo)
    normal=_cross(bu,bv);normal_size=math.sqrt(_dot(normal,normal))
    if normal_size<1e-10:raise ValueError("Degenerate background plane")
    rotation=_rotation(camera["rotation"])
    center=[-sum(rotation[j][i]*camera["position"][j] for j in range(3)) for i in range(3)]
    a,b,c=_dot(bu,bu),_dot(bu,bv),_dot(bv,bv);det=a*c-b*b
    if abs(det)<1e-12:raise ValueError("Degenerate background UV map")
    plane_distance=_dot(normal,_sub(bo,center))
    samples=[]
    def mapper(point):
        world=_object_point(poster_object,point);ray=_sub(world,center)
        divisor=_dot(normal,ray)
        if abs(divisor)<1e-10:raise ValueError("Foreground ray parallel to background")
        t=plane_distance/divisor
        if t<=0:raise ValueError("Background is behind the camera")
        intersection=[center[k]+t*ray[k] for k in range(3)]
        d=_sub(intersection,bo);dd,ee=_dot(d,bu),_dot(d,bv)
        uv=((dd*c-ee*b)/det,(ee*a-dd*b)/det)
        # Compare source camera projections, independently of the UV solution.
        view1=[v+q for v,q in zip(_apply(rotation,world),camera["position"])]
        fitted=[bo[k]+uv[0]*bu[k]+uv[1]*bv[k] for k in range(3)]
        view2=[v+q for v,q in zip(_apply(rotation,fitted),camera["position"])]
        if view1[2]>=0 or view2[2]>=0:raise ValueError("Foreground behind camera")
        focal=384/math.tan(math.radians(camera["fov"])/2)
        error=math.hypot(focal*(view1[0]/view1[2]-view2[0]/view2[2]),
                         focal*(view1[1]/view1[2]-view2[1]/view2[2]))
        samples.append((divisor,error))
        return uv
    def proof():
        divisors=[d for d,_ in samples]
        relative=(max(divisors)-min(divisors))/max(abs(d) for d in divisors)
        # Source rotations round to 4 decimals: tolerate tiny authored rounding.
        if relative>2e-5:raise ValueError("Poster and background planes are not parallel")
        return dict(sourceCameraProjectionMaxPx=max(e for _,e in samples),
                    planeParallelRelativeError=abs(relative))
    return mapper,proof


def split_poster_plane(mesh_bytes,paper_uv,border_uv,material_name,ratio_width):
    """Return (MEAT bytes, proof) with original paper plus an opaque wall ring."""
    if ratio_width not in (1366,1230):raise ValueError("Unsupported widescreen raster")
    mesh=parse_meat(mesh_bytes)
    if len(mesh["parts"])!=1:raise ValueError("Poster must contain one rigid part")
    part=mesh["parts"][0];original=copy.deepcopy(part)
    if len(part["positions"])!=12 or len(part["indices"])!=6:
        raise ValueError("Poster must be its original four-vertex/two-face quad")
    origin,du,dv,windings=_affine_plane(part)
    old_index=part["faceMaterials"][0]
    us,vs=part["uv"][::2],part["uv"][1::2];u0,u1,v0,v1=min(us),max(us),min(vs),max(vs)
    # Use UV-counterclockwise TL,BL,BR,TR, matching the original front winding.
    corners=[(u0,v1),(u0,v0),(u1,v0),(u1,v1)]
    vertex_uv={}
    for i,index in enumerate(part["indices"]):vertex_uv[index]=part["uv"][i*2:i*2+2]
    outer=[min(vertex_uv,key=lambda i:math.dist(vertex_uv[i],uv)) for uv in corners]
    if len(set(outer))!=4:raise ValueError("Poster source is not a UV rectangle")
    inner=[paper_uv[i] for i in (0,3,2,1)]
    if any(not(u0<u<u1 and v0<v<v1) for u,v in inner):
        raise ValueError("Paper contour must lie strictly inside the original quad")
    for u,v in inner:
        part["positions"].extend(origin[k]+du[k]*u+dv[k]*v for k in range(3))
    if part["normals"]:part["normals"].extend(part["normals"][:3]*4)
    part["vertexBones"].extend([part["vertexBones"][0]]*4)
    inner_ids=list(range(4,8));part["indices"]=[];part["uv"]=[];part["faceMaterials"]=[]
    new_index=len(mesh["materialNames"]);mesh["materialNames"].append(material_name)
    source_uv={**vertex_uv,**dict(zip(inner_ids,inner))}
    left=(ratio_width-1024)//2
    border={}
    for index in range(8):
        u,v=border_uv(part["positions"][index*3:index*3+3])
        border[index]=((u*1024+left)/2048,v)
    def face(indices,material,uvmap,direction):
        if direction<0:indices=[indices[0],indices[2],indices[1]]
        part["indices"].extend(indices);part["faceMaterials"].append(material)
        for index in indices:part["uv"].extend(uvmap[index])
    for direction in windings:
        face([4,5,6],old_index,source_uv,direction);face([4,6,7],old_index,source_uv,direction)
        for i in range(4):
            j=(i+1)%4
            face([outer[i],outer[j],inner_ids[j]],new_index,border,direction)
            face([outer[i],inner_ids[j],inner_ids[i]],new_index,border,direction)
    encoded=write_meat(mesh);parsed=parse_meat(encoded)["parts"][0]
    if parsed["positions"][:12]!=original["positions"]:raise AssertionError("Original XYZ changed")
    return encoded,dict(recipe="poster-paper-wall-ring-v1",originalXYZPreserved=True,
                        sourceMeshSha256=_sha(mesh_bytes),meshSha256=_sha(encoded),
                        oldTriangles=2,newTriangles=len(part["indices"])//3,
                        topologyIntentionallySplit=True,oldMaterialForPaper=True,
                        originalOuterFootprintAndDepthPreserved=True,
                        originalTextureRgbAlphaUnmodified=True,paperUV=paper_uv)


def build_poster_replacements(archive,scenes,background_textures,ratio_width):
    """Read original assets, return (mod replacements, proof); never write files.

    background_textures maps original TGA names to accepted source-aligned
    generated2048x1024 texture names. Registration is explicit and limited to
    these two poster meshes/four scene aliases. Other atlas users stay native.
    """
    if not(hasattr(archive,"read") and hasattr(archive,"names")):archive=Archive(archive)
    selected={asset_key(n) for n in scenes};textures={asset_key(k):v for k,v in background_textures.items()}
    names={asset_key(n):n for n in archive.names()};replacements={}
    proof=dict(recipe="poster-wall-ring-v1",ratioWidth=ratio_width,repairs=[],unchangedResources={})
    for rule in POSTERS:
        if rule["texture"] not in textures:continue
        for scene_name in rule["scenes"]:
            if scene_name not in selected:continue
            scene=parse_scene(archive.read(names[scene_name]),scene_name)
            objects={o["name"]:o for o in scene["objects"]}
            obj=objects[rule["object"]];bg=objects[rule["background"]]
            data=archive.read(rule["mesh"]);texture=archive.read(rule["texture"])
            if _sha(data)!=rule["meshSha256"] or _sha(texture)!=rule["textureSha256"]:
                raise ValueError("Poster registry source hash mismatch: "+rule["mesh"])
            bgmesh=next(l['meatname'] for l in bg['lods'] if l.get('meatname'))
            bgpart=parse_meat(archive.read(bgmesh))["parts"][0]
            mapper,projection=source_background_mapper(scene["camera"],obj,bg,bgpart)
            mesh=parse_meat(data);old_name=mesh["materialNames"][0]
            old_name=old_name if old_name.lower().endswith('.mat') else old_name+'.mat'
            old_mat=archive.read(old_name);mat=parse_mat(old_mat,old_name)
            if mat["flags"]!=1 or asset_key(mat["textures"][0])!=rule["texture"]:
                raise ValueError("Unsupported poster material")
            generated=textures[rule["texture"]]
            if asset_key(generated)==rule["texture"]:
                raise ValueError("Poster border needs a dedicated2048x1024 generated texture")
            clone='wo_'+_sha((asset_key(old_name)+'|'+generated).encode())[:16]
            if len(generated.encode('cp1251'))>31:raise ValueError("Generated texture name too long")
            replacements[clone+'.mat']=old_mat[:-32]+generated.encode('cp1251').ljust(32,b'\0')
            paper_uv=[(x/1024,1-y/1024) for x,y in rule["polygon"]]
            encoded,row=split_poster_plane(data,paper_uv,mapper,clone,ratio_width)
            if rule["mesh"] in replacements and replacements[rule["mesh"]]!=encoded:
                raise ValueError("Scene aliases require incompatible poster geometry")
            replacements[rule["mesh"]]=encoded
            row.update(scene=scene_name,mesh=rule["mesh"],originalMaterial=old_name,
                       borderMaterial=clone+'.mat',generatedTexture=generated,
                       sourceTexture=rule["texture"],sourceTextureSha256=rule["textureSha256"],
                       paperOutlineSourcePixels=rule["polygon"],**projection())
            proof['unchangedResources'].update({old_name:_sha(old_mat),rule['texture']:_sha(texture)})
            proof['repairs'].append(row)
    return replacements,proof
