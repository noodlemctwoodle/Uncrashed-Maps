"""Orthographic top-down crop of a generated map: python3 tools/topdown.py map.json out.png cx cy radius

Arguments (all required): the map file, the output PNG, and the world centre `cx cy` and `radius` of the square
window, in metres. Instances outside 1.5 * radius on either axis are skipped.

Run from the repo root: `tools/preview.py` and `data/catalog.json` are opened by relative paths. The colour table is
lifted from preview.py by slicing its source text (the `COL = {...}` literal up to the `W, H` line) and eval-ing it,
because importing preview.py would run it as a script. This is also a script, not a library.

Output: a 1400 x 1400 PNG with +X up and +Y to the right (not the racemap orientation), every instance as its
yaw-rotated footprint rectangle in the row's preview colour (magenta if unlisted), taller things drawn later so
they overpaint; items over 3 m tall are brightened with their top height.

Units: the JSON is Unreal cm; `dims()` and everything after it are metres.

Conventions relied on: yaw = 2 * atan2(q.Z, q.W), pitch/roll ignored; sizes are the catalog's full extents (twice
the half-extent) with the same hard-coded sizes as preview.py for the top-pivoted floor R303, the brick wall R318,
the water tile R183 and the 4 x 4 x 0.1 m ground planes. The pivot offset does not matter top-down, so unlike
preview.py no base offset is needed.
"""

import json, math, sys
from PIL import Image, ImageDraw

sys.path.insert(0, 'tools')
import importlib.util

# Leftover: this spec is never loaded (importing preview.py would execute it); the palette is read from the source
# text below instead. Kept untouched because this pass must not change behaviour.
spec = importlib.util.spec_from_file_location('pv', 'tools/preview.py')
path, out = sys.argv[1], sys.argv[2]
cx0, cy0, radius = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
src = open('tools/preview.py').read()
# Slice the `COL = {...}` dict literal out of preview.py and evaluate it: it must stay a plain literal that ends right
# before the `W, H` assignment for this to keep working.
COL = eval(src[src.index('COL = ') + 6 : src.index('\nW, H')])
cat = json.load(open('data/catalog.json'))


def dims(row):
    """(size_x, size_y, size_z) in metres for an asset row at scale 1: twice the catalog half-extents.

    The hard-coded rows mirror preview.dims() (floor, brick wall, water tile, ground planes); rows without catalog
    bounds are drawn as a 1 m cube.
    """
    if row == 'NewRow_303':
        return (4, 4, 0.30)
    if row == 'NewRow_318':
        return (0.3, 4, 4)
    if row == 'NewRow_183':
        return (4, 4, 2.1)
    # SM_BaseGround ground planes: 4 x 4 x 0.1 m.
    if row in (
        'NewRow_180',
        'NewRow_181',
        'NewRow_182',
        'NewRow_185',
        'NewRow_186',
        'NewRow_197',
        'NewRow_376',
        'NewRow_662',
    ):
        return (4, 4, 0.1)
    if row == 'NewRow_663':
        return (4, 4, 0.1)
    b = cat.get(row, {}).get('bounds')
    return (2 * b['extent'][0] / 100, 2 * b['extent'][1] / 100, 2 * b['extent'][2] / 100) if b else (1, 1, 1)


m = json.load(open(path))
W = 1400
sc = W / (2 * radius)  # pixels per metre
img = Image.new('RGB', (W, W), (25, 25, 30))
d = ImageDraw.Draw(img)


def px(x, y):
    """World (x, y) metres -> pixel: +Y runs right from the image centre and +X runs up (image y decreases)."""
    return ((y - cy0) * sc + W / 2, W / 2 - (x - cx0) * sc)


# Collect (top_z, row, x, y, size_x, size_y, yaw, size_z) per drawable instance; sorted by top height below.
items = []
for a in m['S_AssetsTransform']:
    row = a['Rname']
    if row.startswith('decal_'):
        continue  # decal rows are named after their PNG; images on other surfaces, not solids
    bx, by, bz = dims(row)
    for t in a['Transform']:
        s = t['Scale3D']
        x, y, z = t['Translation']['X'] / 100, t['Translation']['Y'] / 100, t['Translation']['Z'] / 100
        if abs(x - cx0) > radius * 1.5 or abs(y - cy0) > radius * 1.5:
            continue
        lx, ly, lz = s['X'] * bx, s['Y'] * by, s['Z'] * bz
        if lx > 1500:
            continue  # huge ground slabs (over 1.5 km wide) would cover the whole crop; the background stands in
        items.append((z + lz / 2, row, x, y, lx, ly, 2 * math.atan2(t['Rotation']['Z'], t['Rotation']['W']), lz))
# Lowest tops first so taller geometry overpaints what is under it (the sort key treats the pivot as the box centre).
items.sort(key=lambda i: i[0])
for ztop, row, x, y, lx, ly, yaw, lz in items:
    c, s_ = math.cos(yaw), math.sin(yaw)
    # Footprint corners: local rectangle rotated by the yaw about the pivot.
    pts = [
        px(x + ux * c - vy * s_, y + ux * s_ + vy * c)
        for ux, vy in ((-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2))
    ]
    col = COL.get(row, (200, 120, 200))
    # Items taller than 3 m are brightened with height: 50 % at the ground up to 100 % at a 125 m top (empirical).
    if lz > 3:
        f = min(1.0, 0.5 + ztop / 250)
        col = tuple(int(v * f) for v in col)
    d.polygon(pts, fill=col)
d.text((10, 10), f'top-down centre ({cx0:.0f},{cy0:.0f}) r={radius:.0f} m; up = +X', fill=(255, 255, 255))
img.save(out)
print('drawn', len(items))
