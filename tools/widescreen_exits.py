"""Dock invisible boundary exits in a local widescreen mod, never visible doors.

The original scripts still own the cursor, walk animation and destination. Only
rigid, camera-aligned pick boxes touching the old screen boundary are eligible.
Interior doors, meshes, actors, walk paths and the original archive stay intact.
"""
import copy
import itertools
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'editor'))
from formats import asset_key, parse_scene
from widescreen_occluders import _rotation, _apply, _object_point


def projected_bounds(camera, obj):
    rotation = _rotation(camera['rotation'])
    focal = 384 / math.tan(math.radians(camera['fov']) / 2)
    b = obj['bones'][0]
    points = []
    for signs in itertools.product((-1, 1), repeat=3):
        local = [b['center'][i] + signs[i] * b['bbox'][i] for i in range(3)]
        view = [v + p for v, p in zip(_apply(rotation, _object_point(obj, local)), camera['position'])]
        if view[2] >= -1e-6:
            raise ValueError('Exit crosses camera plane')
        points.append((512 - focal * view[0] / view[2], 384 + focal * view[1] / view[2]))
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def dock_exit(camera, obj, width):
    """Return a modified invisible edge box or None for an interior object.

    Coordinates remain in the original camera projection; the wide canvas adds
    (width-1024)/2 to X. Side exits move outward by that amount. Bottom exits
    grow by the same amount on each side, keeping their original vertical band.
    """
    if width not in (1366, 1230):
        raise ValueError('Unsupported widescreen width')
    if obj['lods'] or obj['components'] != ['position'] or len(obj['bones']) != 1:
        return None
    b = obj['bones'][0]
    if b.get('parent', -1) >= 0 or min(b['scale']) <= 0 or max(b['scale']) - min(b['scale']) > 1e-5:
        return None
    box = projected_bounds(camera, obj)
    x0, y0, x1, y1 = box
    # Conservative boundary tests deliberately exclude interior doors even when
    # their original script uses the same foot cursor as a location transition.
    edge = ('bottom' if y0 >= 650 and y1 >= 760 and y1-y0 <= 300
            else 'left' if x0 <= 0 and x1 <= 240
            else 'right' if x1 >= 1024 and x0 >= 900 else None)
    if not edge:
        return None
    cr = _rotation(camera['rotation'])
    axis = _apply(cr, _apply(_rotation(b['rotation']), [1, 0, 0]))
    if abs(axis[0]) < .99999:
        return None
    view = [v+p for v, p in zip(_apply(cr, _object_point(obj, b['center'])), camera['position'])]
    focal = 384 / math.tan(math.radians(camera['fov']) / 2)
    pad = (width-1024)/2
    world_delta = pad * -view[2] / focal
    result = copy.deepcopy(obj)
    target = result['bones'][0]
    if edge == 'bottom':
        target['bbox'][0] += world_delta / (b['scale'][0] * abs(axis[0]))
    else:
        direction = -1 if edge == 'left' else 1
        target['position'] = [b['position'][i] + direction * world_delta * cr[0][i] for i in range(3)]
    after = projected_bounds(camera, result)
    expected = ([x0-pad, y0, x1+pad, y1] if edge == 'bottom'
                else [x0+direction*pad, y0, x1+direction*pad, y1])
    error = max(abs(a-e) for a,e in zip(after, expected))
    if error > .15:
        raise ValueError('Exit projection not camera-aligned: '+obj['name'])
    return result, dict(object=obj['name'], edge=edge, originalBounds=box,
                        wideCanvasBounds=[after[0]+pad, after[1], after[2]+pad, after[3]],
                        projectionErrorPx=error, originalScript=obj['attributes']['scriptname'])


def build_exit_replacements(archive, scenes, width):
    replacements = {}
    proof = []
    for name in sorted(scenes, key=asset_key):
        raw = archive.read(name)
        scene = parse_scene(raw, name)
        changed = []
        changed_ids = set()
        encoded = raw
        for i, obj in enumerate(scene['objects']):
            script = obj['attributes'].get('scriptname')
            if obj['attributes'].get('selectable') != '1' or not script:
                continue
            if not re.search(rb'SetCursorType\s*\(\s*6\s*\)', archive.read(script)):
                continue
            result = dock_exit(scene['camera'], obj, width)
            if result:
                scene['objects'][i], row = result
                row['scene'] = name
                changed.append(row)
                changed_ids.add(obj['id'])
                replacement = scene['objects'][i]['bones'][0]
                pattern = rb'<object\b(?=[^>]*\bname="'+re.escape(obj['name'].encode('cp1251'))+rb'")[^>]*>.*?</object>'
                matches = list(re.finditer(pattern, encoded, re.S))
                if len(matches) != 1:
                    raise ValueError('Source exit XML must have a unique object name')
                match = matches[0]
                block = match.group()
                key = 'bbox' if row['edge']=='bottom' else 'position'
                vector = re.search(rb'<'+key.encode()+rb'\b(?=[^>]*\bx=)[^>]*/>', block)
                if not vector:
                    raise ValueError('Cannot locate source exit vector')
                tag = vector.group()
                for axis, value in zip('xyz', replacement[key]):
                    tag = re.sub(axis.encode()+rb'="[^"]*"', axis.encode()+b'="'+format(value,'.9g').encode()+b'"', tag)
                block = block[:vector.start()]+tag+block[vector.end():]
                encoded = encoded[:match.start()]+block+encoded[match.end():]
        if changed:
            check = parse_scene(encoded, name)
            for before, after in zip(parse_scene(raw, name)['objects'], check['objects']):
                if before['id'] not in changed_ids:
                    if before != after:
                        raise AssertionError('Interior object changed: '+name+'/'+before['name'])
            replacements[name] = encoded
            proof.extend(changed)
    return replacements, proof
