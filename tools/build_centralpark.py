#!/usr/bin/env python3
"""Central Park for Uncrashed, built from OpenStreetMap on the grassy BaseLandscape02 level.

Why this base level: it is the only one with a real grass ground (the Empty board is a numbered grid and Bp_Grass
renders grey on macOS), it is flat to within 2 m, and its 2.42 km board matches the game's 2.2 km flight box. The
frame (data/centralpark_frame.json) puts the world origin on the Bethesda fountain plaza, 12 m out of the arcade's
north mouth, so the spawn (the level's PlayerStart at the origin, facing -Y) stands on open flagstone looking at the
Angel fountain and the Lake with nothing within 5 m of it, and
the board covers the park from Central Park South to the Great Lawn plus Midtown to about 56th Street.

Data: data/centralpark_features.json from tools/osm.py (polygons: water with islands, lawns, woods, rock, plazas,
buildings with heights; lines: paths, drives, transverses, bridges, fences, walls, streams, steps; points: mapped
trees, benches, lamps, statues, vendors). Reference imagery: data/centralpark_naip.png.

Asset-first rule (tools/mapkit.py): real meshes wherever one exists (stone arches and parapets for bridges, Stair_A
for stairs, concrete fence panels for retaining walls, park fences, benches oriented to their path, kiosks, textured
building and house meshes), cubes and concrete only for what the catalogue lacks. Every object stands on the terrain
at its own position (tools/landscape.py sampler). Surfaces sit on per-material height bands so nothing z-fights.

Layers: 1 water and surfaces from polygons, 2 paths/drives/transverse trenches/bridges, 3 the Mall and Bethesda,
4 hand-placed landmarks, 5 buildings (park structures and the city) with window decals facing the park, 6 trees,
7 furniture, vendors and people, 8 Columbus Circle and Grand Army Plaza, 9 the Imagine mosaic decal, then output.
Occupancy grid (4 m): 0 free, 1 path, 2 water, 3 hard, 4 lawn, 5 wood.
usage: build_centralpark.py [--no-windows] [--lite]
"""

import hashlib
import json
import math
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geom import centroid, decompose, l2w, min_rect, point_in_poly, poly_area, rect_faces
from landscape import Landscape
from mapkit import GROUND, LAYER, MapKit, rest, size
from osm import Frame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
STEAM_ID = os.environ.get(
    'UNCRASHED_STEAM_ID', '76561197969360950'
)  # your Steam ID64: maps load from MapEditor/User under it
GAME_USER_MAPS = os.path.expanduser(f'~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User')
NAME, DISPLAY = 'CentralPark', 'New York City - Central Park'
BASE = 'BaseLandscape02'
WITH_WINDOWS = '--no-windows' not in sys.argv
LITE = '--lite' in sys.argv
rng = random.Random(7)
FRAME = json.load(open(os.path.join(DATA, 'centralpark_frame.json')))
FR = Frame(FRAME['lat0'], FRAME['lon0'], FRAME['axis_deg'], True)
F = json.load(open(os.path.join(DATA, 'centralpark_features.json')))
for _p in F['polys']:
    _p['pts'] = [tuple(q) for q in _p['pts']]
    _p['holes'] = [[tuple(q) for q in h] for h in _p['holes']]
for _l in F['lines']:
    _l['pts'] = [tuple(q) for q in _l['pts']]
CAT = json.load(open(os.path.join(DATA, 'catalog.json')))
LAND = Landscape(os.path.join(DATA, 'extracted/Uncrashed/Content/MapEditor/BaseLevel/L_' + BASE))
BOARD = 1205.0  # the landscape's far edges; the near edges (+806 m) are enforced by the sampler in add()

# ---- rows ----------------------------------------------------------------------------------------------------
CUBE = dict(
    default='NewRow_13',
    yellow='NewRow_46',
    blue='NewRow_79',
    red='NewRow_84',
    green='NewRow_268',
    grey='NewRow_256',
    violet='NewRow_378',
    black='NewRow_109',
)
CYL = dict(default='NewRow_14', grey='NewRow_261', black='NewRow_113', yellow='NewRow_64', red='NewRow_89')
CONCRETE, BRICK, PYRAMID = 'NewRow_303', 'NewRow_318', 'NewRow_143'
WATER = 'NewRow_183'
ELM, MAPLE, ALDER, OAK, BIG_ELM = 'NewRow_168', 'NewRow_269', 'NewRow_34', 'NewRow_78', 'NewRow_169'
PINES = ['NewRow_279', 'NewRow_280', 'NewRow_281']
TREES = [ELM, MAPLE, ALDER]
BUSHES = ['NewRow_164', 'NewRow_226']
ROCKS = ['NewRow_71', 'NewRow_162']
CLIFF = 'NewRow_175'
LAMP_TALL, LAMP_SHORT, TRASH, STATUE = 'NewRow_3', 'NewRow_20', 'NewRow_323', 'NewRow_213'
PEOPLE = ['NewRow_252', 'NewRow_255', 'NewRow_801', 'NewRow_802']
PEOPLE_SIT = ['NewRow_254', 'NewRow_800']
CARS = ['NewRow_103', 'NewRow_257', 'NewRow_93', 'NewRow_775']
BOAT, FOOD_CART, FOOD_STALL, TABLE, CHAIR, WATER_TOWER = (
    'NewRow_329',
    'NewRow_246',
    'NewRow_247',
    'NewRow_353',
    'NewRow_352',
    'NewRow_251',
)
PARK_FENCE = 'NewRow_777'

instances = {}
decal_rows = {}
decal_files = {}
stats = {}


def st(k, n=1):
    """Count an event in the build statistics."""
    stats[k] = stats.get(k, 0) + n


# ---- terrain --------------------------------------------------------------------------------------------------
def gz(x, y):
    """Ground-top height (m) at local (x, y); None off the landscape."""
    h = LAND.height_cm(x * 100, y * 100)
    return None if h is None else h / 100.0 + 0.03


G0 = gz(0, 0)


def ground(x, y):
    """Ground height for placement; off-landscape points fall back to the origin height (callers check BOARD)."""
    h = gz(x, y)
    return G0 if h is None else h


print(f'landscape {BASE}: ground at the origin {G0:.2f} m')


# ---- transforms and primitives -------------------------------------------------------------------------------
def quat_yaw(yaw):
    """Quaternion for a yaw (radians) about +Z."""
    return dict(X=0.0, Y=0.0, Z=math.sin(yaw / 2), W=math.cos(yaw / 2))


def quat_pitch_yaw(pitch_deg, yaw_deg):
    """Quaternion for pitch then yaw in degrees (roll 0), as UE's FRotator::Quaternion."""
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2
    SP, CP, SY, CY = math.sin(P), math.cos(P), math.sin(Y), math.cos(Y)
    return dict(X=SP * SY, Y=-SP * CY, Z=CP * SY, W=CP * CY)


def quat_from_axes(X, Y, Z):
    """Quaternion whose rotation maps the local axes onto the given orthonormal world vectors."""
    m = [[X[0], Y[0], Z[0]], [X[1], Y[1], Z[1]], [X[2], Y[2], Z[2]]]
    t = m[0][0] + m[1][1] + m[2][2]
    if t > 0:
        s = math.sqrt(t + 1) * 2
        w, x, y, z = s / 4, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1 + m[0][0] - m[1][1] - m[2][2]) * 2
        w, x, y, z = (m[2][1] - m[1][2]) / s, s / 4, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1 + m[1][1] - m[0][0] - m[2][2]) * 2
        w, x, y, z = (m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, s / 4, (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1 + m[2][2] - m[0][0] - m[1][1]) * 2
        w, x, y, z = (m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, s / 4
    return dict(X=x, Y=y, Z=z, W=w)


def decal_rot(normal_yaw):
    """Wall-decal basis: X into the surface, Y world-down, Z = X x Y (verified against editor-placed decals)."""
    c, s = math.cos(normal_yaw), math.sin(normal_yaw)
    return quat_from_axes((-c, -s, 0.0), (0.0, 0.0, -1.0), (s, -c, 0.0))


def tf(x, y, z, rot, s=(1, 1, 1)):
    """Map-JSON transform: metres -> Unreal centimetres."""
    return dict(
        Rotation=rot,
        Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)),
        Scale3D=dict(X=round(s[0], 4), Y=round(s[1], 4), Z=round(s[2], 4)),
    )


def add(row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0, rot=None, store=None):
    """Place a row at pivot (x, y, z) m; anything off the landscape is dropped silently. The grassy landscape is
    not centred on the origin: it spans -1209..+806 m on both axes (measured from its heightmap), so the check is
    the sampler itself, not a symmetric board size."""
    if abs(x) > BOARD or abs(y) > BOARD or gz(x, y) is None:
        st('dropped_off_landscape')
        return
    (store if store is not None else instances).setdefault(row, []).append(
        tf(x, y, z, rot if rot else quat_yaw(yaw), (sx, sy, sz))
    )


def box(kind, cx, cy, z0, h, lx, ly, yaw=0.0):
    """Axis box from z0 up by h: 'concrete' (SM_ConcreteFloor01, pivot at the TOP), 'brick' (base pivot), or a cube colour."""
    lx, ly, h = max(lx, 0.1), max(ly, 0.1), max(h, 0.01)
    if kind == 'concrete':
        sz = h / 0.30
        add(CONCRETE, cx, cy, z0 + 0.29 * sz, lx / 4, ly / 4, sz, yaw)
    elif kind == 'brick':
        add(BRICK, cx, cy, z0, lx / 0.3, ly / 4, h / 4, yaw)
    else:
        add(CUBE[kind], cx, cy, z0 + h / 2, lx, ly, h, yaw)


def cylinder(kind, cx, cy, z0, h, d):
    """Cylinder of diameter d from z0 up by h (centre pivot)."""
    add(CYL[kind], cx, cy, z0 + h / 2, d, d, h)


def plane(row, x, y, z_top, lx, ly, yaw=0.0):
    """A 4 x 4 x 0.1 m ground plane scaled to lx x ly with its top at z_top."""
    add(row, x, y, z_top - 0.05, max(lx, 0.5) / 4, max(ly, 0.5) / 4, 1.0, yaw)
    st('planes')


def put(row, x, y, dz=0.0, s=1.0, yaw=0.0):
    """Place a row on the terrain at its own position, lifted by dz and the catalogue rest correction."""
    h = gz(x, y)
    if h is None or math.hypot(x, y) < 5.0:  # the spawn (origin) must stay clear: no trees, people or props on it
        return
    add(row, x, y, h + dz + rest(row) * s, s, s, s, yaw)


def ll(lat, lon):
    """WGS84 -> local metres."""
    return FR.xy(lat, lon)


kit = MapKit(add, box, plane, ground_z=ground, rng=rng, stats=stats)

# ---- the park polygon and an occupancy grid ---------------------------------------------------------------
PARK = max(
    (p for p in F['polys'] if p['kind'] == 'park' and p['tags'].get('name') == 'Central Park'),
    key=lambda p: poly_area(p['pts']),
)['pts']
pcx, pcy, plx, ply, pth = min_rect(PARK)
CELL = 4.0
GX0, GY0 = -1300, -1500
GNX, GNY = int(2600 / CELL), int(3000 / CELL)
occ = bytearray(GNX * GNY)


def cell(x, y):
    """Grid cell of a point."""
    return (int((x - GX0) // CELL), int((y - GY0) // CELL))


def mark(x, y, v):
    """Set the occupancy of the cell under (x, y)."""
    i, j = cell(x, y)
    if 0 <= i < GNX and 0 <= j < GNY:
        occ[j * GNX + i] = v


def occ_at(x, y):
    """Occupancy of the cell under (x, y); off-grid counts as hard."""
    i, j = cell(x, y)
    return occ[j * GNX + i] if 0 <= i < GNX and 0 <= j < GNY else 3


def mark_poly(pts, v, holes=()):
    """Mark every cell inside a polygon (minus holes)."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    for j in range(int((min(ys) - GY0) // CELL), int((max(ys) - GY0) // CELL) + 1):
        for i in range(int((min(xs) - GX0) // CELL), int((max(xs) - GX0) // CELL) + 1):
            x, y = GX0 + (i + 0.5) * CELL, GY0 + (j + 0.5) * CELL
            if point_in_poly(x, y, pts) and not any(point_in_poly(x, y, h) for h in holes):
                mark(x, y, v)


def in_park(x, y):
    """True inside the Central Park polygon."""
    return point_in_poly(x, y, PARK)


def mark_line(pts, w, v):
    """Mark the cells along a polyline of width w."""
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / 2))
        for k in range(n + 1):
            t = k / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for dx in (-w / 2, 0, w / 2):
                for dy in (-w / 2, 0, w / 2):
                    mark(x + dx, y + dy, v)


def along_line(pts, step, start=0.0):
    """Yield (x, y, yaw, distance) every `step` metres along a polyline."""
    acc, nxt = 0.0, start
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        yaw = math.atan2(y1 - y0, x1 - x0)
        while nxt <= acc + L:
            t = (nxt - acc) / L
            yield x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, yaw, nxt
            nxt += step
        acc += L


def fill_rects(pts, max_rects=12):
    """Rectangles covering a polygon (one for tiny ones)."""
    return decompose(pts, max_rects) if poly_area(pts) > 30 else [min_rect(pts)]


def parse_width(v):
    """OSM width: '3.5', '3.5 m', '28'0"', '12 ft' -> metres (0 if unparseable)."""
    if not v:
        return 0.0
    v = str(v).strip().lower()
    try:
        if "'" in v:
            ft, _, inch = v.partition("'")
            return (float(ft) + float(inch.replace('"', '') or 0) / 12) * 0.3048
        if 'ft' in v:
            return float(v.replace('ft', '').strip()) * 0.3048
        return float(v.replace('m', '').strip())
    except ValueError:
        return 0.0


def water_level(pts):
    """One level per water body: the highest ground under it plus 5 cm, so the sheet never sinks below the grass."""
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    hs = [
        gz(x, y)
        for x in range(int(min(xs)), int(max(xs)) + 1, 12)
        for y in range(int(min(ys)), int(max(ys)) + 1, 12)
        if point_in_poly(x, y, pts)
    ]
    hs = [h for h in hs if h is not None]
    return (max(hs) if hs else G0) + 0.05


# ---- 1. water and surfaces from OSM polygons -------------------------------------------------------------
water_tiles = 0
for p in F['polys']:
    k, pts, tags = p['kind'], p['pts'], p['tags']
    cx, cy = centroid(pts)
    a = poly_area(pts)
    if abs(cx) > BOARD or abs(cy) > BOARD:
        continue
    inside = in_park(cx, cy)
    if k == 'water' and a > 40:
        tile = 4.0 if (inside and a < 3e4) else (8.0 if a < 20e4 else 16.0)
        lvl = water_level(pts)
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        for j in range(int(min(ys) // tile), int(max(ys) // tile) + 1):
            for i in range(int(min(xs) // tile), int(max(xs) // tile) + 1):
                x, y = (i + 0.5) * tile, (j + 0.5) * tile
                if point_in_poly(x, y, pts) and not any(point_in_poly(x, y, h) for h in p['holes']):
                    add(WATER, x, y, lvl, tile / 4, tile / 4, 1.2)
                    water_tiles += 1
        mark_poly(pts, 2, p['holes'])
        if inside:  # a rocky bank hides the water sheet's edge where the ground dips below it
            for x, y, yaw, dist in along_line(pts + pts[:1], 7.0):
                put(rng.choice(ROCKS), *l2w(x, y, yaw, 0, 1.2), 0.0, rng.uniform(0.7, 1.3), rng.uniform(0, 6.28))
                st('bank_rocks')
        if tags.get('name') == 'The Lake':
            n = 0
            for _ in range(800):
                if n >= 24:
                    break
                x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
                if (
                    point_in_poly(x, y, pts)
                    and not any(point_in_poly(x, y, h) for h in p['holes'])
                    and all(math.hypot(x - q[0], y - q[1]) > 10 for q in pts[::2])
                ):
                    add(BOAT, x, y, lvl + rest(BOAT), 1, 1, 1, rng.uniform(0, 6.28))
                    n += 1
                    st('boats')
        if tags.get('name') == 'Conservatory Water':
            for _ in range(10):
                x, y = rng.uniform(cx - 25, cx + 25), rng.uniform(cy - 25, cy + 25)
                if point_in_poly(x, y, pts):
                    add(BOAT, x, y, lvl, 0.3, 0.3, 0.3, rng.uniform(0, 6.28))
    elif k in ('plaza', 'parking', 'rink') and inside and a > 20:
        mat = 'asphalt' if k == 'parking' else ('pavement2' if k == 'rink' else 'flagstone')
        for q, (rx, ry, lx, ly, th) in enumerate(fill_rects(pts, 20)):
            kit.surface(mat, rx, ry, lx, ly, th, q)
        mark_poly(pts, 3)
        if k == 'rink':
            kit.wall(pts + pts[:1], 'parapet', 1.0)
            for _ in range(30):
                x, y = rng.uniform(cx - 30, cx + 30), rng.uniform(cy - 30, cy + 30)
                if point_in_poly(x, y, pts):
                    put(rng.choice(PEOPLE), x, y, LAYER['pavement2'], 1.0, rng.uniform(0, 6.28))
                    st('skaters')
    elif k == 'grass' and inside:
        mark_poly(pts, 4)
        if tags.get('sport') == 'tennis':
            rx, ry, lx, ly, th = min_rect(pts)
            kit.surface('pavement2', rx, ry, lx, ly, th)
            kit.wall(pts + pts[:1], 'tall_fence')
            short = min(lx, ly)
            tth = th if lx >= ly else th + math.pi / 2
            zc = ground(rx, ry) + LAYER['pavement2']
            for q in range(max(1, int(short // 18))):
                v = -short / 2 + 9 + q * 18
                for dv in (-5.5, 0.0, 5.5):
                    box('default', *l2w(rx, ry, tth, 0, v + dv), zc, 0.02, 23.8, 0.12, tth)
                for du in (-11.9, 11.9):
                    box('default', *l2w(rx, ry, tth, du, v), zc, 0.02, 0.12, 11.0, tth)
                nx_, ny_ = l2w(rx, ry, tth, 0, v)
                add(PARK_FENCE, nx_, ny_, zc, 1, 2.9, 0.4, tth + math.pi / 2)
            mark_poly(pts, 3)
            st('tennis_courts')
        elif 'Ball Field' in (tags.get('name') or '') or tags.get('sport') == 'baseball':
            kit.surface('dirt', cx, cy, 26, 26, pth + math.pi / 4)
            kit.wall([l2w(cx, cy, pth + math.pi / 4, -8, -13), l2w(cx, cy, pth + math.pi / 4, 8, -13)], 'tall_fence')
            st('ballfields')
    elif k == 'wood' and inside:
        mark_poly(pts, 5)
    elif k == 'rock' and inside and a > 40:
        mark_poly(pts, 3)
        for rx, ry, lx, ly, th in fill_rects(pts, 6):
            h = min(2.5, 0.5 + math.sqrt(lx * ly) / 12)
            box('grey', rx, ry, ground(rx, ry) - 0.3, h + 0.3, lx * 0.9, ly * 0.9, th)
        for _ in range(max(2, int(a // 150))):
            x, y = rng.uniform(cx - 15, cx + 15), rng.uniform(cy - 15, cy + 15)
            if point_in_poly(x, y, pts):
                s = rng.uniform(1.2, 2.6)
                put(rng.choice(ROCKS + [CLIFF]), x, y, 0.3, s, rng.uniform(0, 6.28))
                st('rocks')
    elif k == 'fountain' and inside and a > 20:
        g = ground(cx, cy)
        cylinder('grey', cx, cy, g - 0.2, 0.9, 2 * math.sqrt(a / math.pi))
        cylinder('grey', cx, cy, g, 2.5, 1.6)
        for j in range(-3, 4):
            for i in range(-3, 4):
                if point_in_poly(cx + i * 4, cy + j * 4, pts):
                    add(WATER, cx + i * 4, cy + j * 4, g + 0.6, 1, 1, 1)
        mark_poly(pts, 3)
        st('fountains')
print('water tiles', water_tiles)

# ---- 2. paths, drives, transverse trenches, arches ---------------------------------------------------------
PATH_W = dict(
    footway=3.6,
    path=3.0,
    pedestrian=7.0,
    bridleway=4.0,
    cycleway=4.0,
    steps=3.0,
    service=8.0,
    residential=11.0,
    tertiary=12.0,
    secondary=14.0,
    primary=18.0,
    unclassified=10.0,
    living_street=8.0,
)


def is_drive(l):
    """Park drives: named '... Drive' or service roads inside the park."""
    return (l['tags'].get('name') or '').endswith('Drive') or (l['kind'] == 'service' and in_park(*l['pts'][0]))


def is_transverse(l):
    """The sunken crosstown transverse roads."""
    return 'Transverse' in (l['tags'].get('name') or '') and l['kind'] in ('tertiary', 'secondary', 'residential')


path_lines = []  # (pts, width, material, inside, kind, name, bridge)
for l in F['lines']:
    k, pts = l['kind'], l['pts']
    if k not in PATH_W or len(pts) < 2:
        continue
    mid = pts[len(pts) // 2]
    if abs(mid[0]) > BOARD + 100 or abs(mid[1]) > BOARD + 100:
        continue
    inside = in_park(*mid)
    if not inside and k in ('footway', 'path', 'steps', 'pedestrian', 'bridleway', 'cycleway'):
        continue
    if l['tags'].get('tunnel') == 'yes' and not inside:
        continue
    w = parse_width(l['tags'].get('width')) or PATH_W[k]
    if is_drive(l):
        w, mat = max(w, 12.0), 'asphalt'
    elif is_transverse(l):
        w, mat = 12.0, 'asphalt'
    elif k in ('footway', 'path', 'steps', 'pedestrian'):
        mat = 'pavement' if k != 'pedestrian' else 'flagstone'
    elif k == 'bridleway':
        mat = 'dirt'
    else:
        mat = 'asphalt'
    bridge = l['tags'].get('bridge') == 'yes'
    if not bridge:  # bridges are built as arches below, with their own deck
        kit.ribbon(pts, w, mat)
    mark_line(pts, w, 1)
    path_lines.append((pts, w, mat, inside, k, l['tags'].get('name') or '', bridge))
    if not inside and k in ('residential', 'tertiary', 'secondary', 'primary') and not LITE:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            yaw = math.atan2(y1 - y0, x1 - x0)
            if L < 6:
                continue
            for side in (-1, 1):
                sx_, sy_ = l2w((x0 + x1) / 2, (y0 + y1) / 2, yaw, 0, side * (w / 2 + 2.2))
                kit.surface('pavement2', sx_, sy_, L + 0.3, 4.0, yaw)
            if L > 20 and w >= 11:
                box(
                    'yellow',
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    ground((x0 + x1) / 2, (y0 + y1) / 2) + LAYER['asphalt'] + 0.01,
                    0.01,
                    L - 6,
                    0.3,
                    yaw,
                )
st('path_lines', len(path_lines))

# transverse roads: walled trenches (the terrain cannot be dug), so path crossings over them become real overpasses
TRANSVERSE = [pl for pl in path_lines if 'Transverse' in pl[5] and pl[2] == 'asphalt' and pl[1] >= 11]


def near_transverse(x, y, d=10.0):
    """True within d metres of a transverse road centreline."""
    for pts, w, mat, inside, k, nm, bridge in TRANSVERSE:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            d2 = dx * dx + dy * dy
            if d2 < 1e-6:
                continue
            t = max(0, min(1, ((x - x0) * dx + (y - y0) * dy) / d2))
            if math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)) < d:
                return True
    return False


for pts, w, mat, inside, k, nm, bridge in TRANSVERSE:
    for sgn in (-1, 1):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            yaw = math.atan2(y1 - y0, x1 - x0)
            if in_park((x0 + x1) / 2, (y0 + y1) / 2):
                kit.wall(
                    [l2w(x0, y0, yaw, 0, sgn * (w / 2 + 0.8)), l2w(x1, y1, yaw, 0, sgn * (w / 2 + 0.8))],
                    'retaining',
                    3.6,
                )
                st('transverse_walls')
    for x, y, yaw, dist in along_line(pts, 45):
        if in_park(x, y):
            put(
                rng.choice(CARS),
                *l2w(x, y, yaw, 0, rng.choice([-3.0, 3.0])),
                LAYER['asphalt'],
                1.0,
                yaw + (0 if rng.random() < 0.5 else math.pi),
            )
            st('cars')

# arches: every bridge with a mapped outline, then every bridge-tagged path segment without one
arch_centres = []
for l in F['lines']:
    if l['kind'] != 'bridge' or len(l['pts']) < 4 or not in_park(*l['pts'][0]):
        continue
    cx, cy, lx, ly, th = min_rect(l['pts'])
    L, W = (lx, ly) if lx >= ly else (ly, lx)
    th = th if lx >= ly else th + math.pi / 2
    nm = l['tags'].get('name') or ''
    kit.bridge(
        cx, cy, L, W, th, 4.8 if near_transverse(cx, cy) else 3.4, deck='wood' if 'Bow' in nm else 'flagstone', name=nm
    )
    arch_centres.append((cx, cy))
for l in F['lines']:
    if l['tags'].get('bridge') != 'yes' or l['kind'] not in (
        'footway',
        'path',
        'bridleway',
        'cycleway',
        'pedestrian',
        'steps',
    ):
        continue
    pts = l['pts']
    if len(pts) < 2 or not in_park(*pts[len(pts) // 2]):
        continue
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    L = math.hypot(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if L < 6 or any(math.hypot(cx - ox, cy - oy) < 14 for (ox, oy) in arch_centres):
        continue
    W = (parse_width(l['tags'].get('width')) or PATH_W.get(l['kind'], 3.6)) + 1.0
    kit.bridge(
        cx,
        cy,
        L + 2.0,
        W,
        math.atan2(y1 - y0, x1 - x0),
        4.8 if near_transverse(cx, cy) else 3.2,
        name=l['tags'].get('name') or '',
    )
    arch_centres.append((cx, cy))
# streams (the Gill, the Loch): a ribbon of water tiles with rocks along the banks
for l in F['lines']:
    if l['kind'] not in ('stream', 'river', 'canal', 'drain', 'ditch') or not in_park(*l['pts'][0]):
        continue
    for x, y, yaw, dist in along_line(l['pts'], 3.0):
        add(WATER, x, y, ground(x, y) + 0.02, 1.0, 1.0, 1.0, yaw)
        mark(x, y, 2)
        if int(dist) % 9 == 0:
            for sgn in (-1, 1):
                put(rng.choice(ROCKS), *l2w(x, y, yaw, 0, sgn * 2.6), 0.0, rng.uniform(0.8, 1.6), rng.uniform(0, 6.28))
        st('stream_tiles')
# mapped fences, walls, retaining walls and hedges
for l in F['lines']:
    k = l['kind']
    if k not in ('fence', 'wall', 'retaining_wall', 'hedge', 'city_wall') or not in_park(*l['pts'][0]):
        continue
    if k == 'fence':
        kit.wall(l['pts'], 'fence', 1.5)
    elif k == 'hedge':
        for x, y, yaw, dist in along_line(l['pts'], 2.0):
            put(rng.choice(BUSHES), x, y, 0, rng.uniform(0.9, 1.2), rng.uniform(0, 6.28))
        st('hedges')
    elif k == 'retaining_wall':
        kit.wall(l['pts'], 'retaining', 1.8)
    else:
        kit.wall(l['pts'], 'brick', 2.0)
# steps: stone parapets both sides so a flight of steps reads as one on the near-flat terrain
for l in F['lines']:
    if l['kind'] != 'steps' or not in_park(*l['pts'][0]):
        continue
    w = parse_width(l['tags'].get('width')) or 3.0
    for sgn in (-1, 1):
        side = []
        for (x0, y0), (x1, y1) in zip(l['pts'], l['pts'][1:]):
            yaw = math.atan2(y1 - y0, x1 - x0)
            side += [l2w(x0, y0, yaw, 0, sgn * (w / 2 + 0.2)), l2w(x1, y1, yaw, 0, sgn * (w / 2 + 0.2))]
        kit.wall(side, 'parapet')
    st('step_rails')

# ---- 3. the Mall, Bethesda Terrace and the Angel fountain ---------------------------------------------------
_arc = next(l for l in F['lines'] if l['tags'].get('name') == 'Bethesda Arcade')
_south = max(_arc['pts'][0], _arc['pts'][-1], key=lambda q: q[1])  # the Mall meets the arcade at its south mouth
MALL_X, MALL_Y1, MALL_Y0 = (
    _south[0],
    _south[1] + 9.0,
    _south[1] + 370.0,
)  # the Mall runs from the Literary Walk (+Y) up to the Terrace
kit.ribbon([(MALL_X, MALL_Y0), (MALL_X, MALL_Y1)], 12.0, 'flagstone')
mark_line([(MALL_X, MALL_Y0), (MALL_X, MALL_Y1)], 12, 1)
for y in range(int(MALL_Y1), int(MALL_Y0), 12):
    for x in (-8.5, 8.5, -16.5, 16.5):
        s = rng.uniform(1.15, 1.45)
        put(
            BIG_ELM if abs(x) < 10 else ELM,
            x + rng.uniform(-0.4, 0.4),
            y + rng.uniform(-0.5, 0.5),
            0,
            s,
            rng.uniform(0, 6.28),
        )
        st('mall_elms')
    kit.bench(MALL_X - 6.6, y + 6, -math.pi / 2, -1)  # the walk runs toward -Y; a bench on each side faces it
    kit.bench(MALL_X + 6.6, y + 6, -math.pi / 2, 1)
    if (y // 12) % 3 == 0:
        for x in (-7.2, 7.2):
            put(LAMP_SHORT, MALL_X + x, y + 1, 0, 1.0, 0)
            st('lamps')
for nm, x, y in [
    (p['tags']['name'], p['x'], p['y'])
    for p in F['points']
    if p['kind'] in ('artwork', 'memorial') and p['tags'].get('name') and in_park(p['x'], p['y'])
]:
    box('grey', x, y, ground(x, y) - 0.2, 1.8, 1.4, 1.4)
    put(STATUE, x, y, 1.6, 1.3, rng.uniform(0, 6.28))
    st('statues')
# Terrace Drive crosses the arcade on a 4 m embankment; real stairs drop to the fountain plaza on the Lake side
ARC = next(l for l in F['lines'] if l['tags'].get('name') == 'Bethesda Arcade')
(ax0, ay0), (ax1, ay1) = ARC['pts'][0], ARC['pts'][-1]
acx, acy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
ayaw = math.atan2(ay1 - ay0, ax1 - ax0)  # along the arcade; north (-Y) is the +u direction when ay1 < ay0
un = 1 if ay1 < ay0 else -1
gA = ground(acx, acy)
box('concrete', acx, acy, gA + 4.0, 0.6, 16, 70, ayaw)  # Terrace Drive deck: 16 m thick along the arcade, 70 m across
kit.surface('asphalt', acx, acy, 12, 70, ayaw, z_base=gA + 4.6)
for sgn in (-1, 1):
    kit.wall(
        [l2w(acx, acy, ayaw, -8, sgn * 7.5), l2w(acx, acy, ayaw, 8, sgn * 7.5)], 'retaining', 4.0
    )  # the arcade: a 15 m passage under the drive
    for side in (-1, 1):  # the embankment faces either side of the passage mouth
        kit.wall([l2w(acx, acy, ayaw, sgn * 8, side * 7.5), l2w(acx, acy, ayaw, sgn * 8, side * 35)], 'retaining', 4.0)
    kit._raised_parapet([l2w(acx, acy, ayaw, sgn * 7.0, -34), l2w(acx, acy, ayaw, sgn * 7.0, 34)], gA + 4.6)
    fx_, fy_ = l2w(acx, acy, ayaw, un * 20, sgn * 14)  # twin stairs on the Lake side, climbing back up to the drive
    kit.stairs(fx_, fy_, ayaw + (math.pi if un > 0 else 0.0), 4.4, 8.0)
FX, FY = l2w(acx, acy, ayaw, un * 44, 0)  # the Angel fountain, on the lower terrace between the arcade and the Lake
kit.surface('flagstone', FX, FY, 70, 60, ayaw)
mark_poly([l2w(FX, FY, ayaw, u, v) for (u, v) in ((-35, -30), (35, -30), (35, 30), (-35, 30))], 3)
gF = ground(FX, FY) + LAYER['flagstone']
cylinder('grey', FX, FY, gF - 0.1, 0.9, 29.0)
cylinder('grey', FX, FY, gF, 3.0, 3.0)
cylinder('grey', FX, FY, gF + 3.0, 1.2, 6.0)
cylinder('grey', FX, FY, gF + 4.2, 2.2, 1.2)
for j in range(-3, 4):
    for i in range(-3, 4):
        if math.hypot(i * 4, j * 4) < 13:
            add(WATER, FX + i * 4, FY + j * 4, gF + 0.75, 1, 1, 1)
add(STATUE, FX, FY, gF + 6.4, 2.4, 2.4, 2.4, ayaw + math.pi)
st('bethesda')
for q in range(40):
    a_ = q / 40 * 6.283
    put(rng.choice(PEOPLE), FX + 17 * math.cos(a_), FY + 17 * math.sin(a_), LAYER['flagstone'], 1.0, a_ + math.pi)

# ---- 4. hand-placed landmarks OSM only names ---------------------------------------------------------------
OBX, OBY = ll(40.77962, -73.96541)  # Cleopatra's Needle: 21 m on a granite base
gO = ground(OBX, OBY)
kit.surface('flagstone', OBX, OBY, 24, 24)
box('black', OBX, OBY, gO, 2.2, 5, 5)
box('grey', OBX, OBY, gO + 2.2, 18.5, 2.4, 2.4)
add(PYRAMID, OBX, OBY, gO + 21.7, 2.4, 2.4, 2.0, 0)
st('obelisk')
IMX, IMY = next(
    ((p['x'], p['y']) for p in F['points'] if p['tags'].get('name') == 'Strawberry Fields' and p['kind'] == 'memorial'),
    ll(40.77565, -73.97524),
)
kit.surface('flagstone', IMX, IMY, 24, 24)
st('imagine')
for q in range(10):
    a_ = q / 10 * 6.283
    kit.bench(IMX + 11 * math.cos(a_), IMY + 11 * math.sin(a_), a_ + math.pi / 2, -1)
TGX, TGY = ll(40.77215, -73.97785)  # Tavern on the Green: textured workshop meshes and a terrace
gT = ground(TGX, TGY)
add('NewRow_97', *l2w(TGX, TGY, pth, -6, 0), gT, 1.6, 1.6, 1.3, pth)
add('NewRow_95', *l2w(TGX, TGY, pth, 20, 0), gT, 1.3, 1.3, 1.2, pth)
kit.surface('flagstone', *l2w(TGX, TGY, pth, 0, 18), 44, 12, pth)
for q in range(10):
    put(TABLE, *l2w(TGX, TGY, pth, -18 + q * 4, 18), LAYER['flagstone'], 1.0, pth)
    put(CHAIR, *l2w(TGX, TGY, pth, -18 + q * 4, 19.5), LAYER['flagstone'], 1.0, pth + math.pi)
CHX, CHY = ll(40.77465, -73.97345)  # Cherry Hill fountain and turnaround
kit.surface('flagstone', CHX, CHY, 40, 40)
gC = ground(CHX, CHY) + LAYER['flagstone']
cylinder('grey', CHX, CHY, gC - 0.1, 0.8, 7.0)
cylinder('grey', CHX, CHY, gC, 3.5, 0.8)
st('cherry_hill')

# ---- 5. buildings: park structures (asset-first) and the city -----------------------------------------------
SUPERTALL = {
    'One57': 306,
    'Central Park Tower': 472,
    '111 West 57th Street': 435,
    'Steinway Tower': 435,
    '432 Park Avenue': 426,
    '220 Central Park South': 290,
    '53 West 53': 320,
    'Carnegie Hall Tower': 231,
    'Metropolitan Tower': 218,
    'Trump International Hotel and Tower': 177,
    'Time Warner Center': 229,
    'Deutsche Bank Center': 229,
    'The Plaza': 76,
    'Essex House': 155,
    'Hampshire House': 105,
}
COTTAGES = {
    'Swedish Cottage Marionette Theatre': 'NewRow_788',
    'The Dairy (Visitor Center and Gift Shop)': 'NewRow_790',
    'Chess and Checkers House': 'NewRow_791',
    'Mineral Springs': 'NewRow_789',
    "Ladies' Pavilion": 'NewRow_233',
    'Cop Cot': 'NewRow_233',
    'Summerhouse at the Dene': 'NewRow_233',
    'Ballfields Café': 'NewRow_231',
    'Zoo Tickets': 'NewRow_230',
}


def material_for(h, tags, key):
    """Facade colour from height, OSM colour and a stable hash of the footprint."""
    hv = int(hashlib.md5(key.encode()).hexdigest()[:4], 16) / 65535
    col = (tags.get('building:colour') or '').lower()
    if tags.get('building') in ('church', 'cathedral', 'synagogue', 'museum', 'hotel') and h < 90:
        return 'concrete'
    if h >= 150:
        return 'black' if hv < 0.7 else 'grey'
    if h >= 60:
        return 'black' if hv < 0.45 else ('grey' if hv < 0.75 else 'concrete')
    if 'brick' in col or 'red' in col or 'brown' in col:
        return 'brick'
    return 'brick' if hv < 0.5 else 'concrete'


def near_park(x, y):
    """Within about 350 m of the park rectangle: these facades get window decals."""
    return (-420 < y < 160 and abs(x) < 900) or (y <= 160 and abs(x) - 420 < 350) or (y >= 160 and (abs(x) < 700))


facades = []
building_rects = []
bld_count = 0
for p in F['polys']:
    if p['kind'] != 'building':
        continue
    pts, tags = p['pts'], p['tags']
    cx, cy = centroid(pts)
    a = poly_area(pts)
    if a < 10 or abs(cx) > BOARD or abs(cy) > BOARD:
        continue
    nm = tags.get('name') or ''
    try:
        h = float(str(tags.get('height', '')).replace('m', '').strip() or 0)
    except ValueError:
        h = 0.0
    if not h and tags.get('building:levels'):
        try:
            h = float(tags['building:levels']) * 3.4
        except ValueError:
            h = 0.0
    for key, hh in SUPERTALL.items():
        if key.lower() in nm.lower():
            h = max(h, hh)
    inside = in_park(cx, cy)
    if not h:
        h = 6.0 if inside else (22.0 if a < 800 else 35.0)
    if LITE and not inside and math.hypot(cx, cy - 600) > 1300 and a < 400:
        continue
    kind = material_for(h, tags, str(pts[0]))
    bld_count += 1
    if inside:
        mark_poly(pts, 3)
    g = ground(cx, cy)
    if nm in COTTAGES:  # small Victorian structures: a real house / pavilion mesh fitted to the footprint
        rx, ry, lx, ly, th = min_rect(pts)
        row = COTTAGES[nm]
        mx, my, mh = size(row)
        sx, sy = max(0.6, min(2.0, (lx + 2) / mx)), max(0.6, min(2.0, (ly + 2) / my))
        add(row, rx, ry, g + 0.15, sx, sy, min(sx, sy), th)
        st('cottages')
        continue
    if nm == 'Belvedere Castle':  # Vista Rock mound, then the castle and its tower
        rx, ry, lx, ly, th = min_rect(pts)
        tiers = ((1.0, 4.0), (0.8, 4.0), (0.62, 3.5))
        for k_, (sc, hh) in enumerate(tiers):
            box('grey', rx, ry, g - 0.3 + sum(t[1] for t in tiers[:k_]), hh + 0.3, (lx + 30) * sc, (ly + 30) * sc, th)
        for _ in range(30):
            u, v = rng.uniform(-(lx + 30) / 2, (lx + 30) / 2), rng.uniform(-(ly + 30) / 2, (ly + 30) / 2)
            fr_ = max(abs(u) / ((lx + 30) / 2), abs(v) / ((ly + 30) / 2))
            dz = 11.5 if fr_ <= 0.62 else (8.0 if fr_ <= 0.8 else 4.0)
            put(
                rng.choice(ROCKS + [CLIFF]),
                *l2w(rx, ry, th, u, v),
                dz - 0.3,
                rng.uniform(1.5, 3.0),
                rng.uniform(0, 6.28),
            )
        base = g + 11.5
        for rx_, ry_, lx_, ly_, th_ in fill_rects(pts, 6):
            box('brick', rx_, ry_, base, 9.0, lx_, ly_, th_)
            box('concrete', rx_, ry_, base + 9.0, 0.5, lx_ + 0.6, ly_ + 0.6, th_)
        tx, ty = l2w(rx, ry, th, lx * 0.3, 0)
        cylinder('grey', tx, ty, base, 20.0, 7.0)
        cylinder('grey', tx, ty, base + 20, 2.0, 8.0)
        add(PYRAMID, tx, ty, base + 22.0, 7, 7, 6, 0)
        for q in range(12):
            a_ = q / 12 * 6.283
            box('grey', tx + 4.2 * math.cos(a_), ty + 4.2 * math.sin(a_), base + 20.5, 1.2, 1.0, 1.0, a_)
        kit.surface('flagstone', *l2w(rx, ry, th, -lx * 0.5 - 8, 0), 16, ly + 10, th, z_base=base)
        kit.stairs(*l2w(rx, ry, th, -lx * 0.5 - 24, 0), th, 11.5, 6.0)
        st('belvedere')
        continue
    if nm == 'Delacorte Theater':
        kit.wall(pts + pts[:1], 'retaining', 6.0)
        box('concrete', cx, cy, g, 1.2, 20, 14, pth)
        st('delacorte')
        continue
    if nm == 'Central Park Carousel':
        cylinder('default', cx, cy, g - 0.2, 5.2, 16.0)
        add(PYRAMID, cx, cy, g + 7.5, 18, 18, 5, 0)
        for q in range(12):
            a_ = q / 12 * 6.283
            put(rng.choice(PEOPLE), cx + 11 * math.cos(a_), cy + 11 * math.sin(a_), 0.0, 1.0, a_ + math.pi)
        st('carousel')
        continue
    if nm == 'Naumburg Bandshell':
        rx, ry, lx, ly, th = min_rect(pts)
        cylinder('grey', cx, cy, g, 9.0, max(lx, ly))
        box('concrete', cx, cy, g - 0.2, 1.7, lx + 4, ly + 4, th)
        st('bandshell')
        continue
    rects = fill_rects(pts, 10 if a > 400 else 4)
    if not inside and not LITE:  # paved block around city buildings (the landscape is grass)
        rx, ry, lx, ly, th = min_rect(pts)
        kit.surface('pavement3', rx, ry, lx + 8, ly + 8, th)
    placed = kit.building(rects, h, kind, named=(bool(nm) and inside) or h > 60)
    for rx, ry, lx, ly, th, top, used_mesh in placed:
        building_rects.append((rx, ry, lx, ly, th, h))
        if (
            WITH_WINDOWS
            and not used_mesh
            and min(lx, ly) >= 6
            and ((h >= 25 and not inside and near_park(rx, ry)) or (inside and h >= 8))
        ):
            facades.append(
                (rx, ry, g, h, lx, ly, th, 'glass' if kind == 'black' else 'punched', str(rx) + str(ry), inside)
            )
        if not used_mesh and h >= 20 and not inside and not LITE and lx * ly > 150 and rng.random() < 0.3:
            box(
                'grey',
                *l2w(rx, ry, th, rng.uniform(-lx / 4, lx / 4), rng.uniform(-ly / 4, ly / 4)),
                top,
                rng.uniform(2.5, 4),
                3,
                4,
                th,
            )
            if rng.random() < 0.4:
                s = rng.uniform(0.8, 1.1)
                add(
                    WATER_TOWER,
                    *l2w(rx, ry, th, rng.uniform(-lx / 4, lx / 4), rng.uniform(-ly / 4, ly / 4)),
                    top,
                    s,
                    s,
                    s,
                    th,
                )
st('buildings', bld_count)
rect_index = {}
for i, (rx, ry, lx, ly, th, h) in enumerate(building_rects):
    r = math.hypot(lx, ly) / 2
    for gx in range(int((rx - r) // 40), int((rx + r) // 40) + 1):
        for gy in range(int((ry - r) // 40), int((ry + r) // 40) + 1):
            rect_index.setdefault((gx, gy), []).append(i)


def building_at(x, y, margin=0.5):
    """Index of the building rectangle containing (x, y), or None."""
    for i in rect_index.get((int(x // 40), int(y // 40)), ()):
        rx, ry, lx, ly, th, h = building_rects[i]
        c, s = math.cos(th), math.sin(th)
        u = (x - rx) * c + (y - ry) * s
        v = -(x - rx) * s + (y - ry) * c
        if abs(u) <= lx / 2 + margin and abs(v) <= ly / 2 + margin:
            return i
    return None


def window_png(style, cols, rows, path):
    """Window-grid decal texture: 'punched' stone windows or a 'glass' curtain wall."""
    from PIL import Image, ImageDraw

    cw, ch = 48, 48
    img = Image.new('RGBA', (cols * cw, rows * ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for r in range(rows):
        shade = 0.82 + 0.18 * math.sin(r * 1.7)
        for c in range(cols):
            if style == 'punched':
                x0, y0 = c * cw + int(cw * 0.24), r * ch + int(ch * 0.18)
                x1, y1 = c * cw + int(cw * 0.76), r * ch + int(ch * 0.82)
                d.rectangle((x0, y0, x1, y1), fill=(int(28 * shade), int(36 * shade), int(50 * shade), 255))
                d.rectangle((x0, y0, x1, y0 + 3), fill=(int(150 * shade), int(170 * shade), int(195 * shade), 255))
                d.rectangle((x0, y0, x1, y1), outline=(220, 215, 205, 255))
            else:
                d.rectangle(
                    (c * cw, r * ch, (c + 1) * cw, (r + 1) * ch),
                    fill=(int(70 * shade), int(92 * shade), int(118 * shade), 255),
                )
                d.rectangle(
                    (c * cw, r * ch + int(ch * 0.74), (c + 1) * cw, (r + 1) * ch),
                    fill=(int(38 * shade), int(44 * shade), int(52 * shade), 255),
                )
                d.line((c * cw, r * ch, c * cw, (r + 1) * ch), fill=(190, 195, 200, 255), width=2)
                d.line((c * cw, r * ch, (c + 1) * cw, r * ch), fill=(190, 195, 200, 255), width=2)
    img.save(path)


COLS_B = [3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32]
ROWS_B = [6, 8, 10, 12, 15, 18, 22, 26, 30, 36, 42, 50, 60, 72, 85, 100]


def nearest(v, b):
    """Closest bucket value."""
    return min(b, key=lambda q: abs(q - v))


for cx, cy, z0, h, lx, ly, th, style, key, inside in facades:
    fl = 3.6 if style == 'punched' else 4.0
    wm = 2.6 if style == 'punched' else 1.6
    rows_n = nearest(h / fl, ROWS_B)
    for fx, fy, length, nyaw, u_edge, v_edge, nu, nv in rect_faces(cx, cy, lx, ly, th):
        px, py = fx + 0.8 * math.cos(nyaw), fy + 0.8 * math.sin(nyaw)
        j = building_at(px, py, 0.0)
        if j is not None and building_rects[j][5] + 1 >= h * 0.5:
            continue
        if (
            not inside
            and not in_park(fx + 60 * math.cos(nyaw), fy + 60 * math.sin(nyaw))
            and not in_park(fx + 200 * math.cos(nyaw), fy + 200 * math.sin(nyaw))
        ):
            continue
        cols_n = nearest(length / wm, COLS_B)
        k = f'{style}_{cols_n}x{rows_n}'
        name = 'decal_1791400000-' + hashlib.md5(k.encode()).hexdigest().upper() + '.png'
        decal_files[name] = ('win', style, cols_n, rows_n)
        add(name, fx, fy, z0 + h / 2, 2.0, h / 4, length / 4, rot=decal_rot(nyaw), store=decal_rows)
        st('win_decals')

# ---- 6. trees: mapped trees by genus, woods, the rest of the park, the Pinetum, street trees ----------------
GENUS = {
    'ulmus': ELM,
    'acer': MAPLE,
    'quercus': OAK,
    'pinus': PINES[0],
    'platanus': ALDER,
    'tilia': ALDER,
    'prunus': MAPLE,
}


def tree_row(tags):
    """Tree mesh for an OSM genus/species tag."""
    g = (tags.get('genus') or tags.get('species') or '').lower().split(' ')[0]
    return GENUS.get(g, rng.choice(TREES))


def tree(x, y, row=None, s=None):
    """A tree on free ground; False if the cell is a path, water or hard surface."""
    if occ_at(x, y) in (1, 2, 3):
        return False
    s = s or rng.uniform(0.85, 1.35)
    put(row or rng.choice(TREES), x, y, 0, s, rng.uniform(0, 6.28))
    mark(x, y, 1)
    st('trees')
    return True


for p in F['points']:
    if p['kind'] == 'tree' and in_park(p['x'], p['y']):
        tree(p['x'], p['y'], tree_row(p['tags']))
for p in F['polys']:
    if p['kind'] != 'wood' or not in_park(*centroid(p['pts'])):
        continue
    xs = [q[0] for q in p['pts']]
    ys = [q[1] for q in p['pts']]
    pine = 'Pinetum' in (p['tags'].get('name') or '')
    n = int(poly_area(p['pts']) / 55)
    for _ in range(n * 3):
        if n <= 0:
            break
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if point_in_poly(x, y, p['pts']) and tree(
            x, y, rng.choice(PINES) if pine else rng.choice(TREES + [OAK, BIG_ELM] + PINES), rng.uniform(0.9, 1.5)
        ):
            n -= 1
xs = [q[0] for q in PARK]
ys = [q[1] for q in PARK]
want = int(poly_area(PARK) / 420)
for _ in range(want * 4):
    if want <= 0:
        break
    x, y = (
        rng.uniform(max(min(xs), -BOARD), min(max(xs), BOARD)),
        rng.uniform(max(min(ys), -BOARD), min(max(ys), BOARD)),
    )
    if not in_park(x, y) or occ_at(x, y) in (1, 2, 3, 4):
        continue
    if any(occ_at(x + dx, y + dy) == 1 for dx in (-4, 4) for dy in (-4, 4)) and rng.random() < 0.5:
        continue
    if tree(x, y):
        want -= 1
for p in F['points']:
    if p['kind'] == 'tree' and not in_park(p['x'], p['y']) and not LITE and building_at(p['x'], p['y'], 0.5) is None:
        put(rng.choice(TREES), p['x'], p['y'], 0, rng.uniform(0.8, 1.1), rng.uniform(0, 6.28))
        st('street_trees')
for p in F['polys']:  # the Conservatory Garden's hedges, if it is on the board
    if (p['tags'].get('name') or '') == 'Conservatory Garden' and abs(centroid(p['pts'])[1]) < BOARD:
        cx, cy, lx, ly, th = min_rect(p['pts'])
        for v in (-ly / 2 + 6, ly / 2 - 6):
            for x, y, yaw, dist in along_line([l2w(cx, cy, th, -lx / 2 + 6, v), l2w(cx, cy, th, lx / 2 - 6, v)], 2.0):
                put(rng.choice(BUSHES), x, y, 0, 1.1, rng.uniform(0, 6.28))
        st('conservatory_garden')

# ---- 7. furniture, vendors and people -----------------------------------------------------------------------
mapped_lamps = {cell(p['x'], p['y']) for p in F['points'] if p['kind'] == 'lamp' and in_park(p['x'], p['y'])}
for p in F['points']:
    if p['kind'] == 'lamp' and in_park(p['x'], p['y']):
        put(LAMP_SHORT, p['x'], p['y'], 0, 1.0, rng.uniform(0, 6.28))
        st('mapped_lamps')


def nearest_path(x, y):
    """(distance, path yaw, side) of the closest in-park path to a point; side +1 = the point is on the path's left."""
    best = None
    for pts, w, mat, inside, k, nm, bridge in path_lines:
        if not inside:
            continue
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            d2 = dx * dx + dy * dy
            if d2 < 1e-6:
                continue
            t = max(0, min(1, ((x - x0) * dx + (y - y0) * dy) / d2))
            d = math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))
            if best is None or d < best[0]:
                cross = dx * (y - y0) - dy * (x - x0)
                best = (d, math.atan2(dy, dx), 1 if cross > 0 else -1)
    return best


for p in F['points']:
    if p['kind'] == 'bench' and in_park(p['x'], p['y']):
        best = nearest_path(p['x'], p['y'])
        if best and best[0] < 12:
            kit.bench(p['x'], p['y'], best[1], best[2])
            st('mapped_benches')
for pts, w, mat, inside, k, nm, bridge in path_lines:
    if not inside or bridge:
        continue
    drive = mat == 'asphalt' and w >= 11
    for x, y, yaw, dist in along_line(pts, 1.0):
        side = 1 if int(dist / 25) % 2 == 0 else -1
        if dist % 25 < 1 and cell(x, y) not in mapped_lamps:
            put(LAMP_SHORT, *l2w(x, y, yaw, 0, side * (w / 2 + 0.6)), 0, 1.0, yaw + side * math.pi / 2)
            st('lamps')
        if dist % 11 < 1 and (drive or k == 'pedestrian'):
            kit.bench(*l2w(x, y, yaw, 0, -side * (w / 2 + 0.9)), yaw, -side)
        if dist % 60 < 1:
            put(TRASH, *l2w(x, y, yaw, 1.5, side * (w / 2 + 0.5)), 0, 1.0, yaw)
        if dist % (14 if drive else 28) < 1:
            put(
                rng.choice(PEOPLE),
                *l2w(x, y, yaw, 0, rng.uniform(-w / 2 + 0.6, w / 2 - 0.6)),
                LAYER[mat],
                1.0,
                yaw + (0 if rng.random() < 0.5 else math.pi),
            )
            st('people')
        if drive and dist % 45 < 1:
            put(rng.choice(CARS), *l2w(x, y, yaw, 0, rng.choice([-3.0, 3.0])), LAYER['asphalt'], 1.0, yaw)
            st('cars')
for p in F['polys']:
    nm = p['tags'].get('name') or ''
    if nm == 'Sheep Meadow' or (p['kind'] == 'plaza' and 'Playground' in nm and in_park(*centroid(p['pts']))):
        kit.wall(p['pts'] + p['pts'][:1], 'fence', 1.5)
        if nm == 'Sheep Meadow':
            xs = [q[0] for q in p['pts']]
            ys = [q[1] for q in p['pts']]
            for _ in range(140):
                x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
                if point_in_poly(x, y, p['pts']):
                    put(rng.choice(PEOPLE_SIT + PEOPLE), x, y, 0.0, 1.0, rng.uniform(0, 6.28))
                    st('people')
# vendors: mapped food points in the park, a kiosk and crowds at every gate plaza, carts all along Central Park South
for p in F['points']:
    if (
        p['kind'] in ('ice_cream', 'fast_food', 'cafe')
        and in_park(p['x'], p['y'])
        and building_at(p['x'], p['y'], 1.0) is None
    ):
        put(rng.choice([FOOD_CART, FOOD_STALL]), p['x'], p['y'], 0, 1.0, rng.uniform(0, 6.28))
        st('carts')
for p in F['polys']:
    cx, cy = centroid(p['pts'])
    if (
        p['kind'] == 'plaza'
        and in_park(cx, cy)
        and abs(cy) < BOARD
        and any(not in_park(cx + dx, cy + dy) for (dx, dy) in ((60, 0), (-60, 0), (0, 60), (0, -60)))
    ):
        kit.kiosk(cx + rng.uniform(-8, 8), cy + rng.uniform(-8, 8), rng.uniform(0, 6.28))
        for q in range(2):
            put(
                rng.choice([FOOD_CART, FOOD_STALL]),
                cx + rng.uniform(-12, 12),
                cy + rng.uniform(-12, 12),
                0,
                1.0,
                rng.uniform(0, 6.28),
            )
        for q in range(10):
            put(
                rng.choice(PEOPLE), cx + rng.uniform(-14, 14), cy + rng.uniform(-14, 14), 0.0, 1.0, rng.uniform(0, 6.28)
            )
        st('gate_vendors')
south = sorted([(x, y) for (x, y) in PARK if y > max(q[1] for q in PARK) - 40], key=lambda q: q[0])
if len(south) >= 2:
    for x, y, yaw, dist in along_line([south[0], south[-1]], 38):
        put(rng.choice([FOOD_CART, FOOD_STALL]), *l2w(x, y, yaw, 0, 9), 0, 1.0, yaw)
        for q in range(4):
            put(
                rng.choice(PEOPLE),
                *l2w(x, y, yaw, rng.uniform(-8, 8), rng.uniform(7, 12)),
                0.0,
                1.0,
                rng.uniform(0, 6.28),
            )
        st('south_carts')
# city edge: traffic, lamps and people on the streets that frame the park
for pts, w, mat, inside, k, nm, bridge in path_lines:
    if inside or k not in ('primary', 'secondary', 'tertiary', 'residential') or LITE:
        continue
    if not any(
        in_park(x + dx, y + dy)
        for (x, y) in pts[:: max(1, len(pts) // 4)]
        for (dx, dy) in ((0, 0), (120, 0), (-120, 0), (0, 120), (0, -120))
    ):
        continue
    for x, y, yaw, dist in along_line(pts, 36):
        if building_at(x, y, 0.5) is not None:
            continue
        put(
            rng.choice(CARS),
            *l2w(x, y, yaw, 0, rng.choice([-w / 4, w / 4])),
            LAYER['asphalt'],
            1.0,
            yaw + (0 if rng.random() < 0.5 else math.pi),
        )
        st('street_cars')
        if int(dist) % 72 < 36:
            for sgn in (-1, 1):
                lx_, ly_ = l2w(x, y, yaw, 0, sgn * (w / 2 + 1.2))
                if building_at(lx_, ly_, 0.3) is None:
                    put(LAMP_TALL, lx_, ly_, LAYER['pavement2'], 1.0, yaw + sgn * math.pi / 2)
                    st('street_lamps')
        px_, py_ = l2w(x, y, yaw, rng.uniform(-10, 10), rng.choice([-1, 1]) * (w / 2 + 2.0))
        if building_at(px_, py_, 0.3) is None:
            put(rng.choice(PEOPLE), px_, py_, LAYER['pavement2'], 1.0, rng.uniform(0, 6.28))
            st('street_people')

# ---- 8. Columbus Circle and Grand Army Plaza ---------------------------------------------------------------
COL = next(
    (
        (p['x'], p['y'])
        for p in F['points']
        if p['tags'].get('name') == 'Christopher Columbus' and p['kind'] == 'artwork' and not in_park(p['x'], p['y'])
    ),
    None,
)
if COL and abs(COL[0]) < BOARD and abs(COL[1]) < BOARD:
    cx, cy = COL
    g = ground(cx, cy)
    kit.surface('flagstone', cx, cy, 50, 50)
    cylinder('grey', cx, cy, g, 4.0, 6.0)
    cylinder('grey', cx, cy, g + 4.0, 21.0, 2.4)
    cylinder('grey', cx, cy, g + 25.0, 1.0, 3.2)
    add(STATUE, cx, cy, g + 26.0, 2, 2, 2, rng.uniform(0, 6.28))
    for d in (16.0, 24.0):
        cylinder('grey', cx, cy, g + 0.1, 0.7, d)
    for j in range(-3, 4):
        for i in range(-3, 4):
            if 3.5 < math.hypot(i * 4, j * 4) < 11.5:
                add(WATER, cx + i * 4, cy + j * 4, g + 0.7, 1, 1, 1)
    for q in range(24):
        a_ = q / 24 * 6.283
        put(rng.choice(PEOPLE), cx + 14 * math.cos(a_), cy + 14 * math.sin(a_), LAYER['flagstone'], 1.0, a_ + math.pi)
    st('columbus_circle')
GAP = sorted(
    (p for p in F['polys'] if p['tags'].get('name') == 'Grand Army Plaza'), key=lambda p: centroid(p['pts'])[1]
)
if len(GAP) >= 2:
    for p in GAP:
        for q, (rx, ry, lx, ly, th) in enumerate(fill_rects(p['pts'], 8)):
            kit.surface('flagstone', rx, ry, lx, ly, th, q)
    nx_, ny_ = centroid(GAP[0]['pts'])
    sx_, sy_ = centroid(GAP[1]['pts'])
    gN, gS = ground(nx_, ny_) + LAYER['flagstone'], ground(sx_, sy_) + LAYER['flagstone']
    box('grey', nx_, ny_, gN, 3.0, 5, 5)
    add(STATUE, nx_, ny_, gN + 3.0, 2.2, 2.2, 2.2, math.pi / 2)
    cylinder('grey', sx_, sy_, gS - 0.1, 0.8, 24.0)
    cylinder('grey', sx_, sy_, gS, 2.5, 6.0)
    cylinder('grey', sx_, sy_, gS + 2.5, 2.0, 3.5)
    cylinder('grey', sx_, sy_, gS + 4.5, 3.0, 1.0)
    add(STATUE, sx_, sy_, gS + 7.5, 1.4, 1.4, 1.4, 0)
    for j in range(-3, 4):
        for i in range(-3, 4):
            if math.hypot(i * 4, j * 4) < 11:
                add(WATER, sx_ + i * 4, sy_ + j * 4, gS + 0.65, 1, 1, 1)
    for q in range(30):
        put(
            rng.choice(PEOPLE),
            sx_ + rng.uniform(-18, 18),
            sy_ + rng.uniform(-18, 18),
            LAYER['flagstone'],
            1.0,
            rng.uniform(0, 6.28),
        )
    st('grand_army_plaza')


# ---- 9. Imagine mosaic decal (ground) ----------------------------------------------------------------------
def imagine_png(path):
    """The Strawberry Fields mosaic as a 512 px decal: concentric rings, radial joints, IMAGINE across the middle."""
    from PIL import Image, ImageDraw, ImageFont

    S = 512
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r0 = S / 2 - 6
    d.ellipse((6, 6, S - 6, S - 6), fill=(236, 232, 222, 255), outline=(70, 70, 70, 255), width=8)
    for q in range(1, 9):
        rr = r0 * q / 9
        d.ellipse((S / 2 - rr, S / 2 - rr, S / 2 + rr, S / 2 + rr), outline=(60, 60, 60, 255), width=3)
    for q in range(36):
        a_ = q / 36 * 6.283
        d.line(
            (
                S / 2 + r0 * 0.25 * math.cos(a_),
                S / 2 + r0 * 0.25 * math.sin(a_),
                S / 2 + r0 * math.cos(a_),
                S / 2 + r0 * math.sin(a_),
            ),
            fill=(60, 60, 60, 255),
            width=2,
        )
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Georgia.ttf', 74)
    except Exception:
        font = ImageFont.load_default()
    bb = d.textbbox((0, 0), 'IMAGINE', font=font)
    d.rectangle(
        (S / 2 - (bb[2] - bb[0]) / 2 - 10, S / 2 - 44, S / 2 + (bb[2] - bb[0]) / 2 + 10, S / 2 + 44),
        fill=(236, 232, 222, 255),
    )
    d.text((S / 2 - (bb[2] - bb[0]) / 2, S / 2 - (bb[3] - bb[1]) / 2 - 8), 'IMAGINE', fill=(40, 40, 40, 255), font=font)
    img.save(path)


if WITH_WINDOWS:
    name = 'decal_1791400002-' + hashlib.md5(b'imagine').hexdigest().upper() + '.png'
    decal_files[name] = ('imagine',)
    add(
        name,
        IMX,
        IMY,
        ground(IMX, IMY) + LAYER['flagstone'] + 0.5,
        1.0,
        0.65,
        0.65,
        rot=quat_from_axes((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
        store=decal_rows,
    )

# ---- output ---------------------------------------------------------------------------------------------------
north = FR.xy(FRAME['lat0'] + 0.001, FRAME['lon0'])
north_yaw = math.degrees(math.atan2(north[1], north[0]))
cam = (0.0, 420.0, G0 + 95.0)
cam_yaw = -90.0
cam_pitch = math.degrees(math.atan2(G0 - cam[2], 420))


def thumbnail(path):
    """Top-down thumbnail from the OSM features."""
    from PIL import Image, ImageDraw

    W = 1024
    img = Image.new('RGB', (W, W), (150, 190, 130))
    d = ImageDraw.Draw(img)
    sc = W / 2400

    def px(x, y):
        return (W / 2 - x * sc, W / 2 + y * sc)

    col = dict(
        water=(120, 170, 230),
        grass=(150, 200, 130),
        wood=(80, 140, 80),
        building=(110, 110, 120),
        plaza=(200, 195, 185),
        rock=(160, 150, 140),
        park=(135, 185, 115),
    )
    for k in ('park', 'grass', 'wood', 'rock', 'plaza', 'water', 'building'):
        for p in F['polys']:
            if p['kind'] == k:
                d.polygon([px(x, y) for x, y in p['pts']], fill=col[k])
    for l in F['lines']:
        if l['kind'] in ('footway', 'pedestrian', 'path', 'service') and in_park(*l['pts'][0]):
            d.line([px(x, y) for x, y in l['pts']], fill=(245, 245, 240), width=2)
    d.text((24, W - 40), DISPLAY, fill=(20, 20, 20))
    img.save(path, quality=88)


rows_all = dict(instances)
rows_all.update(decal_rows if WITH_WINDOWS else {})
map_json = {
    'S_AssetsTransform': [dict(Rname=r, Transform=t, UniqueGroupTag=['None'] * len(t)) for r, t in rows_all.items()],
    'BaseMapRow': BASE,
    'WeatherIndex': 0,
    'Race': dict(CheckPoints=[], StartTransform=tf(0, 0, 0, dict(X=0, Y=0, Z=0, W=1)), Laps=1, BestTime=-1, Spoints=[]),
    'CamLoc': tf(cam[0], cam[1], cam[2], quat_pitch_yaw(cam_pitch, cam_yaw)),
    'CustomWeather': dict(timeOfDay=16.0, northyaw=round(north_yaw, 2), Cloud=0.2),
}
info = {
    'BaseMapRow': BASE,
    'Name': DISPLAY,
    'CreatorSteamID': STEAM_ID,
    'CreationTimeUnix': int(time.time()),
    'Track': False,
}
out = os.path.join(ROOT, 'maps', NAME)
if os.path.isdir(out):
    shutil.rmtree(out)
os.makedirs(out)
json.dump(map_json, open(os.path.join(out, NAME + '.json'), 'w'))
open(os.path.join(out, NAME + '.info'), 'w').write(json.dumps(info))
if WITH_WINDOWS:
    ddir = os.path.join(out, 'Decals')
    os.makedirs(ddir)
    for name, spec in decal_files.items():
        if spec[0] == 'win':
            window_png(spec[1], spec[2], spec[3], os.path.join(ddir, name))
        else:
            imagine_png(os.path.join(ddir, name))
    for lib in ('UserDecals', 'MapDecals'):
        ld = os.path.join(os.path.dirname(GAME_USER_MAPS), lib)
        os.makedirs(ld, exist_ok=True)
        for name in decal_files:
            shutil.copy(os.path.join(ddir, name), os.path.join(ld, name))
thumbnail(os.path.join(out, 'Thumbnail.jpg'))
dst = os.path.join(GAME_USER_MAPS, NAME)
if os.path.isdir(dst):
    shutil.rmtree(dst)
shutil.copytree(out, dst)
import mapcheck

_fl, _bu, _off = mapcheck.run(map_json, LAND, verbose=False)
_sp = mapcheck.spawn_clear(map_json, LAND, clearance=1.0)
print(
    f'checks: {sum(map(len, _fl.values()))} floating, {sum(map(len, _bu.values()))} buried, {_off} off the landscape, spawn {"CLEAR" if not _sp else "BLOCKED"}'
)
if _sp:
    raise SystemExit('SPAWN BLOCKED: the take-off point must have 1 m of open air in every direction (see above)')
n = sum(len(v) for v in rows_all.values())
print(f'{NAME}: {n} instances, {len(rows_all)} rows, north yaw {north_yaw:.1f} -> {dst}')
print(stats)
print('top rows:', {r: len(v) for r, v in sorted(instances.items(), key=lambda kv: -len(kv[1]))[:14]})
