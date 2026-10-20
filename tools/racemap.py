#!/usr/bin/env python3
"""Top-down race plan: every mesh footprint in grey (structures darker), the road, numbered gates with their flight
height, the straight legs between them and the start arrow.   usage: racemap.py <map.json> <out.png> [half-size m]

Arguments
    <map.json>     map file as the game stores it (UTF-8 BOM tolerated).
    <out.png>      output image, 2000 x 2000 px.
    [half-size m]  half the side of the square world window drawn, centred on the world origin (default 400 m, i.e.
                   an 800 m square, which covers the flat bowl of the Mountain level).

Output: a PNG with +X to the right and +Y up (image rows are flipped), mesh footprints coloured by mesh type, red
lines for the straight legs start -> gate 1 -> ... -> start, each gate as a blue bar with its number and the opening
height, and a green arrow at the start pointing along the flight direction.

Units: the JSON is Unreal cm; raceline converts to metres and everything here (R, footprints, gate bar, arrow) is
metres. The height label is `opening z + 15`: the Mountain level's valley floor is exactly -15.00 m at the origin,
so the label reads as height above the valley floor (meaningless on other base levels).

Conventions relied on: gate opening centre from raceline.fly_point() (pivot + scaled BoxDetect offset); a gate's yaw
= flight bearing - 90 deg, so its frame runs along local X and the flight passes along local Y, which is why the bar
is drawn along X and the start arrow points along yaw + 90 deg. This is a script, not a library: it runs on import.
"""

import json, math, os, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raceline

path, out = sys.argv[1], sys.argv[2]
R = float(sys.argv[3]) if len(sys.argv) > 3 else 400.0
d = json.load(open(path, encoding='utf-8-sig'))
W = 2000
sc = W / (2 * R)  # pixels per metre
im = Image.new('RGB', (W, W), (235, 232, 224))
dr = ImageDraw.Draw(im)


def px(x, y):
    """World (x, y) in metres -> image pixel; the origin is the image centre, +X right, +Y up."""
    return (W / 2 + x * sc, W / 2 - y * sc)


# Mesh-name fragments that read as structure (drawn dark grey) rather than dressing (light grey) or foliage (green).
STRUCT_MESH = ('Concrete', 'Brick', 'Cube', 'Cylinder', 'Wall', 'Column', 'Container', 'Neo', 'Scaffold', 'Crane')
for o in raceline.load_obbs(d):
    mesh = raceline.CAT[o.row]['mesh'] or ''
    # load_obbs() already drops BaseGround/meWater rows, so the first two branches only matter if that filter changes.
    if 'BaseGround' in mesh:
        col = (210, 205, 195)
    elif 'Water' in mesh:
        col = (170, 200, 230)
    elif any(k in mesh for k in STRUCT_MESH):
        col = (90, 90, 100)
    elif 'Tree' in mesh or 'Elm' in mesh or 'Maple' in mesh or 'Pine' in mesh or 'Bush' in mesh:
        col = (150, 185, 140)
    else:
        col = (165, 160, 155)
    # Footprint = the box's local XY rectangle (scaled, origin offset applied) at local z = 0, pushed through the full
    # rotation's XY rows; exact for upright instances, an approximation for pitched or rolled ones.
    ex, ey = o.e[0] * abs(o.S[0]), o.e[1] * abs(o.S[1])
    ox, oy = o.o[0] * o.S[0], o.o[1] * o.S[1]
    corners = []
    for u, v in ((-ex, -ey), (ex, -ey), (ex, ey), (-ex, ey)):
        lx, ly = ox + u, oy + v
        wx = o.R[0][0] * lx + o.R[0][1] * ly + o.T[0]
        wy = o.R[1][0] * lx + o.R[1][1] * ly + o.T[1]
        corners.append(px(wx, wy))
    dr.polygon(corners, fill=col)
race = d['Race']
st = race['StartTransform']['Translation']
s_xy = (st['X'] / 100, st['Y'] / 100)
# Legs: start -> every gate opening -> back to start (the start point is the pivot: the start actor's box is there).
pts = [s_xy] + [(raceline.fly_point(cp)[0], raceline.fly_point(cp)[1]) for cp in race['CheckPoints']] + [s_xy]
for a, b in zip(pts, pts[1:]):
    dr.line([px(*a), px(*b)], fill=(220, 40, 40), width=4)
# `size=` needs Pillow >= 10.1; the hasattr guard is always true on any Pillow, so an older one raises here.
font = ImageFont.load_default(size=22) if hasattr(ImageFont, 'load_default') else None
for i, cp in enumerate(race['CheckPoints']):
    fx, fy, fz = raceline.fly_point(cp)
    q = cp['Transform']['Rotation']
    yaw = 2 * math.atan2(q['Z'], q['W'])
    c, s_ = math.cos(yaw), math.sin(yaw)
    hw = 3.0  # gate drawn as a bar along its local X (flight is along local Y)
    dr.line([px(fx - hw * c, fy - hw * s_), px(fx + hw * c, fy + hw * s_)], fill=(0, 90, 220), width=6)
    x, y = px(fx, fy)
    dr.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(255, 255, 255), outline=(0, 90, 220), width=2)
    g = raceline.CAT and None  # leftover no-op (always None); kept because this pass must not change behaviour
    dr.text((x + 11, y - 24), f'{i + 1}', fill=(0, 0, 0), font=font)
    # +15: height above the Mountain level's valley floor (-15 m), see the module docstring.
    dr.text((x + 11, y - 2), f'{fz + 15:.0f}m', fill=(120, 0, 0), font=font)
q = race['StartTransform']['Rotation']
yaw = 2 * math.atan2(q['Z'], q['W']) + math.pi / 2  # flight direction = local +Y
x, y = px(*s_xy)
# Arrow: 8 m tip along the flight direction, two 4 m barbs swept back by +/- 2.5 rad (about 143 deg).
dr.polygon(
    [
        px(s_xy[0] + 8 * math.cos(yaw), s_xy[1] + 8 * math.sin(yaw)),
        px(s_xy[0] + 4 * math.cos(yaw + 2.5), s_xy[1] + 4 * math.sin(yaw + 2.5)),
        px(s_xy[0] + 4 * math.cos(yaw - 2.5), s_xy[1] + 4 * math.sin(yaw - 2.5)),
    ],
    fill=(0, 160, 0),
)
dr.text((x + 12, y + 8), 'START', fill=(0, 110, 0), font=font)
dr.text(
    (20, 20),
    f'{os.path.basename(path)}: {len(race["CheckPoints"])} gates, red = straight legs, labels = gate number / opening height above the valley floor',
    fill=(0, 0, 0),
    font=font,
)
im.save(out)
print('wrote', out)
