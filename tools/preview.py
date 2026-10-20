"""Quick oblique preview of a generated map: draws every box/mesh as a shaded prism with a painter's algorithm."""

import json, math, sys
from PIL import Image, ImageDraw

path, out = sys.argv[1], sys.argv[2]
cx0, cy0, radius = (float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (0, -60, 260)
m = json.load(open(path))
cat = json.load(open('data/catalog.json'))


def dims(row):
    if row == 'NewRow_303':
        return (4, 4, 0.30, -0.29)
    if row == 'NewRow_318':
        return (0.3, 4, 4, 0)
    if row == 'NewRow_183':
        return (4, 4, 2.1, -2.05)
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
        return (4, 4, 0.1, -0.05)
    if row == 'NewRow_663':
        return (4, 4, 0.1, -0.05)
    b = cat.get(row, {}).get('bounds')
    if b:
        return (
            2 * b['extent'][0] / 100,
            2 * b['extent'][1] / 100,
            2 * b['extent'][2] / 100,
            (b['origin'][2] - b['extent'][2]) / 100,
        )
    return (1, 1, 1, -0.5)


COL = {
    'NewRow_303': (185, 178, 162),
    'NewRow_318': (150, 88, 66),
    'NewRow_256': (125, 128, 134),
    'NewRow_109': (36, 38, 44),
    'NewRow_46': (230, 190, 40),
    'NewRow_794': (170, 172, 160),
    'NewRow_795': (160, 165, 170),
    'NewRow_796': (178, 170, 150),
    'NewRow_797': (165, 160, 150),
    'NewRow_9': (140, 90, 70),
    'NewRow_95': (130, 95, 75),
    'NewRow_168': (60, 120, 50),
    'NewRow_269': (80, 140, 60),
    'NewRow_166': (90, 150, 70),
    'NewRow_251': (120, 120, 125),
    'NewRow_198': (170, 60, 40),
    'NewRow_103': (240, 200, 30),
    'NewRow_257': (235, 235, 235),
    'NewRow_93': (220, 220, 215),
    'NewRow_775': (200, 60, 50),
    'NewRow_3': (90, 90, 90),
    'NewRow_20': (90, 90, 90),
    'NewRow_323': (60, 60, 60),
    'NewRow_246': (200, 180, 60),
    'NewRow_252': (230, 120, 90),
    'NewRow_255': (230, 120, 90),
    'NewRow_801': (230, 120, 90),
    'NewRow_802': (230, 120, 90),
    'NewRow_254': (230, 120, 90),
    'NewRow_800': (230, 120, 90),
    'NewRow_217': (60, 200, 255),
    'NewRow_84': (200, 40, 40),
    'NewRow_13': (240, 240, 240),
    'NewRow_159': (120, 100, 80),
    'NewRow_164': (70, 130, 60),
    'NewRow_226': (70, 130, 60),
    'NewRow_208': (150, 150, 150),
    'NewRow_352': (220, 220, 220),
    'NewRow_52': (60, 90, 60),
    'NewRow_54': (160, 130, 90),
    'NewRow_189': (160, 130, 90),
    'NewRow_187': (120, 60, 40),
    'NewRow_350': (90, 90, 95),
    'NewRow_204': (110, 70, 50),
    'NewRow_323': (50, 50, 50),
    'NewRow_202': (240, 120, 30),
    'NewRow_100': (200, 200, 200),
    'NewRow_4': (255, 80, 220),
    'NewRow_148': (255, 150, 40),
    'NewRow_343': (80, 160, 255),
    'NewRow_213': (150, 140, 120),
    'NewRow_247': (200, 60, 60),
    'NewRow_9': (140, 90, 70),
    'NewRow_95': (130, 95, 75),
    'NewRow_166': (90, 150, 70),
    'NewRow_268': (80, 150, 60),
    'NewRow_79': (60, 120, 220),
    'NewRow_780': (170, 170, 170),
    'NewRow_287': (240, 140, 40),
    'NewRow_288': (240, 140, 40),
    'NewRow_289': (240, 140, 40),
    'NewRow_293': (240, 140, 40),
    'NewRow_295': (240, 140, 40),
    'NewRow_296': (240, 140, 40),
    'NewRow_643': (240, 140, 40),
    'NewRow_261': (130, 130, 135),
    'NewRow_183': (40, 90, 160),
    'NewRow_663': (90, 150, 60),
    'NewRow_182': (45, 45, 50),
    'NewRow_185': (200, 195, 185),
    'NewRow_197': (205, 200, 190),
    'NewRow_180': (120, 95, 70),
    'NewRow_181': (175, 165, 145),
    'NewRow_71': (130, 125, 120),
    'NewRow_162': (140, 130, 115),
    'NewRow_338': (240, 200, 40),
    'NewRow_335': (200, 50, 40),
    'NewRow_190': (120, 60, 50),
    'NewRow_196': (240, 180, 40),
    'NewRow_191': (240, 120, 40),
    'NewRow_188': (60, 80, 200),
    'NewRow_207': (150, 88, 66),
    'NewRow_224': (150, 88, 66),
    'NewRow_214': (150, 88, 66),
    'NewRow_321': (150, 88, 66),
    'NewRow_348': (150, 88, 66),
    'NewRow_327': (185, 178, 162),
    'NewRow_330': (185, 178, 162),
    'NewRow_122': (140, 90, 70),
    'NewRow_42': (125, 128, 134),
    'NewRow_39': (200, 200, 200),
    'NewRow_277': (170, 170, 175),
    'NewRow_317': (170, 170, 175),
    'NewRow_361': (185, 178, 162),
    'NewRow_1': (60, 110, 70),
    'NewRow_48': (200, 200, 210),
    'NewRow_50': (60, 90, 60),
    'NewRow_776': (170, 150, 110),
    'NewRow_291': (40, 40, 40),
    'NewRow_290': (40, 40, 40),
    'NewRow_157': (160, 120, 70),
    'NewRow_271': (160, 160, 165),
    'NewRow_45': (200, 180, 150),
    'NewRow_118': (190, 190, 200),
    'NewRow_49': (150, 150, 150),
    'NewRow_35': (120, 110, 100),
    'NewRow_279': (40, 90, 50),
    'NewRow_280': (40, 90, 50),
    'NewRow_281': (40, 90, 50),
    'NewRow_34': (60, 120, 50),
    'NewRow_78': (60, 120, 50),
    'NewRow_175': (130, 125, 120),
    'NewRow_245': (240, 240, 240),
    'NewRow_687': (120, 130, 100),
    'NewRow_770': (200, 200, 190),
    'NewRow_353': (150, 150, 150),
    'NewRow_315': (200, 170, 90),
    'NewRow_316': (200, 170, 90),
    'NewRow_74': (110, 90, 70),
    'NewRow_662': (210, 195, 160),
    'NewRow_276': (90, 90, 90),
    'NewRow_360': (185, 178, 162),
    'NewRow_362': (185, 178, 162),
    'NewRow_106': (160, 160, 160),
    'NewRow_18': (150, 150, 150),
    'NewRow_329': (120, 80, 50),
    'NewRow_80': (60, 120, 220),
    'NewRow_260': (170, 170, 175),
    'NewRow_310': (150, 60, 50),
    'NewRow_322': (120, 160, 120),
    'NewRow_788': (200, 120, 80),
    'NewRow_789': (200, 120, 80),
    'NewRow_790': (190, 170, 120),
    'NewRow_791': (190, 170, 120),
    'NewRow_793': (190, 170, 120),
    'NewRow_96': (130, 95, 75),
    'NewRow_97': (130, 95, 75),
    'NewRow_98': (130, 95, 75),
    'NewRow_297': (240, 100, 30),
    'NewRow_156': (170, 170, 170),
    'NewRow_78': (60, 120, 50),
    'NewRow_169': (60, 120, 50),
    'NewRow_119': (170, 170, 190),
    'NewRow_123': (170, 170, 190),
    'NewRow_120': (170, 170, 190),
    'NewRow_129': (170, 170, 190),
    'NewRow_11': (170, 170, 190),
    'NewRow_10': (170, 170, 190),
    'NewRow_24': (170, 170, 190),
    'NewRow_23': (170, 170, 190),
    'NewRow_344': (230, 230, 230),
    'NewRow_342': (160, 120, 80),
    'NewRow_339': (160, 120, 80),
    'NewRow_165': (220, 60, 60),
}
W, H = 1600, 1100
# oblique camera: look toward +X? We view from the south-east (-X,+Y) looking north-west, 35 deg elevation
az = math.radians(-135)
el = math.radians(38)


def project(x, y, z):
    dx, dy = x - cx0, y - cy0
    u = -dx * math.sin(az) + dy * math.cos(az)
    v = -(dx * math.cos(az) + dy * math.sin(az))
    depth = dx * math.cos(az) + dy * math.sin(az)
    sc = W / (2.4 * radius)
    return (W / 2 + u * sc, H * 0.62 - (v * math.sin(el) + z * math.cos(el)) * sc, depth + z * 0.3)


items = []
for a in m['S_AssetsTransform']:
    row = a['Rname']
    if row.startswith('decal_'):
        continue
    bx, by, bz, zoff = dims(row)
    for t in a['Transform']:
        s = t['Scale3D']
        x, y, z = t['Translation']['X'] / 100, t['Translation']['Y'] / 100, t['Translation']['Z'] / 100
        if math.hypot(x - cx0, y - cy0) > radius * 1.3:
            continue
        lx, ly, lz = s['X'] * bx, s['Y'] * by, s['Z'] * bz
        if lx > 1500 and row not in ('NewRow_268', 'NewRow_303'):
            continue  # huge ground slabs (park lawn base, city slab) are drawn as ground
        yaw = 2 * math.atan2(t['Rotation']['Z'], t['Rotation']['W'])
        z0 = z + zoff * s['Z'] if row not in ('NewRow_303',) else z - 0.29 * s['Z']
        if row in (
            'NewRow_13',
            'NewRow_256',
            'NewRow_109',
            'NewRow_46',
            'NewRow_14',
            'NewRow_261',
            'NewRow_113',
            'NewRow_103',
            'NewRow_257',
            'NewRow_93',
            'NewRow_775',
        ):
            z0 = z - lz / 2
        items.append((row, x, y, z0, lx, ly, lz, yaw))
img = Image.new('RGB', (W, H), (150, 170, 190))
d = ImageDraw.Draw(img)


def prism(row, x, y, z0, lx, ly, lz, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    corners = [
        (x + ux * c - vy * s, y + ux * s + vy * c)
        for ux, vy in ((-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2))
    ]
    base = COL.get(row, (200, 120, 200))
    faces = []
    top = [project(px, py, z0 + lz) for px, py in corners]
    for i in range(4):
        p, q = corners[i], corners[(i + 1) % 4]
        nx, ny = (q[1] - p[1]), -(q[0] - p[0])  # outward normal (depends on winding; shade by light dir magnitude)
        light = 0.55 + 0.45 * max(0, (nx * 0.3 + ny * -0.95) / (math.hypot(nx, ny) + 1e-9))
        faces.append(
            (
                [project(*p, z0), project(*q, z0), project(*q, z0 + lz), project(*p, z0 + lz)],
                tuple(int(v * light) for v in base),
            )
        )
    faces.append((top, tuple(min(255, int(v * 1.05)) for v in base)))
    return faces


polys = []
for it in items:
    for pts, col in prism(*it):
        flat = it[6] < 0.5
        polys.append(
            (
                0 if flat else 1,
                (it[3] + it[6]) if flat else -sum(p[2] for p in pts) / len(pts),
                [(p[0], p[1]) for p in pts],
                col,
            )
        )
polys.sort(key=lambda p: (p[0], p[1]))  # flat layers by top height, then solids back to front
for _, _, pts, col in polys:
    d.polygon(pts, fill=col)
img.save(out)
print('drawn', len(items), 'items')
