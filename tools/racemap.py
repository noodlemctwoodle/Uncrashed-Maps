#!/usr/bin/env python3
"""Top-down race plan: every mesh footprint in grey (structures darker), the road, numbered gates with their flight
height, the straight legs between them and the start arrow.   usage: racemap.py <map.json> <out.png> [half-size m]"""
import json, math, os, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raceline
path, out = sys.argv[1], sys.argv[2]; R = float(sys.argv[3]) if len(sys.argv) > 3 else 400.0
d = json.load(open(path, encoding='utf-8-sig')); W = 2000; sc = W / (2 * R)
im = Image.new('RGB', (W, W), (235, 232, 224)); dr = ImageDraw.Draw(im)
def px(x, y): return (W / 2 + x * sc, W / 2 - y * sc)
STRUCT_MESH = ('Concrete', 'Brick', 'Cube', 'Cylinder', 'Wall', 'Column', 'Container', 'Neo', 'Scaffold', 'Crane')
for o in raceline.load_obbs(d):
    mesh = raceline.CAT[o.row]['mesh'] or ''
    if 'BaseGround' in mesh: col = (210, 205, 195)
    elif 'Water' in mesh: col = (170, 200, 230)
    elif any(k in mesh for k in STRUCT_MESH): col = (90, 90, 100)
    elif 'Tree' in mesh or 'Elm' in mesh or 'Maple' in mesh or 'Pine' in mesh or 'Bush' in mesh: col = (150, 185, 140)
    else: col = (165, 160, 155)
    ex, ey = o.e[0] * abs(o.S[0]), o.e[1] * abs(o.S[1]); ox, oy = o.o[0] * o.S[0], o.o[1] * o.S[1]
    corners = []
    for (u, v) in ((-ex, -ey), (ex, -ey), (ex, ey), (-ex, ey)):
        lx, ly = ox + u, oy + v
        wx = o.R[0][0] * lx + o.R[0][1] * ly + o.T[0]; wy = o.R[1][0] * lx + o.R[1][1] * ly + o.T[1]; corners.append(px(wx, wy))
    dr.polygon(corners, fill=col)
race = d['Race']; st = race['StartTransform']['Translation']; s_xy = (st['X'] / 100, st['Y'] / 100)
pts = [s_xy] + [(raceline.fly_point(cp)[0], raceline.fly_point(cp)[1]) for cp in race['CheckPoints']] + [s_xy]
for a, b in zip(pts, pts[1:]): dr.line([px(*a), px(*b)], fill=(220, 40, 40), width=4)
font = ImageFont.load_default(size=22) if hasattr(ImageFont, 'load_default') else None
for i, cp in enumerate(race['CheckPoints']):
    fx, fy, fz = raceline.fly_point(cp); q = cp['Transform']['Rotation']; yaw = 2 * math.atan2(q['Z'], q['W'])
    c, s_ = math.cos(yaw), math.sin(yaw); hw = 3.0                                 # gate drawn as a bar along its local X (flight is along local Y)
    dr.line([px(fx - hw * c, fy - hw * s_), px(fx + hw * c, fy + hw * s_)], fill=(0, 90, 220), width=6)
    x, y = px(fx, fy); dr.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(255, 255, 255), outline=(0, 90, 220), width=2)
    g = raceline.CAT and None
    dr.text((x + 11, y - 24), f'{i + 1}', fill=(0, 0, 0), font=font); dr.text((x + 11, y - 2), f'{fz + 15:.0f}m', fill=(120, 0, 0), font=font)
q = race['StartTransform']['Rotation']; yaw = 2 * math.atan2(q['Z'], q['W']) + math.pi / 2       # flight direction = local +Y
x, y = px(*s_xy); dr.polygon([px(s_xy[0] + 8 * math.cos(yaw), s_xy[1] + 8 * math.sin(yaw)), px(s_xy[0] + 4 * math.cos(yaw + 2.5), s_xy[1] + 4 * math.sin(yaw + 2.5)), px(s_xy[0] + 4 * math.cos(yaw - 2.5), s_xy[1] + 4 * math.sin(yaw - 2.5))], fill=(0, 160, 0))
dr.text((x + 12, y + 8), 'START', fill=(0, 110, 0), font=font)
dr.text((20, 20), f'{os.path.basename(path)}: {len(race["CheckPoints"])} gates, red = straight legs, labels = gate number / opening height above the valley floor', fill=(0, 0, 0), font=font)
im.save(out); print('wrote', out)
