#!/usr/bin/env python3
"""Central Park for Uncrashed, built from OpenStreetMap (data/centralpark_osm.json via tools/osm.py) on the flat
Empty board. Frame: origin on the Mall at the Literary Walk, the Mall runs up -Y (the freestyle spawn faces -Y, so
you take off looking up the elm walk to Bethesda Terrace), +X is west. Every lake, lawn, wood, rock outcrop, path,
drive, arch and building comes from OSM geometry; landmarks that OSM only names (Bethesda Fountain, Belvedere on
Vista Rock, the Obelisk, Bow Bridge, the Mall's elm rows, the Imagine mosaic) are modelled on top of it. The
surrounding city uses OSM building footprints with their heights. Aerial reference: data/centralpark_naip.png.
usage: build_centralpark.py [--no-windows] [--lite]"""
import json, math, os, sys, time, hashlib, shutil, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geom import poly_area, centroid, min_rect, point_in_poly, decompose, rect_faces, l2w
from osm import Frame
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); DATA = os.path.join(ROOT, 'data')
STEAM_ID = os.environ.get('UNCRASHED_STEAM_ID', '76561197969360950')   # your Steam ID64: the game loads maps from MapEditor/User under it
GAME_USER_MAPS = os.path.expanduser(f'~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User')
NAME, DISPLAY = 'CentralPark', 'New York City - Central Park'
WITH_WINDOWS = '--no-windows' not in sys.argv; LITE = '--lite' in sys.argv
rng = random.Random(7)
FRAME = json.load(open(os.path.join(DATA, 'centralpark_frame.json'))); FR = Frame(FRAME['lat0'], FRAME['lon0'], FRAME['axis_deg'], True)
F = json.load(open(os.path.join(DATA, 'centralpark_features.json'))); CAT = json.load(open(os.path.join(DATA, 'catalog.json')))
for _p in F['polys']: _p['pts'] = [tuple(q) for q in _p['pts']]; _p['holes'] = [[tuple(q) for q in h] for h in _p['holes']]
for _l in F['lines']: _l['pts'] = [tuple(q) for q in _l['pts']]
BOARD = 2900.0                                  # keep inside the 6 km Empty board
Z0 = 0.06                                       # ground top (the board's landscape is at 0)

# ---- rows ----------------------------------------------------------------------
CUBE = dict(default='NewRow_13', yellow='NewRow_46', blue='NewRow_79', red='NewRow_84', green='NewRow_268', grey='NewRow_256', violet='NewRow_378', black='NewRow_109')
CYL = dict(default='NewRow_14', grey='NewRow_261', black='NewRow_113', yellow='NewRow_64', red='NewRow_89')
CONCRETE, BRICK, PYRAMID = 'NewRow_303', 'NewRow_318', 'NewRow_143'
ASPHALT, PAVE, PAVE2, DIRT, GRAVEL, SAND, WATER = 'NewRow_182', 'NewRow_185', 'NewRow_197', 'NewRow_180', 'NewRow_181', 'NewRow_662', 'NewRow_183'
ELM, MAPLE, ALDER, OAK, BIG_ELM, PINES = 'NewRow_168', 'NewRow_269', 'NewRow_34', 'NewRow_78', 'NewRow_169', ['NewRow_279', 'NewRow_280', 'NewRow_281']
TREES = [ELM, MAPLE, ALDER]; BUSHES = ['NewRow_164', 'NewRow_226']; ROCKS = ['NewRow_71', 'NewRow_162']; CLIFF = 'NewRow_175'
LAMP_TALL, LAMP_SHORT, BENCH, TRASH, FENCE, HANDRAIL, STATUE = 'NewRow_3', 'NewRow_20', 'NewRow_204', 'NewRow_323', 'NewRow_777', 'NewRow_276', 'NewRow_213'
PEOPLE, PEOPLE_SIT = ['NewRow_252', 'NewRow_255', 'NewRow_801', 'NewRow_802'], ['NewRow_254', 'NewRow_800']
CARS = ['NewRow_103', 'NewRow_257', 'NewRow_93', 'NewRow_775']; BOAT, FOOD_CART, FOOD_STALL, TABLE, CHAIR = 'NewRow_329', 'NewRow_246', 'NewRow_247', 'NewRow_353', 'NewRow_352'
STAIRS, WATER_TOWER, PLANTER = 'NewRow_106', 'NewRow_251', 'NewRow_159'
def rest(row):
    b = CAT.get(row, {}).get('bounds')
    if not b: return 0.0
    bot = (b['origin'][2] - b['extent'][2]) / 100.0; return -bot if bot > 0.05 else 0.0

instances = {}; decal_rows = {}; decal_files = {}; stats = {}
def st(k, n=1): stats[k] = stats.get(k, 0) + n
def quat_yaw(yaw): return dict(X=0.0, Y=0.0, Z=math.sin(yaw / 2), W=math.cos(yaw / 2))
def quat_pitch_yaw(pitch_deg, yaw_deg):
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2; SP, CP, SY, CY = math.sin(P), math.cos(P), math.sin(Y), math.cos(Y)
    return dict(X=SP * SY, Y=-SP * CY, Z=CP * SY, W=CP * CY)
def quat_from_axes(X, Y, Z):
    m = [[X[0], Y[0], Z[0]], [X[1], Y[1], Z[1]], [X[2], Y[2], Z[2]]]; t = m[0][0] + m[1][1] + m[2][2]
    if t > 0: s = math.sqrt(t + 1) * 2; w = s / 4; x = (m[2][1] - m[1][2]) / s; y = (m[0][2] - m[2][0]) / s; z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]: s = math.sqrt(1 + m[0][0] - m[1][1] - m[2][2]) * 2; w = (m[2][1] - m[1][2]) / s; x = s / 4; y = (m[0][1] + m[1][0]) / s; z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]: s = math.sqrt(1 + m[1][1] - m[0][0] - m[2][2]) * 2; w = (m[0][2] - m[2][0]) / s; x = (m[0][1] + m[1][0]) / s; y = s / 4; z = (m[1][2] + m[2][1]) / s
    else: s = math.sqrt(1 + m[2][2] - m[0][0] - m[1][1]) * 2; w = (m[1][0] - m[0][1]) / s; x = (m[0][2] + m[2][0]) / s; y = (m[1][2] + m[2][1]) / s; z = s / 4
    return dict(X=x, Y=y, Z=z, W=w)
def decal_rot(normal_yaw):
    c, s = math.cos(normal_yaw), math.sin(normal_yaw); return quat_from_axes((-c, -s, 0.0), (0.0, 0.0, -1.0), (s, -c, 0.0))
def tf(x, y, z, rot, s=(1, 1, 1)): return dict(Rotation=rot, Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)), Scale3D=dict(X=round(s[0], 4), Y=round(s[1], 4), Z=round(s[2], 4)))
def add(row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0, rot=None, store=None):
    if abs(x) > BOARD or abs(y) > BOARD: return
    (store if store is not None else instances).setdefault(row, []).append(tf(x, y, z, rot if rot else quat_yaw(yaw), (sx, sy, sz)))
def box(kind, cx, cy, z0, h, lx, ly, yaw=0.0):
    lx, ly, h = max(lx, 0.1), max(ly, 0.1), max(h, 0.01)
    if kind == 'concrete': sz = h / 0.30; add(CONCRETE, cx, cy, z0 + 0.29 * sz, lx / 4, ly / 4, sz, yaw)
    elif kind == 'brick': add(BRICK, cx, cy, z0, lx / 0.3, ly / 4, h / 4, yaw)
    else: add(CUBE[kind], cx, cy, z0 + h / 2, lx, ly, h, yaw)
def cylinder(kind, cx, cy, z0, h, d): add(CYL[kind], cx, cy, z0 + h / 2, d, d, h)
def plane(row, x, y, z_top, lx, ly, yaw=0.0): add(row, x, y, z_top - 0.05, max(lx, 0.5) / 4, max(ly, 0.5) / 4, 1.0, yaw); st('planes')
def pitched(kind, x0, y0, z0, x1, y1, z1, width, thick=0.4):
    L = math.hypot(x1 - x0, y1 - y0); yaw = math.degrees(math.atan2(y1 - y0, x1 - x0)); pitch = math.degrees(math.atan2(z1 - z0, L))
    add(CUBE[kind], (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2 - thick / 2, math.hypot(L, z1 - z0), width, thick, rot=quat_pitch_yaw(pitch, yaw))
def put(row, x, y, dz=0.0, s=1.0, yaw=0.0): add(row, x, y, Z0 + dz + rest(row) * s, s, s, s, yaw)
def ll(lat, lon): return FR.xy(lat, lon)

# ---- the park polygon and an occupancy grid (4 m) -----------------------------------
PARK = max((p for p in F['polys'] if p['kind'] == 'park' and p['tags'].get('name') == 'Central Park'), key=lambda p: poly_area(p['pts']))['pts']
pcx, pcy, plx, ply, pth = min_rect(PARK); print(f'park rectangle {plx:.0f} x {ply:.0f} m, yaw {math.degrees(pth):.1f} deg, centre ({pcx:.0f},{pcy:.0f})')
CELL = 4.0; GX0, GY0 = -800, -3800; GNX, GNY = int(1600 / CELL), int(4500 / CELL)
occ = bytearray(GNX * GNY)                      # 0 free, 1 path, 2 water, 3 hard (plaza/building/rock), 4 lawn (keep clear of trees), 5 wood
def cell(x, y): return (int((x - GX0) // CELL), int((y - GY0) // CELL))
def mark(x, y, v):
    i, j = cell(x, y)
    if 0 <= i < GNX and 0 <= j < GNY: occ[j * GNX + i] = v
def occ_at(x, y):
    i, j = cell(x, y); return occ[j * GNX + i] if 0 <= i < GNX and 0 <= j < GNY else 3
def mark_poly(pts, v, holes=()):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    for j in range(int((min(ys) - GY0) // CELL), int((max(ys) - GY0) // CELL) + 1):
        for i in range(int((min(xs) - GX0) // CELL), int((max(xs) - GX0) // CELL) + 1):
            x, y = GX0 + (i + 0.5) * CELL, GY0 + (j + 0.5) * CELL
            if point_in_poly(x, y, pts) and not any(point_in_poly(x, y, h) for h in holes): mark(x, y, v)
def in_park(x, y): return point_in_poly(x, y, PARK)
def mark_line(pts, w, v):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0); n = max(1, int(L / 2))
        for k in range(n + 1):
            t = k / n; x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for dx in (-w / 2, 0, w / 2):
                for dy in (-w / 2, 0, w / 2): mark(x + dx, y + dy, v)

# ---- 1. ground: city slab, park lawn base --------------------------------------------
box('concrete', 0, -1200, Z0 - 0.30, 0.30, 2 * BOARD, 2 * BOARD)
box('green', pcx, pcy, Z0 - 0.02, 0.06, plx, ply, pth); st('park_base')

# ---- 2. surfaces from OSM polygons ---------------------------------------------------
def fill_rects(pts, max_rects=12):
    return decompose(pts, max_rects) if poly_area(pts) > 30 else [min_rect(pts)]
water_tiles = 0
for p in F['polys']:
    k, pts, tags = p['kind'], p['pts'], p['tags']; cx, cy = centroid(pts); a = poly_area(pts)
    if abs(cx) > BOARD or abs(cy) > BOARD: continue
    inside = in_park(cx, cy)
    if k == 'water' and a > 40:
        tile = 4.0 if (inside and cy > -1300 and a < 3e4) else (8.0 if a < 20e4 else 16.0)      # 4 m tiles only on the small ponds; the Lake and Reservoir use 8 / 16 m
        if not inside and a > 50e4: tile = 24.0                                                   # the rivers
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        for j in range(int(min(ys) // tile), int(max(ys) // tile) + 1):
            for i in range(int(min(xs) // tile), int(max(xs) // tile) + 1):
                x, y = (i + 0.5) * tile, (j + 0.5) * tile
                if point_in_poly(x, y, pts) and not any(point_in_poly(x, y, h) for h in p['holes']):
                    add(WATER, x, y, Z0 + 0.03, tile / 4, tile / 4, 1.2); water_tiles += 1
        mark_poly(pts, 2, p['holes'])
        if inside and a > 3e4 and tags.get('name') == 'The Lake':
            for _ in range(16):
                x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
                if point_in_poly(x, y, pts) and all(math.hypot(x - q[0], y - q[1]) > 12 for q in pts[::3]): put(BOAT, x, y, 0.05, 1.0, rng.uniform(0, 6.28)); st('boats')
        if tags.get('name') == 'Conservatory Water':
            for _ in range(8): x, y = rng.uniform(cx - 25, cx + 25), rng.uniform(cy - 25, cy + 25); put(BOAT, x, y, 0.04, 0.3, rng.uniform(0, 6.28)) if point_in_poly(x, y, pts) else None
        if tags.get('name') in ('Jacqueline Kennedy Onassis Reservoir',):                       # the iron fence and the running track
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
                L = math.hypot(x1 - x0, y1 - y0); n = max(1, int(L // 4)); yaw = math.atan2(y1 - y0, x1 - x0)
                for q in range(n):
                    t = (q + 0.5) / n; add(FENCE, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, Z0, 1, 1, 0.8, yaw); st('fences')
    elif k in ('plaza', 'parking', 'rink') and inside and a > 20:
        row = ASPHALT if k == 'parking' else (PAVE2 if k == 'rink' else PAVE)
        for (rx, ry, lx, ly, th) in fill_rects(pts, 20): plane(row, rx, ry, Z0 + 0.03, lx, ly, th)
        mark_poly(pts, 3)
        if k == 'rink':
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]): box('default', (x0 + x1) / 2, (y0 + y1) / 2, Z0, 1.0, math.hypot(x1 - x0, y1 - y0), 0.15, math.atan2(y1 - y0, x1 - x0))
            for _ in range(30):
                x, y = rng.uniform(cx - 30, cx + 30), rng.uniform(cy - 30, cy + 30)
                if point_in_poly(x, y, pts): put(rng.choice(PEOPLE), x, y, 0.03, 1.0, rng.uniform(0, 6.28)); st('skaters')
    elif k == 'grass' and inside:
        mark_poly(pts, 4)
        if 'Ball Field' in (tags.get('name') or '') or tags.get('sport') == 'baseball':
            plane(DIRT, cx, cy, Z0 + 0.03, 26, 26, pth + math.pi / 4); st('ballfields')
            for q in range(5): add(FENCE, *l2w(cx, cy, pth + math.pi / 4, -13 + 1 * q, -12), Z0, 1, 1, 1.4, pth + math.pi / 4)
    elif k == 'wood' and inside: mark_poly(pts, 5)
    elif k == 'rock' and inside and a > 40:
        mark_poly(pts, 3)
        for (rx, ry, lx, ly, th) in fill_rects(pts, 6):
            h = min(2.5, 0.5 + math.sqrt(lx * ly) / 12); box('grey', rx, ry, Z0, h, lx * 0.9, ly * 0.9, th)
        for _ in range(max(2, int(a // 150))):
            x, y = rng.uniform(cx - 15, cx + 15), rng.uniform(cy - 15, cy + 15)
            if point_in_poly(x, y, pts): s = rng.uniform(1.2, 2.6); put(rng.choice(ROCKS + [CLIFF]), x, y, 0.3, s, rng.uniform(0, 6.28)); st('rocks')
    elif k == 'fountain' and inside and a > 20:
        cylinder('grey', cx, cy, Z0, 0.7, 2 * math.sqrt(a / math.pi)); cylinder('grey', cx, cy, Z0, 2.5, 1.6)
        for j in range(-3, 4):
            for i in range(-3, 4):
                if point_in_poly(cx + i * 4, cy + j * 4, pts): add(WATER, cx + i * 4, cy + j * 4, Z0 + 0.6, 1, 1, 1)
        mark_poly(pts, 3); st('fountains')
print('water tiles', water_tiles)

# ---- 3. paths, drives, transverses, bridges ------------------------------------------
PATH_W = dict(footway=3.6, path=3.0, pedestrian=7.0, bridleway=4.0, cycleway=4.0, steps=3.0, service=8.0, residential=11.0, tertiary=12.0, secondary=14.0, primary=18.0, unclassified=10.0, living_street=8.0)
def parse_width(v):
    """OSM width: '3.5', '3.5 m', '28'0"', '12 ft' -> metres (0 if unparseable)."""
    if not v: return 0.0
    v = str(v).strip().lower()
    try:
        if "'" in v: ft, _, inch = v.partition("'"); return (float(ft) + float(inch.replace('"', '') or 0) / 12) * 0.3048
        if 'ft' in v: return float(v.replace('ft', '').strip()) * 0.3048
        return float(v.replace('m', '').strip())
    except ValueError: return 0.0
def is_drive(l): return (l['tags'].get('name') or '').endswith('Drive') or l['kind'] == 'service' and in_park(*l['pts'][0])
def is_transverse(l): return 'Transverse' in (l['tags'].get('name') or '') and l['kind'] in ('tertiary', 'secondary', 'residential')
path_lines = []
for l in F['lines']:
    k = l['kind']; pts = l['pts']
    if k not in PATH_W or len(pts) < 2: continue
    inside = in_park(*pts[len(pts) // 2])
    if not inside and k in ('footway', 'path', 'steps', 'pedestrian', 'bridleway', 'cycleway'): continue
    if l['tags'].get('tunnel') == 'yes' and not inside: continue
    w = parse_width(l['tags'].get('width')) or PATH_W[k]
    if is_drive(l): w = max(w, 12.0); row = ASPHALT
    elif is_transverse(l): w = 12.0; row = ASPHALT
    elif k in ('footway', 'path', 'steps', 'pedestrian'): row = PAVE if inside else PAVE
    elif k == 'bridleway': row = DIRT
    elif k == 'cycleway': row = ASPHALT
    else: row = ASPHALT
    bridge = l['tags'].get('bridge') == 'yes'
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.5: continue
        n = max(1, int(math.ceil(L / 22))); yaw = math.atan2(y1 - y0, x1 - x0)
        for q in range(n):
            t0, t1 = q / n, (q + 1) / n; mx, my = x0 + (x1 - x0) * (t0 + t1) / 2, y0 + (y1 - y0) * (t0 + t1) / 2
            if bridge and inside: box('grey', mx, my, Z0 + 2.6, 0.4, L / n + 0.5, w, yaw); st('bridge_decks')
            else: plane(row, mx, my, Z0 + (0.04 if row == ASPHALT else 0.05), L / n + 0.6, w, yaw)
    mark_line(pts, w, 1)
    path_lines.append((pts, w, row, inside, k, l['tags'].get('name') or '', bridge))
    if not inside and k in ('residential', 'tertiary', 'secondary', 'primary') and not LITE:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0); yaw = math.atan2(y1 - y0, x1 - x0)
            if L < 6: continue
            for side in (-1, 1): plane(PAVE, *l2w((x0 + x1) / 2, (y0 + y1) / 2, yaw, 0, side * (w / 2 + 2.2)), Z0 + 0.06, L, 4.0, yaw)
            if L > 20 and w >= 11: box('yellow', (x0 + x1) / 2, (y0 + y1) / 2, Z0 + 0.05, 0.01, L - 6, 0.3, yaw)
st('path_lines', len(path_lines))
# arches and bridges with a mapped outline (man_made=bridge): raised deck, stone abutments, handrails -> a fly-through
for l in F['lines']:
    if l['kind'] != 'bridge' or len(l['pts']) < 4 or not in_park(*l['pts'][0]): continue
    cx, cy, lx, ly, th = min_rect(l['pts']); L, W = (lx, ly) if lx >= ly else (ly, lx); th = th if lx >= ly else th + math.pi / 2
    H = 3.2 if W < 8 else 4.0; name = l['tags'].get('name') or ''
    box('concrete', cx, cy, Z0 + H, 0.5, L, W, th)
    for sgn in (-1, 1):
        ax, ay = l2w(cx, cy, th, sgn * (L / 2 - 1.0), 0); box('brick', ax, ay, Z0, H, 2.0, W, th)           # abutments: the arch opening is between them
        for q in range(int(L // 2)): add(HANDRAIL, *l2w(cx, cy, th, -L / 2 + 1 + q * 2, sgn * (W / 2 - 0.3)), Z0 + H + 0.5, 1, 1, 1, th)
        rx, ry = l2w(cx, cy, th, sgn * (L / 2 + 6), 0); pitched('grey', *l2w(cx, cy, th, sgn * (L / 2 + 12), 0), Z0 + 0.05, *l2w(cx, cy, th, sgn * L / 2, 0), Z0 + H + 0.5, W)
    if 'Bow' in name:                                                                                             # Bow Bridge: a shallow cast-iron arch, 26 m, rises 2.5 m over the water
        for sgn in (-1, 1): box('default', *l2w(cx, cy, th, 0, sgn * (W / 2 - 0.2)), Z0 + H + 0.5, 1.0, L, 0.2, th)
    st('arches')

# ---- 4. the Mall, Bethesda Terrace and Fountain --------------------------------------
MALL_Y0, MALL_Y1 = 40.0, -330.0
plane(PAVE2, 0, (MALL_Y0 + MALL_Y1) / 2, Z0 + 0.06, 12.0, MALL_Y0 - MALL_Y1); mark_line([(0, MALL_Y0), (0, MALL_Y1)], 12, 1)
for y in range(int(MALL_Y1), int(MALL_Y0), 12):
    for x in (-8.5, 8.5, -16.5, 16.5): s = rng.uniform(1.15, 1.45); put(BIG_ELM if abs(x) < 10 else ELM, x + rng.uniform(-0.4, 0.4), y + rng.uniform(-0.5, 0.5), 0, s, rng.uniform(0, 6.28)); st('mall_elms')
    for x in (-6.6, 6.6): put(BENCH, x, y + 6, 0, 1.0, math.pi / 2 if x < 0 else -math.pi / 2); st('benches')
    if (y // 12) % 3 == 0:
        for x in (-7.2, 7.2): put(LAMP_SHORT, x, y + 1, 0, 1.0, 0); st('lamps')
for (nm, x, y) in [(p['tags']['name'], p['x'], p['y']) for p in F['points'] if p['kind'] in ('artwork', 'memorial') and p['tags'].get('name') and in_park(p['x'], p['y'])]:
    box('grey', x, y, Z0, 1.6, 1.4, 1.4); put(STATUE, x, y, 1.6, 1.3, rng.uniform(0, 6.28)); st('statues')
# Bethesda Terrace: Terrace Drive crosses on a 4 m embankment over the arcade; twin stairs drop to the fountain plaza
ARC = next(l for l in F['lines'] if l['tags'].get('name') == 'Bethesda Arcade'); ax0, ay0 = ARC['pts'][0]; ax1, ay1 = ARC['pts'][-1]
acx, acy = (ax0 + ax1) / 2, (ay0 + ay1) / 2; ayaw = math.atan2(ay1 - ay0, ax1 - ax0)
box('concrete', acx, acy, Z0 + 4.0, 0.6, 16, 70, ayaw); plane(ASPHALT, acx, acy, Z0 + 4.65, 12, 70, ayaw)
for sgn in (-1, 1):
    box('brick', *l2w(acx, acy, ayaw, sgn * 7.5, 0), Z0, 4.0, 1.0, 70, ayaw)                                   # arcade side walls (16 m wide passage under the drive)
    for u in (-30, -18, 18, 30): add(HANDRAIL, *l2w(acx, acy, ayaw, sgn * 7.0, u), Z0 + 4.7, 1, 1, 1, ayaw + math.pi / 2)
    pitched('grey', *l2w(acx, acy, ayaw, sgn * 14, 0), Z0 + 4.6, *l2w(acx, acy, ayaw, sgn * 26, 0), Z0 + 0.05, 8.0)                 # grand stairs down to the plaza
FX, FY = l2w(acx, acy, ayaw, 0, -48)                                                                                # fountain plaza north of the arcade (toward the Lake)
plane(PAVE2, FX, FY, Z0 + 0.06, 70, 60, ayaw); mark_poly([l2w(FX, FY, ayaw, u, v) for (u, v) in ((-35, -30), (35, -30), (35, 30), (-35, 30))], 3)
cylinder('grey', FX, FY, Z0, 0.9, 29.0); cylinder('grey', FX, FY, Z0, 3.0, 3.0); cylinder('grey', FX, FY, Z0 + 3.0, 1.2, 6.0); cylinder('grey', FX, FY, Z0 + 4.2, 2.2, 1.2)
for j in range(-3, 4):
    for i in range(-3, 4):
        if math.hypot(i * 4, j * 4) < 13: add(WATER, FX + i * 4, FY + j * 4, Z0 + 0.75, 1, 1, 1)
put(STATUE, FX, FY, 6.4, 2.4, ayaw + math.pi); st('bethesda')
for q in range(40): a = q / 40 * 6.283; put(rng.choice(PEOPLE), FX + 17 * math.cos(a), FY + 17 * math.sin(a), 0.06, 1.0, a + math.pi)
# ---- 5. hand-placed landmarks OSM only names ---------------------------------------------
OBX, OBY = ll(40.77962, -73.96541)                                                                             # Cleopatra's Needle, 21 m, on its granite base
box('black', OBX, OBY, Z0, 2.2, 5, 5); box('grey', OBX, OBY, Z0 + 2.2, 18.5, 2.4, 2.4); add(PYRAMID, OBX, OBY, Z0 + 21.7, 2.4, 2.4, 2.0, 0); plane(PAVE2, OBX, OBY, Z0 + 0.06, 24, 24); st('obelisk')
IMX, IMY = next(((p['x'], p['y']) for p in F['points'] if p['tags'].get('name') == 'Strawberry Fields' and p['kind'] == 'memorial'), ll(40.77565, -73.97524))
plane(PAVE2, IMX, IMY, Z0 + 0.06, 24, 24); st('imagine')
for q in range(10): a = q / 10 * 6.283; put(BENCH, IMX + 11 * math.cos(a), IMY + 11 * math.sin(a), 0, 1.0, a + math.pi / 2)
TGX, TGY = ll(40.77215, -73.97785)                                                                             # Tavern on the Green (OSM has no footprint for it here)
box('brick', TGX, TGY, Z0, 7.0, 40, 22, pth); box('concrete', TGX, TGY, Z0 + 7.0, 0.5, 42, 24, pth); plane(PAVE2, *l2w(TGX, TGY, pth, 0, 18), Z0 + 0.06, 40, 12, pth)
for q in range(10): put(TABLE, *l2w(TGX, TGY, pth, -18 + q * 4, 18), 0, 1.0, pth); put(CHAIR, *l2w(TGX, TGY, pth, -18 + q * 4, 19.5), 0, 1.0, pth + math.pi)
CHX, CHY = ll(40.77465, -73.97345)                                                                             # Cherry Hill fountain and turnaround
plane(PAVE2, CHX, CHY, Z0 + 0.06, 40, 40); cylinder('grey', CHX, CHY, Z0, 0.8, 7.0); cylinder('grey', CHX, CHY, Z0, 3.5, 0.8); st('cherry_hill')
# ---- 6. buildings: park structures and the city ---------------------------------------
SUPERTALL = {'One57': 306, 'Central Park Tower': 472, '111 West 57th Street': 435, 'Steinway Tower': 435, '432 Park Avenue': 426, '220 Central Park South': 290, '53 West 53': 320, 'Carnegie Hall Tower': 231, 'Metropolitan Tower': 218, 'Trump International Hotel and Tower': 177, 'Time Warner Center': 229, 'Deutsche Bank Center': 229, 'The Plaza': 76, 'Essex House': 155, 'Hampshire House': 105}
def material_for(h, tags, key):
    hv = int(hashlib.md5(key.encode()).hexdigest()[:4], 16) / 65535; col = (tags.get('building:colour') or '').lower()
    if tags.get('building') in ('church', 'cathedral', 'synagogue', 'museum', 'hotel') and h < 90: return 'concrete'
    if h >= 150: return 'black' if hv < 0.7 else 'grey'
    if h >= 60: return 'black' if hv < 0.45 else ('grey' if hv < 0.75 else 'concrete')
    if 'brick' in col or 'red' in col or 'brown' in col: return 'brick'
    return 'brick' if hv < 0.5 else 'concrete'
facades = []; bld_count = 0; building_rects = []
park_x_min, park_x_max = min(q[0] for q in PARK), max(q[0] for q in PARK)
def near_park(x, y):
    return (-420 < y < 160 and abs(x) < 900) or (y <= 160 and abs(x) - 420 < 350) or (y >= 160 and (abs(x) < 700))
for p in F['polys']:
    if p['kind'] not in ('building',): continue
    pts, tags = p['pts'], p['tags']; cx, cy = centroid(pts); a = poly_area(pts)
    if a < 10 or abs(cx) > BOARD or abs(cy) > BOARD: continue
    nm = tags.get('name') or ''; h = 0.0
    try: h = float(str(tags.get('height', '')).replace('m', '').strip() or 0)
    except ValueError: h = 0.0
    if not h and tags.get('building:levels'):
        try: h = float(tags['building:levels']) * 3.4
        except ValueError: h = 0.0
    for key, hh in SUPERTALL.items():
        if key.lower() in nm.lower(): h = max(h, hh)
    inside = in_park(cx, cy)
    if not h: h = 6.0 if inside else (22.0 if a < 800 else 35.0)
    if LITE and not inside and math.hypot(cx, cy + 1200) > 1900 and a < 400: continue
    kind = material_for(h, tags, str(p['pts'][0])); bld_count += 1
    if inside: mark_poly(pts, 3)
    if nm == 'Belvedere Castle':                                                                                   # Vista Rock mound, then the castle and its tower
        for k, (sc, hh) in enumerate(((1.0, 4.0), (0.8, 4.0), (0.62, 3.5))):
            rx, ry, lx, ly, th = min_rect(pts); box('grey', rx, ry, Z0 + sum(x[1] for x in ((1.0, 4.0), (0.8, 4.0), (0.62, 3.5))[:k]), hh, (lx + 30) * sc, (ly + 30) * sc, th)
        rx_, ry_, lx_, ly_, th_ = min_rect(pts)
        for _ in range(30):                                                                                        # rocks sit on the mound tier they land on
            u, v = rng.uniform(-(lx_ + 30) / 2, (lx_ + 30) / 2), rng.uniform(-(ly_ + 30) / 2, (ly_ + 30) / 2); fx_, fy_ = l2w(rx_, ry_, th_, u, v)
            fr_ = max(abs(u) / ((lx_ + 30) / 2), abs(v) / ((ly_ + 30) / 2)); dz = 11.5 if fr_ <= 0.62 else (8.0 if fr_ <= 0.8 else 4.0)
            put(rng.choice(ROCKS + [CLIFF]), fx_, fy_, dz - 0.3, rng.uniform(1.5, 3.0), rng.uniform(0, 6.28))
        base = Z0 + 11.5
        for (rx, ry, lx, ly, th) in fill_rects(pts, 6): box('brick', rx, ry, base, 9.0, lx, ly, th); box('concrete', rx, ry, base + 9.0, 0.5, lx + 0.6, ly + 0.6, th)
        rx, ry, lx, ly, th = min_rect(pts); tx, ty = l2w(rx, ry, th, lx * 0.3, 0)
        cylinder('grey', tx, ty, base, 20.0, 7.0); cylinder('grey', tx, ty, base + 20, 2.0, 8.0); add(PYRAMID, tx, ty, base + 22.0, 7, 7, 6, 0)
        for q in range(12): a_ = q / 12 * 6.283; box('grey', tx + 4.2 * math.cos(a_), ty + 4.2 * math.sin(a_), base + 20.5, 1.2, 1.0, 1.0, a_)
        plane(PAVE2, *l2w(rx, ry, th, -lx * 0.5 - 8, 0), base + 0.06, 16, ly + 10, th); st('belvedere'); continue
    if nm == 'Delacorte Theater':
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]): box('brick', (x0 + x1) / 2, (y0 + y1) / 2, Z0, 6.0, math.hypot(x1 - x0, y1 - y0), 0.5, math.atan2(y1 - y0, x1 - x0))
        box('concrete', cx, cy, Z0, 1.2, 20, 14, pth); st('delacorte'); continue
    if nm == 'Central Park Carousel':
        cylinder('default', cx, cy, Z0, 5.0, 16.0); add(PYRAMID, cx, cy, Z0 + 7.5, 18, 18, 5, 0)
        for q in range(12): a_ = q / 12 * 6.283; put(rng.choice(PEOPLE), cx + 11 * math.cos(a_), cy + 11 * math.sin(a_), 0.05, 1.0, a_ + math.pi); st('carousel'); continue
    if nm == 'Naumburg Bandshell':
        rx, ry, lx, ly, th = min_rect(pts); cylinder('concrete' if False else 'grey', cx, cy, Z0, 9.0, max(lx, ly)); box('concrete', cx, cy, Z0, 1.5, lx + 4, ly + 4, th); st('bandshell'); continue
    rects = fill_rects(pts, 10 if a > 400 else 4)
    for (rx, ry, lx, ly, th) in rects:
        building_rects.append((rx, ry, lx, ly, th, h))
        if h >= 45 and not inside and min(lx, ly) >= 14 and a > 1500 and 'black' != kind and h < 250:
            box(kind, rx, ry, Z0, 0.5 * h, lx, ly, th); box(kind, rx, ry, Z0 + 0.5 * h, 0.3 * h, lx * 0.8, ly * 0.8, th); box(kind, rx, ry, Z0 + 0.8 * h, 0.2 * h, lx * 0.6, ly * 0.6, th)
        else: box(kind, rx, ry, Z0, h, lx, ly, th)
        if h >= 25 and not inside and near_park(rx, ry) and min(lx, ly) >= 6 and WITH_WINDOWS: facades.append((rx, ry, Z0, h, lx, ly, th, 'glass' if kind == 'black' else 'punched', str(rx) + str(ry)))
        if h >= 20 and not inside and not LITE and lx * ly > 150 and rng.random() < 0.3:
            box('grey', *l2w(rx, ry, th, rng.uniform(-lx / 4, lx / 4), rng.uniform(-ly / 4, ly / 4)), Z0 + h, rng.uniform(2.5, 4), 3, 4, th)
            if rng.random() < 0.4: s = rng.uniform(0.8, 1.1); add(WATER_TOWER, *l2w(rx, ry, th, rng.uniform(-lx / 4, lx / 4), rng.uniform(-ly / 4, ly / 4)), Z0 + h, s, s, s, th)
st('buildings', bld_count)
rect_index = {}
for i, (rx, ry, lx, ly, th, h) in enumerate(building_rects):
    r = math.hypot(lx, ly) / 2
    for gx in range(int((rx - r) // 40), int((rx + r) // 40) + 1):
        for gy in range(int((ry - r) // 40), int((ry + r) // 40) + 1): rect_index.setdefault((gx, gy), []).append(i)
def building_at(x, y, margin=0.5):
    for i in rect_index.get((int(x // 40), int(y // 40)), ()):
        rx, ry, lx, ly, th, h = building_rects[i]; c, s = math.cos(th), math.sin(th); u = (x - rx) * c + (y - ry) * s; v = -(x - rx) * s + (y - ry) * c
        if abs(u) <= lx / 2 + margin and abs(v) <= ly / 2 + margin: return i
    return None
# window decals on facades facing the park
def window_png(style, cols, rows, path):
    from PIL import Image, ImageDraw
    cw, ch = 48, 48; img = Image.new('RGBA', (cols * cw, rows * ch), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for r in range(rows):
        shade = 0.82 + 0.18 * math.sin(r * 1.7)
        for c in range(cols):
            if style == 'punched':
                x0, y0 = c * cw + int(cw * 0.24), r * ch + int(ch * 0.18); x1, y1 = c * cw + int(cw * 0.76), r * ch + int(ch * 0.82)
                d.rectangle((x0, y0, x1, y1), fill=(int(28 * shade), int(36 * shade), int(50 * shade), 255)); d.rectangle((x0, y0, x1, y0 + 3), fill=(int(150 * shade), int(170 * shade), int(195 * shade), 255)); d.rectangle((x0, y0, x1, y1), outline=(220, 215, 205, 255))
            else:
                d.rectangle((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch), fill=(int(70 * shade), int(92 * shade), int(118 * shade), 255)); d.rectangle((c * cw, r * ch + int(ch * 0.74), (c + 1) * cw, (r + 1) * ch), fill=(int(38 * shade), int(44 * shade), int(52 * shade), 255))
                d.line((c * cw, r * ch, c * cw, (r + 1) * ch), fill=(190, 195, 200, 255), width=2); d.line((c * cw, r * ch, (c + 1) * cw, r * ch), fill=(190, 195, 200, 255), width=2)
    img.save(path)
COLS_B = [3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32]; ROWS_B = [6, 8, 10, 12, 15, 18, 22, 26, 30, 36, 42, 50, 60, 72, 85, 100]
def nearest(v, b): return min(b, key=lambda q: abs(q - v))
for (cx, cy, z0, h, lx, ly, th, style, key) in facades:
    fl = 3.6 if style == 'punched' else 4.0; wm = 2.6 if style == 'punched' else 1.6; rows_n = nearest(h / fl, ROWS_B)
    for (fx, fy, length, nyaw, u_edge, v_edge, nu, nv) in rect_faces(cx, cy, lx, ly, th):
        px, py = fx + 0.8 * math.cos(nyaw), fy + 0.8 * math.sin(nyaw); j = building_at(px, py, 0.0)
        if j is not None and building_rects[j][5] + 1 >= z0 + h * 0.5: continue
        if not in_park(fx + 60 * math.cos(nyaw), fy + 60 * math.sin(nyaw)) and not in_park(fx + 200 * math.cos(nyaw), fy + 200 * math.sin(nyaw)): continue   # only faces that look at the park
        cols_n = nearest(length / wm, COLS_B); k = f'{style}_{cols_n}x{rows_n}'
        name = 'decal_1791400000-' + hashlib.md5(k.encode()).hexdigest().upper() + '.png'; decal_files[name] = ('win', style, cols_n, rows_n)
        add(name, fx, fy, z0 + h / 2, 2.0, h / 4, length / 4, rot=decal_rot(nyaw), store=decal_rows); st('win_decals')
# ---- 7. trees: mapped trees, woods, the rest of the park, street trees -----------------
GENUS = {'ulmus': ELM, 'acer': MAPLE, 'quercus': OAK, 'pinus': PINES[0], 'platanus': ALDER, 'tilia': ALDER, 'prunus': MAPLE}
def tree_row(tags):
    g = (tags.get('genus') or tags.get('species') or '').lower().split(' ')[0]; return GENUS.get(g, rng.choice(TREES))
def tree(x, y, row=None, s=None):
    if occ_at(x, y) in (1, 2, 3): return False
    s = s or rng.uniform(0.85, 1.35); put(row or rng.choice(TREES), x, y, 0, s, rng.uniform(0, 6.28)); mark(x, y, 1); st('trees'); return True
for p in F['points']:
    if p['kind'] == 'tree' and in_park(p['x'], p['y']): tree(p['x'], p['y'], tree_row(p['tags']))
for p in F['polys']:
    if p['kind'] != 'wood' or not in_park(*centroid(p['pts'])): continue
    xs = [q[0] for q in p['pts']]; ys = [q[1] for q in p['pts']]; n = int(poly_area(p['pts']) / 55)
    for _ in range(n * 3):
        if n <= 0: break
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if point_in_poly(x, y, p['pts']) and tree(x, y, rng.choice(TREES + [OAK, BIG_ELM] + PINES), rng.uniform(0.9, 1.5)): n -= 1
xs = [q[0] for q in PARK]; ys = [q[1] for q in PARK]; want = int(poly_area(PARK) / 420)
for _ in range(want * 4):
    if want <= 0: break
    x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
    if not in_park(x, y) or occ_at(x, y) in (1, 2, 3, 4): continue
    if any(occ_at(x + dx, y + dy) == 1 for dx in (-4, 4) for dy in (-4, 4)) and rng.random() < 0.5: continue     # fewer trees right on the paths
    if tree(x, y): want -= 1
for p in F['points']:
    if p['kind'] == 'tree' and not in_park(p['x'], p['y']) and not LITE and building_at(p['x'], p['y'], 0.5) is None: put(rng.choice(TREES), p['x'], p['y'], 0, rng.uniform(0.8, 1.1), rng.uniform(0, 6.28)); st('street_trees')
# ---- 8. furniture and people along the paths --------------------------------------------
for (pts, w, row, inside, k, nm, bridge) in path_lines:
    if not inside: continue
    drive = row == ASPHALT and w >= 11; acc = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0); yaw = math.atan2(y1 - y0, x1 - x0); n = max(1, int(L / 3))
        for q in range(n):
            t = (q + 0.5) / n; x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t; acc += L / n
            side = 1 if int(acc / 25) % 2 == 0 else -1
            if acc % 25 < L / n and not bridge: put(LAMP_SHORT, *l2w(x, y, yaw, 0, side * (w / 2 + 0.6)), 0, 1.0, yaw + side * math.pi / 2); st('lamps')
            if acc % 11 < L / n and (drive or k == 'pedestrian') and not bridge: put(BENCH, *l2w(x, y, yaw, 0, -side * (w / 2 + 0.9)), 0, 1.0, yaw + (math.pi / 2 if side > 0 else -math.pi / 2)); st('benches')
            if acc % 60 < L / n and not bridge: put(TRASH, *l2w(x, y, yaw, 1.5, side * (w / 2 + 0.5)), 0, 1.0, yaw)
            if acc % (14 if drive else 28) < L / n:
                r = rng.random(); put(rng.choice(PEOPLE), *l2w(x, y, yaw, 0, rng.uniform(-w / 2 + 0.6, w / 2 - 0.6)), 0.05, 1.0, yaw + (0 if r < 0.5 else math.pi)); st('people')
            if drive and acc % 45 < L / n and not bridge: put(rng.choice(CARS), *l2w(x, y, yaw, 0, rng.choice([-3.0, 3.0])), 0.05, 1.0, yaw); st('cars')
# Sheep Meadow fence, playgrounds and entrances
for p in F['polys']:
    nm = p['tags'].get('name') or ''
    if nm == 'Sheep Meadow' or (p['kind'] == 'plaza' and 'Playground' in nm and in_park(*centroid(p['pts']))):
        for (x0, y0), (x1, y1) in zip(p['pts'], p['pts'][1:] + p['pts'][:1]):
            L = math.hypot(x1 - x0, y1 - y0); n = max(1, int(L // 4)); yaw = math.atan2(y1 - y0, x1 - x0)
            for q in range(n):
                t = (q + 0.5) / n; add(FENCE, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, Z0, 1, 1, 0.6, yaw); st('fences')
        if nm == 'Sheep Meadow':
            cx, cy = centroid(p['pts']); xs = [q[0] for q in p['pts']]; ys = [q[1] for q in p['pts']]
            for _ in range(140):
                x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
                if point_in_poly(x, y, p['pts']): put(rng.choice(PEOPLE_SIT + PEOPLE), x, y, 0.03, 1.0, rng.uniform(0, 6.28)); st('people')
for p in F['points']:
    if p['kind'] in ('ice_cream', 'fast_food', 'cafe') and (in_park(p['x'], p['y']) or abs(p['y'] - 440) < 30) and building_at(p['x'], p['y'], 1.0) is None: put(rng.choice([FOOD_CART, FOOD_STALL]), p['x'], p['y'], 0, 1.0, rng.uniform(0, 6.28)); st('carts')
# ---- 9. Imagine mosaic decal (ground) -----------------------------------------------------
def imagine_png(path):
    from PIL import Image, ImageDraw, ImageFont
    S = 512; img = Image.new('RGBA', (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(img); r0 = S / 2 - 6
    d.ellipse((6, 6, S - 6, S - 6), fill=(236, 232, 222, 255), outline=(70, 70, 70, 255), width=8)
    for q in range(1, 9):
        rr = r0 * q / 9; d.ellipse((S / 2 - rr, S / 2 - rr, S / 2 + rr, S / 2 + rr), outline=(60, 60, 60, 255), width=3)
    for q in range(36): a = q / 36 * 6.283; d.line((S / 2 + r0 * 0.25 * math.cos(a), S / 2 + r0 * 0.25 * math.sin(a), S / 2 + r0 * math.cos(a), S / 2 + r0 * math.sin(a)), fill=(60, 60, 60, 255), width=2)
    try: font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Georgia.ttf', 74)
    except Exception: font = ImageFont.load_default()
    bb = d.textbbox((0, 0), 'IMAGINE', font=font); d.rectangle((S / 2 - (bb[2] - bb[0]) / 2 - 10, S / 2 - 44, S / 2 + (bb[2] - bb[0]) / 2 + 10, S / 2 + 44), fill=(236, 232, 222, 255))
    d.text((S / 2 - (bb[2] - bb[0]) / 2, S / 2 - (bb[3] - bb[1]) / 2 - 8), 'IMAGINE', fill=(40, 40, 40, 255), font=font); img.save(path)
if WITH_WINDOWS:
    name = 'decal_1791400002-' + hashlib.md5(b'imagine').hexdigest().upper() + '.png'; decal_files[name] = ('imagine',)
    add(name, IMX, IMY, Z0 + 0.5, 1.0, 0.65, 0.65, rot=quat_from_axes((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)), store=decal_rows)
# ---- output ------------------------------------------------------------------------------
north = FR.xy(FRAME['lat0'] + 0.001, FRAME['lon0']); north_yaw = math.degrees(math.atan2(north[1], north[0]))
cam = (0.0, 420.0, 95.0); cam_yaw = -90.0; cam_pitch = math.degrees(math.atan2(0 - cam[2], 420))
def thumbnail(path):
    from PIL import Image, ImageDraw
    W = 1024; img = Image.new('RGB', (W, W), (235, 232, 224)); d = ImageDraw.Draw(img); sc = W / 2000
    def px(x, y): return (W / 2 - x * sc, W / 2 + (y + 600) * sc)
    col = dict(water=(120, 170, 230), grass=(150, 200, 130), wood=(80, 140, 80), building=(110, 110, 120), plaza=(200, 195, 185), rock=(160, 150, 140), park=(170, 205, 150))
    for k in ('park', 'grass', 'wood', 'rock', 'plaza', 'water', 'building'):
        for p in F['polys']:
            if p['kind'] == k: d.polygon([px(x, y) for x, y in p['pts']], fill=col[k])
    for l in F['lines']:
        if l['kind'] in ('footway', 'pedestrian', 'path', 'service') and in_park(*l['pts'][0]): d.line([px(x, y) for x, y in l['pts']], fill=(245, 245, 240), width=2)
    d.text((24, W - 40), DISPLAY, fill=(20, 20, 20)); img.save(path, quality=88)
rows_all = dict(instances); rows_all.update(decal_rows if WITH_WINDOWS else {})
map_json = {'S_AssetsTransform': [dict(Rname=r, Transform=t, UniqueGroupTag=['None'] * len(t)) for r, t in rows_all.items()], 'BaseMapRow': 'BaseBoard', 'WeatherIndex': 0,
            'Race': dict(CheckPoints=[], StartTransform=tf(0, 0, 0, dict(X=0, Y=0, Z=0, W=1)), Laps=1, BestTime=-1, Spoints=[]),
            'CamLoc': tf(cam[0], cam[1], cam[2], quat_pitch_yaw(cam_pitch, cam_yaw)), 'CustomWeather': dict(timeOfDay=16.0, northyaw=round(north_yaw, 2), Cloud=0.2)}
info = {'BaseMapRow': 'BaseBoard', 'Name': DISPLAY, 'CreatorSteamID': STEAM_ID, 'CreationTimeUnix': int(time.time()), 'Track': False}
out = os.path.join(ROOT, 'maps', NAME)
if os.path.isdir(out): shutil.rmtree(out)
os.makedirs(out); json.dump(map_json, open(os.path.join(out, NAME + '.json'), 'w')); open(os.path.join(out, NAME + '.info'), 'w').write(json.dumps(info))
if WITH_WINDOWS:
    ddir = os.path.join(out, 'Decals'); os.makedirs(ddir)
    for name, spec in decal_files.items():
        if spec[0] == 'win': window_png(spec[1], spec[2], spec[3], os.path.join(ddir, name))
        else: imagine_png(os.path.join(ddir, name))
    for lib in ('UserDecals', 'MapDecals'):
        ld = os.path.join(os.path.dirname(GAME_USER_MAPS), lib); os.makedirs(ld, exist_ok=True)
        for name in decal_files: shutil.copy(os.path.join(ddir, name), os.path.join(ld, name))
thumbnail(os.path.join(out, 'Thumbnail.jpg'))
dst = os.path.join(GAME_USER_MAPS, NAME)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(out, dst)
n = sum(len(v) for v in rows_all.values())
print(f'{NAME}: {n} instances, {len(rows_all)} rows, north yaw {north_yaw:.1f} -> {dst}'); print(stats)
print('top rows:', {r: len(v) for r, v in sorted(instances.items(), key=lambda kv: -len(kv[1]))[:14]})
