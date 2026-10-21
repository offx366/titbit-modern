"""Restore authored foreground alpha tails in local widescreen mod archives.

The disco clean plate must omit its booth/platform. The native alpha foreground
then supplies those objects at their original depth. This module restores the
small part of that silhouette cropped by the original MEAT's UV rectangle; it
does not paint, rescale, move or overwrite an original texture or material.
"""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "editor"))
from formats import Archive, asset_key, parse_meat, write_meat
from PIL import Image


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _affine_plane(part):
    if part["flags"] != 1 or len(set(part["vertexBones"])) != 1:
        raise ValueError("Foreground must be a single rigid UV-mapped plane")
    if len(set(part["faceMaterials"])) != 1 or len(part["indices"]) < 3:
        raise ValueError("Foreground must use one material and nonempty geometry")
    uv = part["uv"]
    xyz = [part["positions"][3*i:3*i+3] for i in part["indices"][:3]]
    u0,v0,u1,v1,u2,v2 = uv[:6]
    det = (u1-u0)*(v2-v0)-(u2-u0)*(v1-v0)
    if abs(det) < 1e-10:
        raise ValueError("Degenerate foreground UV triangle")
    du = [((xyz[1][k]-xyz[0][k])*(v2-v0)-(xyz[2][k]-xyz[0][k])*(v1-v0))/det for k in range(3)]
    dv = [((u1-u0)*(xyz[2][k]-xyz[0][k])-(u2-u0)*(xyz[1][k]-xyz[0][k]))/det for k in range(3)]
    origin = [xyz[0][k]-u0*du[k]-v0*dv[k] for k in range(3)]
    tolerance = max(1.0, *(abs(x) for x in part["positions"]))*1e-5
    for corner,index in enumerate(part["indices"]):
        for k in range(3):
            fitted = origin[k]+uv[2*corner]*du[k]+uv[2*corner+1]*dv[k]
            if abs(fitted-part["positions"][3*index+k]) > tolerance:
                raise ValueError("Foreground geometry/UV is not affine and coplanar")
    winding = set()
    for face in range(0,len(uv),6):
        a,b,c,d,e,f = uv[face:face+6]
        area = (c-a)*(f-b)-(e-a)*(d-b)
        if abs(area) > 1e-10:
            winding.add(1 if area > 0 else -1)
    if not winding:
        raise ValueError("Foreground has no nondegenerate faces")
    return origin,du,dv,sorted(winding)


def extend_alpha_tail(mesh_bytes, texture_bytes):
    """Return (mesh bytes, proof); append right/bottom strips, never rewrite faces.

    Intended for the registered disco platform atlas region: alpha in the same
    lower-right atlas region belongs to the platform. Other atlas fragments above
    or to its left are excluded. Pixel centers define the alpha coverage proof.
    Calling this on its own result returns identical bytes and zero new faces.
    """
    mesh = parse_meat(mesh_bytes)
    if len(mesh["parts"]) != 1:
        raise ValueError("Foreground repair requires exactly one mesh part")
    part = mesh["parts"][0]
    origin,du,dv,winding = _affine_plane(part)
    uv = part["uv"]
    u0,u1 = min(uv[::2]),max(uv[::2])
    v0,v1 = min(uv[1::2]),max(uv[1::2])
    if not (0 <= u0 < u1 <= 1 and 0 <= v0 < v1 <= 1):
        raise ValueError("Foreground UV rectangle is outside its source atlas")
    image = Image.open(io.BytesIO(texture_bytes)).convert("RGBA")
    width,height = image.size
    region = image.getchannel("A").point(lambda a:255 if a>=128 else 0)
    # Exclude unrelated atlas fragments. Keep the authored top and left edges.
    left,top = max(0,math.floor(u0*width)),max(0,math.floor((1-v1)*height))
    region.paste(0,(0,0,width,top));region.paste(0,(0,top,left,height))
    bbox = region.getbbox()
    nu1,nv0 = u1,v0
    if bbox:
        nu1 = max(u1,min(1.0,(bbox[2]+1)/width))
        nv0 = min(v0,max(0.0,1-(bbox[3]+1)/height))
    old_counts = {key:len(part[key]) for key in
                  ("positions","indices","uv","vertexBones","faceMaterials","normals")}

    def append_quad(points):
        offset = len(part["positions"])//3
        for u,v in points:
            part["positions"].extend(origin[k]+u*du[k]+v*dv[k] for k in range(3))
        if part["normals"]:
            part["normals"].extend(part["normals"][:3]*4)
        part["vertexBones"].extend([part["vertexBones"][0]]*4)
        for direction in winding:
            indices = [0,1,2,0,2,3] if direction>0 else [0,2,1,0,3,2]
            part["indices"].extend(offset+i for i in indices)
            part["faceMaterials"].extend([part["faceMaterials"][0]]*2)
            for i in indices:
                part["uv"].extend(points[i])

    if nu1-u1 > 1e-7:
        append_quad([(u1,nv0),(nu1,nv0),(nu1,v1),(u1,v1)])
    if v0-nv0 > 1e-7:
        append_quad([(u0,nv0),(u1,nv0),(u1,v0),(u0,v0)])
    encoded = write_meat(mesh) if len(part["indices"]) != old_counts["indices"] else mesh_bytes
    original = parse_meat(mesh_bytes)["parts"][0]
    parsed = parse_meat(encoded)["parts"][0]
    if any(parsed[key][:count] != original[key] for key,count in old_counts.items()):
        raise AssertionError("Repair changed the original foreground geometry")
    _affine_plane(parsed)
    before = after = 0
    for y in range(top,height):
        row = region.crop((left,y,width,y+1)).tobytes()
        for column,alpha in enumerate(row):
            if not alpha:
                continue
            u,v = (left+column+0.5)/width,1-(y+0.5)/height
            before += not (u0<=u<=u1 and v0<=v<=v1)
            after += not (u0<=u<=nu1 and nv0<=v<=v1)
    if after:
        raise AssertionError("Repaired rectangle still clips foreground alpha")
    proof = dict(recipe="native-alpha-tail-v1",sourceMeshSha256=_sha(mesh_bytes),
                 meshSha256=_sha(encoded),textureSha256=_sha(texture_bytes),
                 oldUV=[u0,v0,u1,v1],newUV=[u0,nv0,nu1,v1],alphaBBox=bbox,
                 addedVertices=(len(parsed["positions"])-old_counts["positions"])//3,
                 addedTriangles=(len(parsed["indices"])-old_counts["indices"])//3,
                 clippedOpaquePixelsBefore=before,clippedOpaquePixelsAfter=after,
                 originalGeometryPrefixPreserved=True,coplanar=True)
    return encoded,proof


def build_foreground_replacements(archive, scenes=()):
    """Return (replacement dict, proof) without writing archives or source files.

    Pass the immutable original Archive, plus the scenes whose generated frames
    are clean plates. Both aspect ratios use the same authored world geometry.
    Omitting scenes selects no repairs; callers must explicitly declare clean
    plates. No repair is selected for unrelated or absent scenes.
    """
    if not (hasattr(archive,"read") and hasattr(archive,"names")):
        archive = Archive(archive)
    names = {asset_key(n) for n in archive.names()}
    selected = {asset_key(n) for n in (scenes or ())}
    proof = dict(recipe="native-foreground-v1",repairs=[],unchangedResources={})
    scene,mesh,texture,material = ("club_disko02.xml","disko02stoika.meat",
                                 "club_dans_render_02.tga","disko_02_alfa.mat")
    if scene not in selected or scene not in names:
        return {},proof
    data,row = extend_alpha_tail(archive.read(mesh),archive.read(texture))
    row.update(scene=scene,mesh=mesh,texture=texture,material=material)
    proof["repairs"].append(row)
    proof["unchangedResources"] = {name:_sha(archive.read(name)) for name in (texture,material)}
    return {mesh:data},proof
