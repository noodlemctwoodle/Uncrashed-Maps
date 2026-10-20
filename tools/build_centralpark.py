#!/usr/bin/env python3
"""Central Park for Uncrashed, built from OpenStreetMap (data/centralpark_osm.json via tools/osm.py) on the flat
Empty board. Frame: origin on the Mall at the Literary Walk, the Mall runs up -Y (the freestyle spawn faces -Y, so
you take off looking up the elm walk to Bethesda Terrace), +X is west. Every lake, lawn, wood, rock outcrop, path,
drive, arch and building comes from OSM geometry; landmarks that OSM only names (Bethesda Fountain, Belvedere on
Vista Rock, the Obelisk, Bow Bridge, the Mall's elm rows, the Imagine mosaic) are modelled on top of it. The
surrounding city uses OSM building footprints with their heights. Aerial reference: data/centralpark_naip.png.
usage: build_centralpark.py [--no-windows] [--lite]

Inputs (all under data/): centralpark_frame.json (lat0, lon0, axis_deg of the local frame), centralpark_features.json
(the osm.py output: polys / lines / points in local metres with OSM tags) and catalog.json (mesh bounds per asset
row, cm). Outputs: maps/CentralPark/ (CentralPark.json, CentralPark.info, Thumbnail.jpg, Decals/*.png), then the
whole folder is copied into the game's MapEditor/User/CentralPark and the decal PNGs into MapEditor/UserDecals and
MapEditor/MapDecals (the editor loads user decals from those libraries; without the copies they render blank).
Running this script installs the map; nothing is committed.

Units and frame: everything in this file is metres and radians (yaw counter-clockwise from +X, math.atan2
convention) until `tf()` writes Unreal centimetres. The frame is osm.Frame(lat0, lon0, axis_deg, flip_north=True):
+Y points back down the park axis (south-ish), +X to the west; the Empty board's PlayerStart is the origin facing -Y
and the board is flat at Z = 0, so `Z0` (6 cm) is the top of the ground surfaces laid here. `BOARD` (2900 m) keeps
everything inside the 6 km board. Decal transforms use the editor's basis: local X into the surface, Y world-down,
Z = X x Y along the wall, scale (depth, height/4, width/4); the ground mosaic uses the same rule with X pointing
down into the pavement.

Layer order (each section also stamps the 4 m occupancy grid `occ` so later layers avoid earlier ones):
  1. ground: a concrete slab over the city and a green lawn base over the park's bounding rectangle;
  2. surfaces from OSM polygons: water tiles (with boats and the Reservoir fence), plazas / parking / the rink,
     lawns (marked, ball fields get a dirt diamond), woods (marked), rock outcrops, fountains;
  3. paths, drives, transverses and city streets as ground planes, raised decks for bridge=yes segments, the 19
     mapped arches (man_made=bridge outlines) as fly-through decks on abutments with ramps;
  4. the Mall (four elm rows, benches, lamps), statues, Bethesda Terrace (embankment, arcade, twin stairs) and the
     fountain plaza;
  5. hand-placed landmarks OSM only names: the Obelisk, Strawberry Fields, Tavern on the Green, Cherry Hill;
  6. buildings: special massing for Belvedere, Delacorte, the Carousel and the Bandshell, generic boxes for the rest
     (setbacks on tall pre-war-style towers, roof clutter), then window decals on city facades facing the park;
  7. trees: mapped trees by genus, woods, the rest of the park, street trees;
  8. furniture and people along the paths, the Sheep Meadow and playground fences, food carts;
  9. the Imagine mosaic ground decal;
  output: map JSON, .info, decal PNGs, thumbnail, install.

Occupancy grid `occ` (4 m cells, x -800..800, y -3800..700): 0 free, 1 path (also stamped by placed trees),
2 water, 3 hard (plaza, building, rock, fountain; also returned outside the grid), 4 lawn (keep clear of trees),
5 wood. `tree()` refuses 1/2/3, the random park fill also refuses 4."""

import json, math, os, sys, time, hashlib, shutil, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geom import poly_area, centroid, min_rect, point_in_poly, decompose, rect_faces, l2w
from osm import Frame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
STEAM_ID = os.environ.get(
    'UNCRASHED_STEAM_ID', '76561197969360950'
)  # your Steam ID64: the game loads maps from MapEditor/User under it
GAME_USER_MAPS = os.path.expanduser(f'~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User')
NAME, DISPLAY = 'CentralPark', 'New York City - Central Park'
WITH_WINDOWS = '--no-windows' not in sys.argv
LITE = '--lite' in sys.argv
rng = random.Random(7)  # fixed seed: the same map every build
FRAME = json.load(open(os.path.join(DATA, 'centralpark_frame.json')))
FR = Frame(FRAME['lat0'], FRAME['lon0'], FRAME['axis_deg'], True)  # flip_north: +Y runs back down the axis
F = json.load(open(os.path.join(DATA, 'centralpark_features.json')))
CAT = json.load(open(os.path.join(DATA, 'catalog.json')))
# JSON gives lists; the geometry helpers hash/compare points, so make them tuples once
for _p in F['polys']:
    _p['pts'] = [tuple(q) for q in _p['pts']]
    _p['holes'] = [[tuple(q) for q in h] for h in _p['holes']]
for _l in F['lines']:
    _l['pts'] = [tuple(q) for q in _l['pts']]
BOARD = 2900.0  # keep inside the 6 km Empty board
Z0 = 0.06  # ground top (the board's landscape is at 0)

# ---- rows ----------------------------------------------------------------------
# Asset rows of DT_MapEditorAssets (see data/catalog.json and docs/ASSETS.md). Pivots that matter below:
# cubes / cylinders / pyramid 1 m, centre pivot; CONCRETE = SM_ConcreteFloor01 4x4x0.30 m with the pivot at the TOP;
# BRICK = SM_ConcreteWall01 0.3x4x4 m, base pivot; ground planes (ASPHALT..SAND) 4x4x0.1 m, centre pivot;
# WATER = BP_meWater 4 m tile, pivot AT the surface, 2.1 m deep. Props (trees, benches, people, ...) go through
# put(), which applies the catalog rest() correction.
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
ASPHALT, PAVE, PAVE2, DIRT, GRAVEL, SAND, WATER = (
    'NewRow_182',
    'NewRow_185',
    'NewRow_197',
    'NewRow_180',
    'NewRow_181',
    'NewRow_662',
    'NewRow_183',
)
ELM, MAPLE, ALDER, OAK, BIG_ELM, PINES = (
    'NewRow_168',
    'NewRow_269',
    'NewRow_34',
    'NewRow_78',
    'NewRow_169',
    ['NewRow_279', 'NewRow_280', 'NewRow_281'],
)
TREES = [ELM, MAPLE, ALDER]
BUSHES = ['NewRow_164', 'NewRow_226']
ROCKS = ['NewRow_71', 'NewRow_162']
CLIFF = 'NewRow_175'
LAMP_TALL, LAMP_SHORT, BENCH, TRASH, FENCE, HANDRAIL, STATUE = (
    'NewRow_3',
    'NewRow_20',
    'NewRow_204',
    'NewRow_323',
    'NewRow_777',
    'NewRow_276',
    'NewRow_213',
)
PEOPLE, PEOPLE_SIT = ['NewRow_252', 'NewRow_255', 'NewRow_801', 'NewRow_802'], ['NewRow_254', 'NewRow_800']
CARS = ['NewRow_103', 'NewRow_257', 'NewRow_93', 'NewRow_775']
BOAT, FOOD_CART, FOOD_STALL, TABLE, CHAIR = 'NewRow_329', 'NewRow_246', 'NewRow_247', 'NewRow_353', 'NewRow_352'
STAIRS, WATER_TOWER, PLANTER = 'NewRow_106', 'NewRow_251', 'NewRow_159'


def rest(row):
    """Vertical correction (m, <= 0) so a mesh placed at ground height rests on the ground instead of hovering.

    `bot` is the mesh's lowest point relative to its pivot (catalog bounds are cm: origin - extent). A mesh whose
    base sits more than 5 cm ABOVE the pivot would float by that much, so the pivot is lowered by `bot`. Meshes
    whose base is below the pivot (trees, rocks, houses) get 0: they are meant to sink a little. Rows without bounds
    (decals, unknown) get 0. Scale the result by the instance scale (see put()).
    """
    b = CAT.get(row, {}).get('bounds')
    if not b:
        return 0.0
    bot = (b['origin'][2] - b['extent'][2]) / 100.0
    return -bot if bot > 0.05 else 0.0


instances = {}  # row name -> list of transforms (the S_AssetsTransform payload)
decal_rows = {}  # decal PNG name -> list of transforms, kept apart so --no-windows can drop them
decal_files = {}  # decal PNG name -> spec tuple used to render it at output time
stats = {}  # counters printed at the end


def st(k, n=1):
    """Bump the stats counter `k` by `n`."""
    stats[k] = stats.get(k, 0) + n


def quat_yaw(yaw):
    """Quaternion (dict X, Y, Z, W) for a rotation about Z by `yaw` radians: Z = sin(yaw/2), W = cos(yaw/2)."""
    return dict(X=0.0, Y=0.0, Z=math.sin(yaw / 2), W=math.cos(yaw / 2))


def quat_pitch_yaw(pitch_deg, yaw_deg):
    """Quaternion for an Unreal rotator (pitch, yaw, roll = 0), both in DEGREES (note: unlike quat_yaw).

    Same formula as FRotator::Quaternion with the roll terms removed; positive pitch tilts the local +X up.
    """
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2
    SP, CP, SY, CY = math.sin(P), math.cos(P), math.sin(Y), math.cos(Y)
    return dict(X=SP * SY, Y=-SP * CY, Z=CP * SY, W=CP * CY)


def quat_from_axes(X, Y, Z):
    """Quaternion whose local X, Y, Z axes are the given world unit vectors (3-tuples, right-handed, orthonormal).

    Builds the rotation matrix with the axes as columns and converts it with the standard trace / largest-diagonal
    branch method (numerically safe for every orientation). Used for decals, whose basis is not a plain yaw.
    """
    m = [[X[0], Y[0], Z[0]], [X[1], Y[1], Z[1]], [X[2], Y[2], Z[2]]]
    t = m[0][0] + m[1][1] + m[2][2]
    if t > 0:
        s = math.sqrt(t + 1) * 2
        w = s / 4
        x = (m[2][1] - m[1][2]) / s
        y = (m[0][2] - m[2][0]) / s
        z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1 + m[0][0] - m[1][1] - m[2][2]) * 2
        w = (m[2][1] - m[1][2]) / s
        x = s / 4
        y = (m[0][1] + m[1][0]) / s
        z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1 + m[1][1] - m[0][0] - m[2][2]) * 2
        w = (m[0][2] - m[2][0]) / s
        x = (m[0][1] + m[1][0]) / s
        y = s / 4
        z = (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1 + m[2][2] - m[0][0] - m[1][1]) * 2
        w = (m[1][0] - m[0][1]) / s
        x = (m[0][2] + m[2][0]) / s
        y = (m[1][2] + m[2][1]) / s
        z = s / 4
    return dict(X=x, Y=y, Z=z, W=w)


def decal_rot(normal_yaw):
    """Rotation of a wall decal on a facade whose OUTWARD normal has world yaw `normal_yaw` (radians).

    Editor decal basis (measured on Workshop maps, matches Unreal's deferred-decal shader: texture U along local Z,
    V along local Y, projection along +X): X points into the surface (opposite the outward normal), Y straight
    down, Z = X x Y runs along the wall. With this basis the PNG reads upright from outside the building.
    """
    c, s = math.cos(normal_yaw), math.sin(normal_yaw)
    return quat_from_axes((-c, -s, 0.0), (0.0, 0.0, -1.0), (s, -c, 0.0))


def tf(x, y, z, rot, s=(1, 1, 1)):
    """Map-file transform: position in METRES -> Unreal cm (2 dp), quaternion `rot`, Scale3D `s` (4 dp)."""
    return dict(
        Rotation=rot,
        Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)),
        Scale3D=dict(X=round(s[0], 4), Y=round(s[1], 4), Z=round(s[2], 4)),
    )


def add(row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0, rot=None, store=None):
    """Append one instance of asset `row` at the PIVOT position (x, y, z) metres, scale (sx, sy, sz).

    `yaw` (radians) builds a plain Z rotation unless a full quaternion `rot` is given. Instances outside +-BOARD are
    silently dropped. `store` redirects the transform to another dict (the decal rows); default: `instances`.
    """
    if abs(x) > BOARD or abs(y) > BOARD:
        return
    (store if store is not None else instances).setdefault(row, []).append(
        tf(x, y, z, rot if rot else quat_yaw(yaw), (sx, sy, sz))
    )


def box(kind, cx, cy, z0, h, lx, ly, yaw=0.0):
    """Solid block lx (along yaw) x ly x h metres whose BOTTOM is at z0, from one scaled mesh.

    `kind`: 'concrete' = SM_ConcreteFloor01 (4x4x0.30 m, pivot at the top, mesh spans z -0.29..+0.01), so the pivot
    goes 0.29 * sz above z0; 'brick' = SM_ConcreteWall01 (0.3x4x4 m, base pivot) placed at z0; anything else is a
    CUBE colour (1 m, centre pivot) placed at z0 + h/2. Sizes are clamped to >= 0.1 m / 0.01 m so no scale is zero.
    """
    lx, ly, h = max(lx, 0.1), max(ly, 0.1), max(h, 0.01)
    if kind == 'concrete':
        sz = h / 0.30
        add(CONCRETE, cx, cy, z0 + 0.29 * sz, lx / 4, ly / 4, sz, yaw)
    elif kind == 'brick':
        add(BRICK, cx, cy, z0, lx / 0.3, ly / 4, h / 4, yaw)
    else:
        add(CUBE[kind], cx, cy, z0 + h / 2, lx, ly, h, yaw)


def cylinder(kind, cx, cy, z0, h, d):
    """Upright cylinder of diameter d and height h (m) standing on z0 (SM_Cylinder is 1 m, centre pivot)."""
    add(CYL[kind], cx, cy, z0 + h / 2, d, d, h)


def plane(row, x, y, z_top, lx, ly, yaw=0.0):
    """Textured ground plane (4x4x0.1 m mesh, centre pivot) scaled to lx x ly with its TOP at z_top; min 0.5 m."""
    add(row, x, y, z_top - 0.05, max(lx, 0.5) / 4, max(ly, 0.5) / 4, 1.0, yaw)
    st('planes')


def pitched(kind, x0, y0, z0, x1, y1, z1, width, thick=0.4):
    """Sloping slab (cube colour `kind`) from (x0, y0, z0) to (x1, y1, z1), `width` m across, `thick` m thick.

    Yaw follows the plan direction, pitch the rise over the plan length; the centre is dropped by thick/2 so the
    top surface runs roughly through the two end points. Ramps up to bridge decks and the Bethesda stairs.
    """
    L = math.hypot(x1 - x0, y1 - y0)
    yaw = math.degrees(math.atan2(y1 - y0, x1 - x0))
    pitch = math.degrees(math.atan2(z1 - z0, L))
    add(
        CUBE[kind],
        (x0 + x1) / 2,
        (y0 + y1) / 2,
        (z0 + z1) / 2 - thick / 2,
        math.hypot(L, z1 - z0),
        width,
        thick,
        rot=quat_pitch_yaw(pitch, yaw),
    )


def put(row, x, y, dz=0.0, s=1.0, yaw=0.0):
    """Prop on the ground: uniform scale `s`, base at Z0 + dz (m) with the catalog rest() correction scaled by s."""
    add(row, x, y, Z0 + dz + rest(row) * s, s, s, s, yaw)


def ll(lat, lon):
    """WGS84 degrees -> local metres through the map frame (for hand-placed landmarks)."""
    return FR.xy(lat, lon)


# ---- the park polygon and an occupancy grid (4 m) -----------------------------------
# PARK: the largest polygon tagged leisure=park with the name Central Park (OSM holds a few smaller ones), as a list
# of (x, y) metres. Its minimum-area rectangle gives the park grid yaw `pth` used to align lawn base, ball fields
# and Tavern on the Green.
PARK = max(
    (p for p in F['polys'] if p['kind'] == 'park' and p['tags'].get('name') == 'Central Park'),
    key=lambda p: poly_area(p['pts']),
)['pts']
pcx, pcy, plx, ply, pth = min_rect(PARK)
print(f'park rectangle {plx:.0f} x {ply:.0f} m, yaw {math.degrees(pth):.1f} deg, centre ({pcx:.0f},{pcy:.0f})')
CELL = 4.0
GX0, GY0 = -800, -3800  # grid origin (m): covers x -800..800, y -3800..700, i.e. the park plus a margin
GNX, GNY = int(1600 / CELL), int(4500 / CELL)
occ = bytearray(
    GNX * GNY
)  # 0 free, 1 path, 2 water, 3 hard (plaza/building/rock), 4 lawn (keep clear of trees), 5 wood


def cell(x, y):
    """(x, y) metres -> (i, j) grid indices (may be out of range; callers check)."""
    return (int((x - GX0) // CELL), int((y - GY0) // CELL))


def mark(x, y, v):
    """Set the occupancy value `v` of the cell containing (x, y); points outside the grid are ignored."""
    i, j = cell(x, y)
    if 0 <= i < GNX and 0 <= j < GNY:
        occ[j * GNX + i] = v


def occ_at(x, y):
    """Occupancy value at (x, y); outside the grid everything counts as 3 (hard) so nothing gets planted there."""
    i, j = cell(x, y)
    return occ[j * GNX + i] if 0 <= i < GNX and 0 <= j < GNY else 3


def mark_poly(pts, v, holes=()):
    """Stamp `v` into every cell whose centre is inside the polygon `pts` and in none of the `holes` rings."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    for j in range(int((min(ys) - GY0) // CELL), int((max(ys) - GY0) // CELL) + 1):
        for i in range(int((min(xs) - GX0) // CELL), int((max(xs) - GX0) // CELL) + 1):
            x, y = GX0 + (i + 0.5) * CELL, GY0 + (j + 0.5) * CELL
            if point_in_poly(x, y, pts) and not any(point_in_poly(x, y, h) for h in holes):
                mark(x, y, v)


def in_park(x, y):
    """True when (x, y) lies inside the Central Park outline polygon."""
    return point_in_poly(x, y, PARK)


def mark_line(pts, w, v):
    """Stamp `v` along a polyline of width `w` m: samples every ~2 m, a 3x3 stamp at 0 and +-w/2 on both axes.

    The stamp is axis-aligned, not rotated with the line, so it over-marks diagonals slightly (good enough to keep
    trees off the paths).
    """
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / 2))
        for k in range(n + 1):
            t = k / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            for dx in (-w / 2, 0, w / 2):
                for dy in (-w / 2, 0, w / 2):
                    mark(x + dx, y + dy, v)


# ---- 1. ground: city slab, park lawn base --------------------------------------------
# One 5.8 km concrete slab (top at Z0) centred on the park's middle (y -1200), then a thin green cube over the
# park's bounding rectangle (top at Z0 + 0.04) as the lawn base; the real lawns are only marked, not tiled.
box('concrete', 0, -1200, Z0 - 0.30, 0.30, 2 * BOARD, 2 * BOARD)
box('green', pcx, pcy, Z0 - 0.02, 0.06, plx, ply, pth)
st('park_base')


# ---- 2. surfaces from OSM polygons ---------------------------------------------------
def fill_rects(pts, max_rects=12):
    """Rectangles covering a polygon: geom.decompose for anything over 30 m^2, a single min_rect for small ones."""
    return decompose(pts, max_rects) if poly_area(pts) > 30 else [min_rect(pts)]


# Each polygon kind becomes a surface and stamps the occupancy grid. Heights above Z0: water surface +0.03, plazas
# +0.03, so they sit above the lawn base (+0.04 top) without fighting the paths (+0.04 / +0.05, section 3).
water_tiles = 0
for p in F['polys']:
    k, pts, tags = p['kind'], p['pts'], p['tags']
    cx, cy = centroid(pts)
    a = poly_area(pts)
    if abs(cx) > BOARD or abs(cy) > BOARD:
        continue
    inside = in_park(cx, cy)
    if k == 'water' and a > 40:
        # BP_meWater is a 4 m tile with the pivot at the surface; big water is tiled with the tile scaled 2x, 4x or
        # 6x (8 / 16 / 24 m) to keep the instance count down. cy > -1300 picks the southern half of the park.
        tile = (
            4.0 if (inside and cy > -1300 and a < 3e4) else (8.0 if a < 20e4 else 16.0)
        )  # 4 m tiles only on the small ponds; the Lake and Reservoir use 8 / 16 m
        if not inside and a > 50e4:
            tile = 24.0  # the rivers
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        # tile centres on a world-aligned lattice of pitch `tile`, kept only inside the ring and outside its islands;
        # Z scale 1.2 deepens the 2.1 m volume a little (empirical)
        for j in range(int(min(ys) // tile), int(max(ys) // tile) + 1):
            for i in range(int(min(xs) // tile), int(max(xs) // tile) + 1):
                x, y = (i + 0.5) * tile, (j + 0.5) * tile
                if point_in_poly(x, y, pts) and not any(point_in_poly(x, y, h) for h in p['holes']):
                    add(WATER, x, y, Z0 + 0.03, tile / 4, tile / 4, 1.2)
                    water_tiles += 1
        mark_poly(pts, 2, p['holes'])
        if inside and a > 3e4 and tags.get('name') == 'The Lake':
            # rowing boats: 16 tries, kept only > 12 m from the shore (every third outline vertex is checked)
            for _ in range(16):
                x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
                if point_in_poly(x, y, pts) and all(math.hypot(x - q[0], y - q[1]) > 12 for q in pts[::3]):
                    put(BOAT, x, y, 0.05, 1.0, rng.uniform(0, 6.28))
                    st('boats')
        if tags.get('name') == 'Conservatory Water':
            # the model-boat pond: the same boat mesh at 0.3 scale
            for _ in range(8):
                x, y = rng.uniform(cx - 25, cx + 25), rng.uniform(cy - 25, cy + 25)
                put(BOAT, x, y, 0.04, 0.3, rng.uniform(0, 6.28)) if point_in_poly(x, y, pts) else None
        if tags.get('name') in ('Jacqueline Kennedy Onassis Reservoir',):  # the iron fence and the running track
            # one 4 m fence piece per 4 m of shoreline, lowered to 0.8 scale in Z
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
                L = math.hypot(x1 - x0, y1 - y0)
                n = max(1, int(L // 4))
                yaw = math.atan2(y1 - y0, x1 - x0)
                for q in range(n):
                    t = (q + 0.5) / n
                    add(FENCE, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, Z0, 1, 1, 0.8, yaw)
                    st('fences')
    elif k in ('plaza', 'parking', 'rink') and inside and a > 20:
        # paved areas: up to 20 rectangles of ground plane each; the rink gets a 1 m rink wall and 30 skaters
        row = ASPHALT if k == 'parking' else (PAVE2 if k == 'rink' else PAVE)
        for rx, ry, lx, ly, th in fill_rects(pts, 20):
            plane(row, rx, ry, Z0 + 0.03, lx, ly, th)
        mark_poly(pts, 3)
        if k == 'rink':
            for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
                box(
                    'default',
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    Z0,
                    1.0,
                    math.hypot(x1 - x0, y1 - y0),
                    0.15,
                    math.atan2(y1 - y0, x1 - x0),
                )
            for _ in range(30):
                x, y = rng.uniform(cx - 30, cx + 30), rng.uniform(cy - 30, cy + 30)
                if point_in_poly(x, y, pts):
                    put(rng.choice(PEOPLE), x, y, 0.03, 1.0, rng.uniform(0, 6.28))
                    st('skaters')
    elif k == 'grass' and inside:
        # lawns are the green base already; only marked (4) so the random trees stay off them
        mark_poly(pts, 4)
        if 'Ball Field' in (tags.get('name') or '') or tags.get('sport') == 'baseball':
            # a 26 m dirt diamond turned 45 deg to the park grid, with a short backstop of 5 tall fence pieces
            plane(DIRT, cx, cy, Z0 + 0.03, 26, 26, pth + math.pi / 4)
            st('ballfields')
            for q in range(5):
                add(FENCE, *l2w(cx, cy, pth + math.pi / 4, -13 + 1 * q, -12), Z0, 1, 1, 1.4, pth + math.pi / 4)
    elif k == 'wood' and inside:
        mark_poly(pts, 5)
    elif k == 'rock' and inside and a > 40:
        # outcrops: grey slabs 0.5..2.5 m high over 90 % of each covering rectangle, plus one rock mesh per 150 m^2
        # (at least 2) at 1.2-2.6x, raised 0.3 m so they sit on the slab rather than in it (empirical)
        mark_poly(pts, 3)
        for rx, ry, lx, ly, th in fill_rects(pts, 6):
            h = min(2.5, 0.5 + math.sqrt(lx * ly) / 12)
            box('grey', rx, ry, Z0, h, lx * 0.9, ly * 0.9, th)
        for _ in range(max(2, int(a // 150))):
            x, y = rng.uniform(cx - 15, cx + 15), rng.uniform(cy - 15, cy + 15)
            if point_in_poly(x, y, pts):
                s = rng.uniform(1.2, 2.6)
                put(rng.choice(ROCKS + [CLIFF]), x, y, 0.3, s, rng.uniform(0, 6.28))
                st('rocks')
    elif k == 'fountain' and inside and a > 20:
        # basin: a 0.7 m cylinder with the polygon's equivalent diameter, a 2.5 m jet column, 4 m water tiles
        # inside the outline at +0.6 (just under the rim)
        cylinder('grey', cx, cy, Z0, 0.7, 2 * math.sqrt(a / math.pi))
        cylinder('grey', cx, cy, Z0, 2.5, 1.6)
        for j in range(-3, 4):
            for i in range(-3, 4):
                if point_in_poly(cx + i * 4, cy + j * 4, pts):
                    add(WATER, cx + i * 4, cy + j * 4, Z0 + 0.6, 1, 1, 1)
        mark_poly(pts, 3)
        st('fountains')
print('water tiles', water_tiles)

# ---- 3. paths, drives, transverses, bridges ------------------------------------------
# default widths (m) per OSM highway kind when the way has no usable width tag (typical values, empirical)
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


def is_drive(l):
    """True for the park drives: any way named '... Drive', or a service road whose first point is in the park."""
    return (l['tags'].get('name') or '').endswith('Drive') or l['kind'] == 'service' and in_park(*l['pts'][0])


def is_transverse(l):
    """True for the sunken transverse roads (named '... Transverse', mapped as tertiary/secondary/residential)."""
    return 'Transverse' in (l['tags'].get('name') or '') and l['kind'] in ('tertiary', 'secondary', 'residential')


# Every highway way becomes a run of ground planes along its real geometry. Outside the park only roads are built
# (no city footpaths, no tunnels); inside, bridge=yes segments become raised grey decks you can fly under.
# path_lines keeps (pts, width, row, inside, kind, name, bridge) for the furniture pass in section 8.
path_lines = []
for l in F['lines']:
    k = l['kind']
    pts = l['pts']
    if k not in PATH_W or len(pts) < 2:
        continue
    inside = in_park(*pts[len(pts) // 2])
    if not inside and k in ('footway', 'path', 'steps', 'pedestrian', 'bridleway', 'cycleway'):
        continue
    if l['tags'].get('tunnel') == 'yes' and not inside:
        continue
    w = parse_width(l['tags'].get('width')) or PATH_W[k]
    # surface by role: drives and transverses are 12 m asphalt, foot paths pavement, the bridle path dirt
    if is_drive(l):
        w = max(w, 12.0)
        row = ASPHALT
    elif is_transverse(l):
        w = 12.0
        row = ASPHALT
    elif k in ('footway', 'path', 'steps', 'pedestrian'):
        row = PAVE if inside else PAVE
    elif k == 'bridleway':
        row = DIRT
    elif k == 'cycleway':
        row = ASPHALT
    else:
        row = ASPHALT
    bridge = l['tags'].get('bridge') == 'yes'
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 0.5:
            continue
        # pieces of <= 22 m so the 4 m plane is never stretched too far; +0.6 m overlap hides the seams.
        # Asphalt sits at +0.04 and pavement at +0.05 so paths crossing drives do not z-fight.
        n = max(1, int(math.ceil(L / 22)))
        yaw = math.atan2(y1 - y0, x1 - x0)
        for q in range(n):
            t0, t1 = q / n, (q + 1) / n
            mx, my = x0 + (x1 - x0) * (t0 + t1) / 2, y0 + (y1 - y0) * (t0 + t1) / 2
            if bridge and inside:
                # deck bottom 2.6 m up, 0.4 m thick: a flyable gap under every mapped footbridge
                box('grey', mx, my, Z0 + 2.6, 0.4, L / n + 0.5, w, yaw)
                st('bridge_decks')
            else:
                plane(row, mx, my, Z0 + (0.04 if row == ASPHALT else 0.05), L / n + 0.6, w, yaw)
    mark_line(pts, w, 1)
    path_lines.append((pts, w, row, inside, k, l['tags'].get('name') or '', bridge))
    if not inside and k in ('residential', 'tertiary', 'secondary', 'primary') and not LITE:
        # city streets: 4 m sidewalks on both sides (centred 2.2 m beyond the kerb, +0.06 so they ride above the
        # road) and a yellow centre line on wide (>= 11 m) streets, stopped 3 m short of each end
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            yaw = math.atan2(y1 - y0, x1 - x0)
            if L < 6:
                continue
            for side in (-1, 1):
                plane(PAVE, *l2w((x0 + x1) / 2, (y0 + y1) / 2, yaw, 0, side * (w / 2 + 2.2)), Z0 + 0.06, L, 4.0, yaw)
            if L > 20 and w >= 11:
                box('yellow', (x0 + x1) / 2, (y0 + y1) / 2, Z0 + 0.05, 0.01, L - 6, 0.3, yaw)
st('path_lines', len(path_lines))
# arches and bridges with a mapped outline (man_made=bridge): raised deck, stone abutments, handrails -> a fly-through
# The outline's minimum rectangle gives the deck: L along the carried path, W across. The opening height H is 3.2 m
# for narrow arches, 4 m for wide ones (empirical). The abutments close the two ENDS of the deck, so the passage
# underneath runs across the deck (the way the crossed path really goes); ramps 12 m long lead up to each end.
for l in F['lines']:
    if l['kind'] != 'bridge' or len(l['pts']) < 4 or not in_park(*l['pts'][0]):
        continue
    cx, cy, lx, ly, th = min_rect(l['pts'])
    L, W = (lx, ly) if lx >= ly else (ly, lx)
    th = th if lx >= ly else th + math.pi / 2
    H = 3.2 if W < 8 else 4.0
    name = l['tags'].get('name') or ''
    box('concrete', cx, cy, Z0 + H, 0.5, L, W, th)  # deck: bottom at H, 0.5 m thick
    for sgn in (-1, 1):
        ax, ay = l2w(cx, cy, th, sgn * (L / 2 - 1.0), 0)
        box('brick', ax, ay, Z0, H, 2.0, W, th)  # abutments: the arch opening is between them
        for q in range(int(L // 2)):
            add(HANDRAIL, *l2w(cx, cy, th, -L / 2 + 1 + q * 2, sgn * (W / 2 - 0.3)), Z0 + H + 0.5, 1, 1, 1, th)
        rx, ry = l2w(cx, cy, th, sgn * (L / 2 + 6), 0)
        pitched(
            'grey',
            *l2w(cx, cy, th, sgn * (L / 2 + 12), 0),
            Z0 + 0.05,
            *l2w(cx, cy, th, sgn * L / 2, 0),
            Z0 + H + 0.5,
            W,
        )
    if 'Bow' in name:  # Bow Bridge: a shallow cast-iron arch, 26 m, rises 2.5 m over the water
        # solid 1 m parapets along both long edges instead of the open handrails
        for sgn in (-1, 1):
            box('default', *l2w(cx, cy, th, 0, sgn * (W / 2 - 0.2)), Z0 + H + 0.5, 1.0, L, 0.2, th)
    st('arches')

# ---- 4. the Mall, Bethesda Terrace and Fountain --------------------------------------
# The Mall runs along x = 0 from y = +40 (south end, Literary Walk, just behind the spawn) to y = -330 (north end
# at the Terrace): a 12 m paved walk with four elm rows every 12 m (inner rows at +-8.5 m use the big elm, outer
# rows at +-16.5 m the smaller one), benches at +-6.6 m facing the walk and a lamp pair every 36 m.
MALL_Y0, MALL_Y1 = 40.0, -330.0
plane(PAVE2, 0, (MALL_Y0 + MALL_Y1) / 2, Z0 + 0.06, 12.0, MALL_Y0 - MALL_Y1)
mark_line([(0, MALL_Y0), (0, MALL_Y1)], 12, 1)
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
    for x in (-6.6, 6.6):
        put(BENCH, x, y + 6, 0, 1.0, math.pi / 2 if x < 0 else -math.pi / 2)
        st('benches')
    if (y // 12) % 3 == 0:
        for x in (-7.2, 7.2):
            put(LAMP_SHORT, x, y + 1, 0, 1.0, 0)
            st('lamps')
# every named artwork / memorial node in the park: a 1.6 m grey plinth with the statue mesh at 1.3x on top
for nm, x, y in [
    (p['tags']['name'], p['x'], p['y'])
    for p in F['points']
    if p['kind'] in ('artwork', 'memorial') and p['tags'].get('name') and in_park(p['x'], p['y'])
]:
    box('grey', x, y, Z0, 1.6, 1.4, 1.4)
    put(STATUE, x, y, 1.6, 1.3, rng.uniform(0, 6.28))
    st('statues')
# Bethesda Terrace: Terrace Drive crosses on a 4 m embankment over the arcade; twin stairs drop to the fountain plaza
# The OSM way named 'Bethesda Arcade' gives the arcade axis (ayaw, local u) and centre; the drive runs along it on
# a 16 x 70 m concrete embankment (deck bottom at 4.0 m) with asphalt on top, the arcade passage is the gap between
# the two brick side walls, and the stairs are sloping slabs from the deck edge (u = +-14) down to ground (u = +-26).
ARC = next(l for l in F['lines'] if l['tags'].get('name') == 'Bethesda Arcade')
ax0, ay0 = ARC['pts'][0]
ax1, ay1 = ARC['pts'][-1]
acx, acy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
ayaw = math.atan2(ay1 - ay0, ax1 - ax0)
box('concrete', acx, acy, Z0 + 4.0, 0.6, 16, 70, ayaw)
plane(ASPHALT, acx, acy, Z0 + 4.65, 12, 70, ayaw)
for sgn in (-1, 1):
    box(
        'brick', *l2w(acx, acy, ayaw, sgn * 7.5, 0), Z0, 4.0, 1.0, 70, ayaw
    )  # arcade side walls (16 m wide passage under the drive)
    for u in (-30, -18, 18, 30):
        add(HANDRAIL, *l2w(acx, acy, ayaw, sgn * 7.0, u), Z0 + 4.7, 1, 1, 1, ayaw + math.pi / 2)
    pitched(
        'grey', *l2w(acx, acy, ayaw, sgn * 14, 0), Z0 + 4.6, *l2w(acx, acy, ayaw, sgn * 26, 0), Z0 + 0.05, 8.0
    )  # grand stairs down to the plaza
FX, FY = l2w(acx, acy, ayaw, 0, -48)  # fountain plaza north of the arcade (toward the Lake)
# Bethesda Fountain: 70 x 60 m plaza, a 29 m basin (0.9 m rim), pedestal, upper bowl and stem stacked to 6.4 m,
# water tiles within a 13 m radius just under the rim, the Angel statue at 2.4x on top, 40 onlookers in a 17 m ring
plane(PAVE2, FX, FY, Z0 + 0.06, 70, 60, ayaw)
mark_poly([l2w(FX, FY, ayaw, u, v) for (u, v) in ((-35, -30), (35, -30), (35, 30), (-35, 30))], 3)
cylinder('grey', FX, FY, Z0, 0.9, 29.0)
cylinder('grey', FX, FY, Z0, 3.0, 3.0)
cylinder('grey', FX, FY, Z0 + 3.0, 1.2, 6.0)
cylinder('grey', FX, FY, Z0 + 4.2, 2.2, 1.2)
for j in range(-3, 4):
    for i in range(-3, 4):
        if math.hypot(i * 4, j * 4) < 13:
            add(WATER, FX + i * 4, FY + j * 4, Z0 + 0.75, 1, 1, 1)
put(STATUE, FX, FY, 6.4, 2.4, ayaw + math.pi)
st('bethesda')
for q in range(40):
    a = q / 40 * 6.283
    put(rng.choice(PEOPLE), FX + 17 * math.cos(a), FY + 17 * math.sin(a), 0.06, 1.0, a + math.pi)
# ---- 5. hand-placed landmarks OSM only names ---------------------------------------------
# Positions are WGS84 through ll(); sizes are approximate real dimensions.
OBX, OBY = ll(40.77962, -73.96541)  # Cleopatra's Needle, 21 m, on its granite base
box('black', OBX, OBY, Z0, 2.2, 5, 5)
box('grey', OBX, OBY, Z0 + 2.2, 18.5, 2.4, 2.4)
add(PYRAMID, OBX, OBY, Z0 + 21.7, 2.4, 2.4, 2.0, 0)  # pyramidion: SM_Pyramide is 1 m, centre pivot
plane(PAVE2, OBX, OBY, Z0 + 0.06, 24, 24)
st('obelisk')
# Strawberry Fields: the Imagine mosaic site from the OSM memorial node (fixed coordinates as a fallback); a 24 m
# plaza ringed by 10 benches at 11 m facing inwards. The mosaic decal itself is placed in section 9.
IMX, IMY = next(
    ((p['x'], p['y']) for p in F['points'] if p['tags'].get('name') == 'Strawberry Fields' and p['kind'] == 'memorial'),
    ll(40.77565, -73.97524),
)
plane(PAVE2, IMX, IMY, Z0 + 0.06, 24, 24)
st('imagine')
for q in range(10):
    a = q / 10 * 6.283
    put(BENCH, IMX + 11 * math.cos(a), IMY + 11 * math.sin(a), 0, 1.0, a + math.pi / 2)
TGX, TGY = ll(40.77215, -73.97785)  # Tavern on the Green (OSM has no footprint for it here)
# a 40 x 22 x 7 m brick block on the park grid with a roof slab overhanging 1 m, and a terrace with 10 tables
box('brick', TGX, TGY, Z0, 7.0, 40, 22, pth)
box('concrete', TGX, TGY, Z0 + 7.0, 0.5, 42, 24, pth)
plane(PAVE2, *l2w(TGX, TGY, pth, 0, 18), Z0 + 0.06, 40, 12, pth)
for q in range(10):
    put(TABLE, *l2w(TGX, TGY, pth, -18 + q * 4, 18), 0, 1.0, pth)
    put(CHAIR, *l2w(TGX, TGY, pth, -18 + q * 4, 19.5), 0, 1.0, pth + math.pi)
CHX, CHY = ll(40.77465, -73.97345)  # Cherry Hill fountain and turnaround
plane(PAVE2, CHX, CHY, Z0 + 0.06, 40, 40)
cylinder('grey', CHX, CHY, Z0, 0.8, 7.0)
cylinder('grey', CHX, CHY, Z0, 3.5, 0.8)
st('cherry_hill')
# ---- 6. buildings: park structures and the city ---------------------------------------
# Roof / spire heights (m) of towers around the park that OSM often leaves without a height; matched by name
# substring and used as a floor for the tagged height.
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


def material_for(h, tags, key):
    """Box material ('concrete', 'black', 'grey', 'brick') for a building of height h (m) from its OSM tags.

    `key` (any stable string, the first footprint vertex) is hashed to a 0..1 value so the mix is varied but
    reproducible. Civic / religious / hotel buildings under 90 m read as limestone (concrete); towers >= 150 m are
    70 % black glass, else grey; 60..150 m are 45 % glass, 30 % grey, 25 % concrete; low buildings follow the
    building:colour tag (brick / red / brown -> brick) or split 50/50 brick / concrete. Splits are empirical.
    """
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


facades = []  # (cx, cy, z0, h, lx, ly, th, style, key) of city boxes that may get window decals
bld_count = 0
building_rects = []  # (cx, cy, lx, ly, th, h) of every building box, for the spatial index below
park_x_min, park_x_max = min(q[0] for q in PARK), max(q[0] for q in PARK)


def near_park(x, y):
    """True where a city building is close enough to the park to deserve window decals: the band across the south
    end (y -420..160, within 900 m of the axis), the blocks flanking the park's long sides (within 350 m beyond
    its ~420 m half-width) and the blocks south of it within 700 m of the axis (empirical)."""
    return (-420 < y < 160 and abs(x) < 900) or (y <= 160 and abs(x) - 420 < 350) or (y >= 160 and (abs(x) < 700))


# Height: the OSM height tag (metres, a trailing 'm' tolerated), else building:levels x 3.4 m, raised to the
# SUPERTALL figure when the name matches; with nothing at all 6 m inside the park, 22 m for small city footprints
# and 35 m for large ones. --lite drops small (< 400 m^2) buildings more than 1.9 km from the park's middle.
for p in F['polys']:
    if p['kind'] not in ('building',):
        continue
    pts, tags = p['pts'], p['tags']
    cx, cy = centroid(pts)
    a = poly_area(pts)
    if a < 10 or abs(cx) > BOARD or abs(cy) > BOARD:
        continue
    nm = tags.get('name') or ''
    h = 0.0
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
    if LITE and not inside and math.hypot(cx, cy + 1200) > 1900 and a < 400:
        continue
    kind = material_for(h, tags, str(p['pts'][0]))
    bld_count += 1
    if inside:
        mark_poly(pts, 3)
    if nm == 'Belvedere Castle':  # Vista Rock mound, then the castle and its tower
        # mound: three grey tiers (4 + 4 + 3.5 = 11.5 m) on the castle's rectangle widened by 30 m, scaled 1.0 /
        # 0.8 / 0.62; 30 rock meshes land on whichever tier their fractional distance from the centre falls in
        for k, (sc, hh) in enumerate(((1.0, 4.0), (0.8, 4.0), (0.62, 3.5))):
            rx, ry, lx, ly, th = min_rect(pts)
            box(
                'grey',
                rx,
                ry,
                Z0 + sum(x[1] for x in ((1.0, 4.0), (0.8, 4.0), (0.62, 3.5))[:k]),
                hh,
                (lx + 30) * sc,
                (ly + 30) * sc,
                th,
            )
        rx_, ry_, lx_, ly_, th_ = min_rect(pts)
        for _ in range(30):  # rocks sit on the mound tier they land on
            u, v = rng.uniform(-(lx_ + 30) / 2, (lx_ + 30) / 2), rng.uniform(-(ly_ + 30) / 2, (ly_ + 30) / 2)
            fx_, fy_ = l2w(rx_, ry_, th_, u, v)
            fr_ = max(abs(u) / ((lx_ + 30) / 2), abs(v) / ((ly_ + 30) / 2))
            dz = 11.5 if fr_ <= 0.62 else (8.0 if fr_ <= 0.8 else 4.0)
            put(rng.choice(ROCKS + [CLIFF]), fx_, fy_, dz - 0.3, rng.uniform(1.5, 3.0), rng.uniform(0, 6.28))
        # the castle on top of the mound: 9 m brick massing with a capping slab, a 7 m round tower 20 m tall with
        # a corbelled cap, pyramid roof and 12 merlons, and a 16 m paved terrace on the -u side
        base = Z0 + 11.5
        for rx, ry, lx, ly, th in fill_rects(pts, 6):
            box('brick', rx, ry, base, 9.0, lx, ly, th)
            box('concrete', rx, ry, base + 9.0, 0.5, lx + 0.6, ly + 0.6, th)
        rx, ry, lx, ly, th = min_rect(pts)
        tx, ty = l2w(rx, ry, th, lx * 0.3, 0)
        cylinder('grey', tx, ty, base, 20.0, 7.0)
        cylinder('grey', tx, ty, base + 20, 2.0, 8.0)
        add(PYRAMID, tx, ty, base + 22.0, 7, 7, 6, 0)
        for q in range(12):
            a_ = q / 12 * 6.283
            box('grey', tx + 4.2 * math.cos(a_), ty + 4.2 * math.sin(a_), base + 20.5, 1.2, 1.0, 1.0, a_)
        plane(PAVE2, *l2w(rx, ry, th, -lx * 0.5 - 8, 0), base + 0.06, 16, ly + 10, th)
        st('belvedere')
        continue
    if nm == 'Delacorte Theater':
        # open-air theatre: a 6 m brick wall along the footprint outline and a 1.2 m stage slab
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            box(
                'brick',
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                Z0,
                6.0,
                math.hypot(x1 - x0, y1 - y0),
                0.5,
                math.atan2(y1 - y0, x1 - x0),
            )
        box('concrete', cx, cy, Z0, 1.2, 20, 14, pth)
        st('delacorte')
        continue
    if nm == 'Central Park Carousel':
        # a 16 m drum with a pyramid roof (centre pivot: 7.5 = drum top 5 + half of the 5 m roof) and 12 riders.
        # NB: the `continue` below is inside the riders loop, so the carousel also falls through to the generic
        # box massing further down (kept as is: changing it would change the map).
        cylinder('default', cx, cy, Z0, 5.0, 16.0)
        add(PYRAMID, cx, cy, Z0 + 7.5, 18, 18, 5, 0)
        for q in range(12):
            a_ = q / 12 * 6.283
            put(rng.choice(PEOPLE), cx + 11 * math.cos(a_), cy + 11 * math.sin(a_), 0.05, 1.0, a_ + math.pi)
            st('carousel')
            continue
    if nm == 'Naumburg Bandshell':
        # the half-dome as a 9 m cylinder spanning the outline's long side, on a 1.5 m stage (the ternary is a
        # leftover and always picks 'grey')
        rx, ry, lx, ly, th = min_rect(pts)
        cylinder('concrete' if False else 'grey', cx, cy, Z0, 9.0, max(lx, ly))
        box('concrete', cx, cy, Z0, 1.5, lx + 4, ly + 4, th)
        st('bandshell')
        continue
    # generic massing: up to 10 rectangles for big footprints, 4 for small. City towers of 45..250 m with a side
    # >= 14 m and > 1500 m^2 that are not glass get 1916-zoning setbacks (50 % / 30 % / 20 % of h on 100 / 80 / 60 %
    # footprints); everything else is one box. Window decals (section 6b) only for >= 25 m boxes near the park.
    rects = fill_rects(pts, 10 if a > 400 else 4)
    for rx, ry, lx, ly, th in rects:
        building_rects.append((rx, ry, lx, ly, th, h))
        if h >= 45 and not inside and min(lx, ly) >= 14 and a > 1500 and 'black' != kind and h < 250:
            box(kind, rx, ry, Z0, 0.5 * h, lx, ly, th)
            box(kind, rx, ry, Z0 + 0.5 * h, 0.3 * h, lx * 0.8, ly * 0.8, th)
            box(kind, rx, ry, Z0 + 0.8 * h, 0.2 * h, lx * 0.6, ly * 0.6, th)
        else:
            box(kind, rx, ry, Z0, h, lx, ly, th)
        if h >= 25 and not inside and near_park(rx, ry) and min(lx, ly) >= 6 and WITH_WINDOWS:
            facades.append((rx, ry, Z0, h, lx, ly, th, 'glass' if kind == 'black' else 'punched', str(rx) + str(ry)))
        # roof clutter (not --lite): 30 % of city roofs over 150 m^2 get an elevator bulkhead, 40 % of those a
        # water tower (the farm grain-silo mesh at 0.8-1.1x)
        if h >= 20 and not inside and not LITE and lx * ly > 150 and rng.random() < 0.3:
            box(
                'grey',
                *l2w(rx, ry, th, rng.uniform(-lx / 4, lx / 4), rng.uniform(-ly / 4, ly / 4)),
                Z0 + h,
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
                    Z0 + h,
                    s,
                    s,
                    s,
                    th,
                )
st('buildings', bld_count)
# spatial index: 40 m buckets -> indices of the building rectangles whose bounding circle touches the bucket
rect_index = {}
for i, (rx, ry, lx, ly, th, h) in enumerate(building_rects):
    r = math.hypot(lx, ly) / 2
    for gx in range(int((rx - r) // 40), int((rx + r) // 40) + 1):
        for gy in range(int((ry - r) // 40), int((ry + r) // 40) + 1):
            rect_index.setdefault((gx, gy), []).append(i)


def building_at(x, y, margin=0.5):
    """Index into building_rects of a building box containing (x, y) (grown by `margin` m on each side), or None.

    Only the bucket containing the point is searched, which is enough because every rectangle is registered in all
    the buckets it can reach.
    """
    for i in rect_index.get((int(x // 40), int(y // 40)), ()):
        rx, ry, lx, ly, th, h = building_rects[i]
        c, s = math.cos(th), math.sin(th)
        u = (x - rx) * c + (y - ry) * s
        v = -(x - rx) * s + (y - ry) * c
        if abs(u) <= lx / 2 + margin and abs(v) <= ly / 2 + margin:
            return i
    return None


# window decals on facades facing the park
def window_png(style, cols, rows, path):
    """Render a cols x rows window-grid PNG (48 px per window, transparent background) to `path`.

    'punched': masonry look, each cell a dark window with a light sill line and a pale frame; anything else
    ('glass'): curtain wall, the whole cell glazed blue-grey with a darker spandrel band over the bottom 26 % and
    light mullion lines. `shade` varies per row with a sine so floors do not all look identical. Needs Pillow.
    """
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


# allowed grid sizes: facades snap to the nearest so a bounded set of PNGs is shared by many buildings
COLS_B = [3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32]
ROWS_B = [6, 8, 10, 12, 15, 18, 22, 26, 30, 36, 42, 50, 60, 72, 85, 100]


def nearest(v, b):
    """The value in `b` closest to `v`."""
    return min(b, key=lambda q: abs(q - v))


# One decal per facade: rows from the floor height (3.6 m masonry, 4.0 m glass), columns from the window pitch
# (2.6 m / 1.6 m). A face is skipped when a point 0.8 m outside it lies in a neighbour at least about half as tall
# (party wall) or when neither 60 m nor 200 m along its normal is in the park. The decal sits at the face centre,
# half way up, scale (2.0 depth, h/4, length/4) with the editor's wall basis (decal_rot); the row name is the PNG
# file name, kept unique and stable by the fixed prefix plus the MD5 of the grid key.
for cx, cy, z0, h, lx, ly, th, style, key in facades:
    fl = 3.6 if style == 'punched' else 4.0
    wm = 2.6 if style == 'punched' else 1.6
    rows_n = nearest(h / fl, ROWS_B)
    for fx, fy, length, nyaw, u_edge, v_edge, nu, nv in rect_faces(cx, cy, lx, ly, th):
        px, py = fx + 0.8 * math.cos(nyaw), fy + 0.8 * math.sin(nyaw)
        j = building_at(px, py, 0.0)
        if j is not None and building_rects[j][5] + 1 >= z0 + h * 0.5:
            continue
        if not in_park(fx + 60 * math.cos(nyaw), fy + 60 * math.sin(nyaw)) and not in_park(
            fx + 200 * math.cos(nyaw), fy + 200 * math.sin(nyaw)
        ):
            continue  # only faces that look at the park
        cols_n = nearest(length / wm, COLS_B)
        k = f'{style}_{cols_n}x{rows_n}'
        name = 'decal_1791400000-' + hashlib.md5(k.encode()).hexdigest().upper() + '.png'
        decal_files[name] = ('win', style, cols_n, rows_n)
        add(name, fx, fy, z0 + h / 2, 2.0, h / 4, length / 4, rot=decal_rot(nyaw), store=decal_rows)
        st('win_decals')
# ---- 7. trees: mapped trees, woods, the rest of the park, street trees -----------------
# OSM genus -> editor tree row (first word of genus or species, lower case); plane and linden use the alder mesh
# as the nearest look-alike. Unknown genera get a random TREES row.
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
    """Tree row for an OSM tree node from its genus / species tag (random TREES row when unknown)."""
    g = (tags.get('genus') or tags.get('species') or '').lower().split(' ')[0]
    return GENUS.get(g, rng.choice(TREES))


def tree(x, y, row=None, s=None):
    """Plant one tree at (x, y) unless the cell is path, water or hard (1/2/3); lawns and woods are allowed.

    Random TREES row and 0.85-1.35x scale unless given, random yaw, then the cell is marked 1 so nothing else lands
    on it. Returns True when a tree was placed.
    """
    if occ_at(x, y) in (1, 2, 3):
        return False
    s = s or rng.uniform(0.85, 1.35)
    put(row or rng.choice(TREES), x, y, 0, s, rng.uniform(0, 6.28))
    mark(x, y, 1)
    st('trees')
    return True


# 7a. every mapped tree inside the park at its real position
for p in F['points']:
    if p['kind'] == 'tree' and in_park(p['x'], p['y']):
        tree(p['x'], p['y'], tree_row(p['tags']))
# 7b. woods: one tree per 55 m^2 of each wood polygon (up to 3 tries per tree), bigger species mix, 0.9-1.5x
for p in F['polys']:
    if p['kind'] != 'wood' or not in_park(*centroid(p['pts'])):
        continue
    xs = [q[0] for q in p['pts']]
    ys = [q[1] for q in p['pts']]
    n = int(poly_area(p['pts']) / 55)
    for _ in range(n * 3):
        if n <= 0:
            break
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        if point_in_poly(x, y, p['pts']) and tree(
            x, y, rng.choice(TREES + [OAK, BIG_ELM] + PINES), rng.uniform(0.9, 1.5)
        ):
            n -= 1
# 7c. the rest of the park: one tree per 420 m^2 of free ground (not lawns either), thinned to half next to paths
xs = [q[0] for q in PARK]
ys = [q[1] for q in PARK]
want = int(poly_area(PARK) / 420)
for _ in range(want * 4):
    if want <= 0:
        break
    x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
    if not in_park(x, y) or occ_at(x, y) in (1, 2, 3, 4):
        continue
    if any(occ_at(x + dx, y + dy) == 1 for dx in (-4, 4) for dy in (-4, 4)) and rng.random() < 0.5:
        continue  # fewer trees right on the paths
    if tree(x, y):
        want -= 1
# 7d. mapped street trees outside the park (not --lite), skipped where a building box stands
for p in F['points']:
    if p['kind'] == 'tree' and not in_park(p['x'], p['y']) and not LITE and building_at(p['x'], p['y'], 0.5) is None:
        put(rng.choice(TREES), p['x'], p['y'], 0, rng.uniform(0.8, 1.1), rng.uniform(0, 6.28))
        st('street_trees')
# ---- 8. furniture and people along the paths --------------------------------------------
# Walk each in-park path in ~3 m steps with a running distance `acc`; the side alternates every 25 m. Lamps every
# 25 m at the edge facing the path, benches every 11 m on drives and pedestrian ways (opposite side, facing the
# path), trash cans every 60 m, people every 14 m on drives / 28 m on paths anywhere across the width, cars every
# 45 m on drives in either lane (+-3 m). Bridges get people only. Spacings are empirical.
for pts, w, row, inside, k, nm, bridge in path_lines:
    if not inside:
        continue
    drive = row == ASPHALT and w >= 11
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        yaw = math.atan2(y1 - y0, x1 - x0)
        n = max(1, int(L / 3))
        for q in range(n):
            t = (q + 0.5) / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            acc += L / n
            side = 1 if int(acc / 25) % 2 == 0 else -1
            if acc % 25 < L / n and not bridge:
                put(LAMP_SHORT, *l2w(x, y, yaw, 0, side * (w / 2 + 0.6)), 0, 1.0, yaw + side * math.pi / 2)
                st('lamps')
            if acc % 11 < L / n and (drive or k == 'pedestrian') and not bridge:
                put(
                    BENCH,
                    *l2w(x, y, yaw, 0, -side * (w / 2 + 0.9)),
                    0,
                    1.0,
                    yaw + (math.pi / 2 if side > 0 else -math.pi / 2),
                )
                st('benches')
            if acc % 60 < L / n and not bridge:
                put(TRASH, *l2w(x, y, yaw, 1.5, side * (w / 2 + 0.5)), 0, 1.0, yaw)
            if acc % (14 if drive else 28) < L / n:
                r = rng.random()
                put(
                    rng.choice(PEOPLE),
                    *l2w(x, y, yaw, 0, rng.uniform(-w / 2 + 0.6, w / 2 - 0.6)),
                    0.05,
                    1.0,
                    yaw + (0 if r < 0.5 else math.pi),
                )
                st('people')
            if drive and acc % 45 < L / n and not bridge:
                put(rng.choice(CARS), *l2w(x, y, yaw, 0, rng.choice([-3.0, 3.0])), 0.05, 1.0, yaw)
                st('cars')
# Sheep Meadow fence, playgrounds and entrances
# one low (0.6x) fence piece per 4 m of outline around Sheep Meadow and every in-park playground; 140 people
# lounging on the meadow (sitting and standing figures)
for p in F['polys']:
    nm = p['tags'].get('name') or ''
    if nm == 'Sheep Meadow' or (p['kind'] == 'plaza' and 'Playground' in nm and in_park(*centroid(p['pts']))):
        for (x0, y0), (x1, y1) in zip(p['pts'], p['pts'][1:] + p['pts'][:1]):
            L = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(L // 4))
            yaw = math.atan2(y1 - y0, x1 - x0)
            for q in range(n):
                t = (q + 0.5) / n
                add(FENCE, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, Z0, 1, 1, 0.6, yaw)
                st('fences')
        if nm == 'Sheep Meadow':
            cx, cy = centroid(p['pts'])
            xs = [q[0] for q in p['pts']]
            ys = [q[1] for q in p['pts']]
            for _ in range(140):
                x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
                if point_in_poly(x, y, p['pts']):
                    put(rng.choice(PEOPLE_SIT + PEOPLE), x, y, 0.03, 1.0, rng.uniform(0, 6.28))
                    st('people')
# food carts at the mapped ice-cream / fast-food / cafe nodes inside the park, plus the strip within 30 m of
# y = 440 outside it (empirical), wherever no building box stands
for p in F['points']:
    if (
        p['kind'] in ('ice_cream', 'fast_food', 'cafe')
        and (in_park(p['x'], p['y']) or abs(p['y'] - 440) < 30)
        and building_at(p['x'], p['y'], 1.0) is None
    ):
        put(rng.choice([FOOD_CART, FOOD_STALL]), p['x'], p['y'], 0, 1.0, rng.uniform(0, 6.28))
        st('carts')


# ---- 9. Imagine mosaic decal (ground) -----------------------------------------------------
def imagine_png(path):
    """Render the Imagine mosaic as a 512 px PNG: a cream disc with 8 concentric rings, 36 radial lines from a
    quarter radius outwards and the word IMAGINE (Georgia if the macOS font is there, else Pillow's default)
    on a cream band across the middle. Transparent outside the disc. Needs Pillow."""
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
        a = q / 36 * 6.283
        d.line(
            (
                S / 2 + r0 * 0.25 * math.cos(a),
                S / 2 + r0 * 0.25 * math.sin(a),
                S / 2 + r0 * math.cos(a),
                S / 2 + r0 * math.sin(a),
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


# Ground decal: the same basis rule as the walls turned onto the pavement, X = (0, 0, -1) straight down into the
# ground, Y = world +Y, Z = X x Y = world +X; the projection box (depth scale 1.0) is centred 0.5 m up so it
# reaches the plaza surface, and 0.65 x 0.65 (x 4 m) gives a 2.6 m mosaic. Different prefix from the window
# decals so the names cannot collide.
if WITH_WINDOWS:
    name = 'decal_1791400002-' + hashlib.md5(b'imagine').hexdigest().upper() + '.png'
    decal_files[name] = ('imagine',)
    add(
        name,
        IMX,
        IMY,
        Z0 + 0.5,
        1.0,
        0.65,
        0.65,
        rot=quat_from_axes((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
        store=decal_rows,
    )
# ---- output ------------------------------------------------------------------------------
# north_yaw: direction of true north in the local frame (CustomWeather.northyaw), from a point 0.001 deg north of
# the origin. Menu camera: 420 m south of the origin (+Y), 95 m up, yaw -90 (looking along -Y) and pitched down
# at the origin.
north = FR.xy(FRAME['lat0'] + 0.001, FRAME['lon0'])
north_yaw = math.degrees(math.atan2(north[1], north[0]))
cam = (0.0, 420.0, 95.0)
cam_yaw = -90.0
cam_pitch = math.degrees(math.atan2(0 - cam[2], 420))


def thumbnail(path):
    """Top-down 1024 px JPEG of the south 2 km of the map (y -1600..400) from the OSM polygons and in-park paths.

    Screen x = -x (so east is on the right: local +X is west) and screen y grows with local y (south down).
    Kinds are painted in a fixed order so water and buildings end up on top of the park and lawns. Needs Pillow.
    """
    from PIL import Image, ImageDraw

    W = 1024
    img = Image.new('RGB', (W, W), (235, 232, 224))
    d = ImageDraw.Draw(img)
    sc = W / 2000

    def px(x, y):
        """Local metres -> image pixels (x mirrored, window centred on y = -600)."""
        return (W / 2 - x * sc, W / 2 + (y + 600) * sc)

    col = dict(
        water=(120, 170, 230),
        grass=(150, 200, 130),
        wood=(80, 140, 80),
        building=(110, 110, 120),
        plaza=(200, 195, 185),
        rock=(160, 150, 140),
        park=(170, 205, 150),
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


# Map JSON (format in the README): one S_AssetsTransform entry per row with all its transforms; freestyle map
# (Track false in .info) so the empty Race block is ignored and the drone spawns at the board's PlayerStart;
# timeOfDay 16 = late afternoon light, Cloud 0.2 (empirical). Decal rows join only with windows enabled.
rows_all = dict(instances)
rows_all.update(decal_rows if WITH_WINDOWS else {})
map_json = {
    'S_AssetsTransform': [dict(Rname=r, Transform=t, UniqueGroupTag=['None'] * len(t)) for r, t in rows_all.items()],
    'BaseMapRow': 'BaseBoard',
    'WeatherIndex': 0,
    'Race': dict(CheckPoints=[], StartTransform=tf(0, 0, 0, dict(X=0, Y=0, Z=0, W=1)), Laps=1, BestTime=-1, Spoints=[]),
    'CamLoc': tf(cam[0], cam[1], cam[2], quat_pitch_yaw(cam_pitch, cam_yaw)),
    'CustomWeather': dict(timeOfDay=16.0, northyaw=round(north_yaw, 2), Cloud=0.2),
}
info = {
    'BaseMapRow': 'BaseBoard',
    'Name': DISPLAY,
    'CreatorSteamID': STEAM_ID,
    'CreationTimeUnix': int(time.time()),
    'Track': False,
}
# write maps/CentralPark/ fresh, render the decal PNGs into its Decals/ folder and copy them into the editor's two
# decal libraries, draw the thumbnail, then replace the game's copy of the map folder
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
n = sum(len(v) for v in rows_all.values())
print(f'{NAME}: {n} instances, {len(rows_all)} rows, north yaw {north_yaw:.1f} -> {dst}')
print(stats)
print('top rows:', {r: len(v) for r, v in sorted(instances.items(), key=lambda kv: -len(kv[1]))[:14]})
