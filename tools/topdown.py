"""Orthographic top-down crop of a generated map: python3 tools/topdown.py map.json out.png cx cy radius"""
import json, math, sys
from PIL import Image, ImageDraw
sys.path.insert(0, 'tools')
import importlib.util
spec = importlib.util.spec_from_file_location('pv', 'tools/preview.py')
path, out = sys.argv[1], sys.argv[2]; cx0, cy0, radius = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
src = open('tools/preview.py').read()
COL = eval(src[src.index('COL = ') + 6: src.index('\nW, H')])
cat = json.load(open('data/catalog.json'))
def dims(row):
    if row == 'NewRow_303': return (4, 4, 0.30)
    if row == 'NewRow_318': return (0.3, 4, 4)
    if row == 'NewRow_183': return (4, 4, 2.1)
    if row in ('NewRow_180','NewRow_181','NewRow_182','NewRow_185','NewRow_186','NewRow_197','NewRow_376','NewRow_662'): return (4, 4, 0.1)
    if row == 'NewRow_663': return (4, 4, 0.1)
    b = cat.get(row, {}).get('bounds')
    return (2 * b['extent'][0] / 100, 2 * b['extent'][1] / 100, 2 * b['extent'][2] / 100) if b else (1, 1, 1)
m = json.load(open(path)); W = 1400; sc = W / (2 * radius)
img = Image.new('RGB', (W, W), (25, 25, 30)); d = ImageDraw.Draw(img)
def px(x, y): return ((y - cy0) * sc + W / 2, W / 2 - (x - cx0) * sc)
items = []
for a in m['S_AssetsTransform']:
    row = a['Rname']
    if row.startswith('decal_'): continue
    bx, by, bz = dims(row)
    for t in a['Transform']:
        s = t['Scale3D']; x, y, z = t['Translation']['X'] / 100, t['Translation']['Y'] / 100, t['Translation']['Z'] / 100
        if abs(x - cx0) > radius * 1.5 or abs(y - cy0) > radius * 1.5: continue
        lx, ly, lz = s['X'] * bx, s['Y'] * by, s['Z'] * bz
        if lx > 1500: continue
        items.append((z + lz / 2, row, x, y, lx, ly, 2 * math.atan2(t['Rotation']['Z'], t['Rotation']['W']), lz))
items.sort(key=lambda i: i[0])
for ztop, row, x, y, lx, ly, yaw, lz in items:
    c, s_ = math.cos(yaw), math.sin(yaw)
    pts = [px(x + ux * c - vy * s_, y + ux * s_ + vy * c) for ux, vy in ((-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2))]
    col = COL.get(row, (200, 120, 200))
    if lz > 3: f = min(1.0, 0.5 + ztop / 250); col = tuple(int(v * f) for v in col)
    d.polygon(pts, fill=col)
d.text((10, 10), f'top-down centre ({cx0:.0f},{cy0:.0f}) r={radius:.0f} m; up = +X', fill=(255, 255, 255))
img.save(out); print('drawn', len(items))
