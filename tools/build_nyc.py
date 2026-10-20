#!/usr/bin/env python3
"""Build and install the NYC map (Midtown Manhattan) for Uncrashed from NYC Open Data.

Purpose
    Turns public GIS data into one Uncrashed map, "New York City - Midtown Manhattan": every building footprint
    becomes box or textured-mesh massing at its real roof height, every street centreline becomes asphalt with
    sidewalks, markings, trees, lamps, traffic and pedestrians, parks and leftover lots are dressed, and FPV
    features (construction skeletons, open parking decks, skybridges, the Park Avenue viaduct) are added. The
    whole 6 km board is used: full detail in the central 2 km square, boxes, roads and parks in the rings beyond
    it, and water tiles wherever the shoreline-clipped tracts show no land. The script runs top to bottom as one
    pipeline (module-level code); the sections are marked with `# ---- ... ----` headers.

Inputs (NYC Open Data Socrata datasets, already saved in data/; see README "Regenerating")
    data/midtown_buildings.json   footprints 5zhs-2jue: the_geom, height_roof (feet), construction_year, bin, name
    data/midtown_streets.json     centrelines inkn-q76z: the_geom, streetwidth (feet), stname_label, trafdir,
                                  rw_type, from/to_level_code
    data/midtown_parks.json       Parks Properties enfh-gkve: multipolygon, signname, typecategory, acres
    data/ring_*.json              the same three datasets for the whole 6 km board (mid and outer rings)
    data/land_tracts.json         shoreline-clipped 2020 census tracts 63ge-mke6 (land mask for the rivers)
    data/catalog.json             DT_MapEditorAssets rows with mesh bounds in cm (metres = values / 100)

Outputs
    maps/NYC/NYC.json, NYC.info, Thumbnail.jpg and Decals/*.png, plus an installed copy under
    ~/Library/Application Support/Uncrashed/<STEAM_ID>/MapEditor/User/NYC/. Decal PNGs are also copied into the
    editor's MapEditor/UserDecals/ and MapEditor/MapDecals/ libraries, which is where it loads user PNGs from
    (they render blank otherwise).

Usage
    python3 tools/build_nyc.py [--no-windows]
    --no-windows leaves the window-grid and billboard decals out. UNCRASHED_STEAM_ID overrides the Steam ID64.
    Takes minutes, needs only the system Python (Pillow for the thumbnail and decal PNGs), and overwrites both
    maps/NYC and the installed map.

Coordinate frame and units
    All placement maths is in METRES with +Z up; add() converts to Unreal CENTIMETRES for the JSON. The origin is
    the 5th Avenue / 38th Street centreline node: a Track:false map spawns at the Empty board's PlayerStart,
    which is the world origin facing yaw -90 deg (-Y). The frame is rotated by FRAME_ROT so that -Y points at
    the Empire State Building; true north then lies at yaw FRAME_ROT (equivalent to 44 deg, stored in
    CustomWeather.northyaw), so +X is roughly north and +Y roughly east. Yaw is math.atan2(y, x): it increases
    from +X towards +Y like a compass bearing, and is in radians everywhere except the two functions that say
    "_deg". Quaternions are UE (X, Y, Z, W); a pure yaw is (0, 0, sin(yaw/2), cos(yaw/2)).

Measured conventions relied on (see .claude/skills/uncrashed-maps/SKILL.md and README)
    - Translation is the actor pivot. SM_Cube and SM_Cylinder are 1 m with a centre pivot; SM_ConcreteFloor01
      (NewRow_303) is 4 x 4 x 0.30 m with the pivot at the TOP (mesh z -0.29..+0.01); SM_ConcreteWall01
      (NewRow_318) is 0.3 x 4 x 4 m with a bottom-centre pivot; the SM_BaseGround_0-1 ground planes are
      4 x 4 x 0.1 m centre pivot; BP_meWater is a 4 m tile 2.1 m deep with the pivot AT THE SURFACE.
    - The editor's PivotPointOffset column is not applied by the game to stored transforms: trust mesh bounds.
    - Wall decals (BP_ME_Decals rows): basis X into the surface, Y world-down, Z = X x Y along the wall;
      Scale3D = (depth, height / 4, width / 4); the row name is the PNG filename.
    - Bp_Grass renders untextured grey on macOS (no Mac material override), so lawns are thin green cubes.
    - The build is deterministic: one seeded random.Random(34) plus md5 hashes of building ids.
"""

import json, math, os, sys, time, hashlib, shutil, random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
STEAM_ID = os.environ.get(
    'UNCRASHED_STEAM_ID', '76561197969360950'
)  # your Steam ID64: the game loads maps from MapEditor/User under it
GAME_USER_MAPS = os.path.expanduser(f'~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User')
rng = random.Random(34)  # fixed seed: the same data always produces the same map

# ---- asset rows -------------------------------------------------------------
# Row names of DT_MapEditorAssets (see data/catalog.json / docs/ASSETS.md). Sizes quoted are the unscaled mesh
# bounds in metres; Scale3D multiplies them.
CUBE = dict(
    default='NewRow_13',
    yellow='NewRow_46',
    blue='NewRow_79',
    red='NewRow_84',
    green='NewRow_268',
    grey='NewRow_256',
    violet='NewRow_378',
    black='NewRow_109',
)  # SM_Cube, 1 m, centre pivot
CYL = dict(default='NewRow_14', grey='NewRow_261', black='NewRow_113', yellow='NewRow_64')  # SM_Cylinder, centre pivot
CONCRETE = 'NewRow_303'  # SM_ConcreteFloor01 4x4x0.30 m, triplanar concrete, pivot at top (z -0.29..+0.01)
BRICK = 'NewRow_318'  # SM_ConcreteWall01 0.3x4x4 m, triplanar brick, pivot at bottom centre
WATER_TOWER = 'NewRow_251'  # SM_GrainSilo_3 (farm silo, 3.2 m dia x 8.7 m); scaled down it reads as a water tower
ELM, MAPLE, SMALL_TREE, BUSH, BUSH2 = 'NewRow_168', 'NewRow_269', 'NewRow_166', 'NewRow_164', 'NewRow_226'
LAMP_TALL, LAMP_SHORT = 'NewRow_3', 'NewRow_20'  # BP_LightsNightME (9.9 m floodlight) / BP_LightsNightME3 (5.4 m lamp)
TRASH_CAN, FOOD_CART, FOOD_STALL, DUMPSTER, CONE, BARRIER = (
    'NewRow_323',
    'NewRow_246',
    'NewRow_247',
    'NewRow_52',
    'NewRow_202',
    'NewRow_100',
)
PALLET, CRATE, BARREL, FUSEBOX, PLANTER, BENCH, CAFE_TABLE, CHAIR, STATUE = (
    'NewRow_54',
    'NewRow_189',
    'NewRow_187',
    'NewRow_350',
    'NewRow_159',
    'NewRow_204',
    'NewRow_208',
    'NewRow_352',
    'NewRow_213',
)
SCAFFOLD = 'NewRow_198'  # SM_Scaffolding24 1.6 x 2.4 x 2.0, pivot at one end, z -0.57..1.41
LED_V = 'NewRow_217'  # LED_SCREEN_VERTICAL 3 x 0.7 x 8 m, pivot bottom centre, screen faces +Y
NEONS = ['NewRow_4', 'NewRow_148', 'NewRow_343']  # pink / orange / blue neon tubes (with light)
# the editor's drone-pilot figures double as pedestrians
PEOPLE_STAND = ['NewRow_252', 'NewRow_255', 'NewRow_801', 'NewRow_802']
PEOPLE_SIT = ['NewRow_254', 'NewRow_800']
# (row, length m, yaw fix deg, weight): Camaro (yellow, the taxi), GT86, old van (mesh is long along Y, hence
# the 90 deg fix), Kangoo. Weights are the relative frequency in traffic and car parks.
CARS = [
    ('NewRow_103', 4.8, 0, 45),
    ('NewRow_257', 4.3, 0, 30),
    ('NewRow_93', 5.7, 90, 15),
    ('NewRow_775', 4.2, 0, 10),
]  # row, length, yaw fix, weight
cat = json.load(open(os.path.join(DATA, 'catalog.json')))


def mesh_info(row, max_stack, flat_roof):
    """Describe a textured building mesh for try_mesh(): (length X m, length Y m, height above the pivot m,
    max_stack, flat_roof). Bounds come from the catalog (cm, origin + extent); the height is origin.z + extent.z
    because these meshes are ground-pivoted. `max_stack` = how many may be stacked vertically; `flat_roof` =
    whether roof clutter may go on top."""
    b = cat[row]['bounds']
    ox, oy, oz = b['origin']
    ex, ey, ez = b['extent']
    return (2 * ex / 100, 2 * ey / 100, (oz + ez) / 100, max_stack, flat_roof)


MESHES = {
    r: mesh_info(r, 3, True) for r in ('NewRow_794', 'NewRow_795', 'NewRow_796', 'NewRow_797')
}  # office blocks A-D
MESHES['NewRow_9'] = mesh_info('NewRow_9', 1, False)  # SM_building_01 brick low-rise (pitched roof details)
MESHES['NewRow_95'] = mesh_info('NewRow_95', 1, False)  # sm_OldWorkshop_01_02

FT = 0.3048  # NYC Open Data heights and street widths are in feet
Z_GROUND = 0.06  # top of the core ground slab (m); everything "on the ground" sits here, 6 cm above the board
Z_WALK = Z_GROUND + 0.15  # top of the sidewalk kerb slabs (m): a 15 cm kerb
MAX_RANGE = 1000.0  # half-size (m) of the board's MapSettings flyable range box; full detail inside it

instances = {}  # row name -> list of Transform dicts (the S_AssetsTransform payload); filled by add()
facades = []  # (cx, cy, z0, h, lx, ly, yaw, style, bin) of plain box tiers that may get window decals
stats = defaultdict(int)  # build counters printed at the end


def quat_yaw(yaw_rad):
    """UE quaternion (X, Y, Z, W) for a pure yaw of `yaw_rad` radians about +Z (Z = sin(yaw/2), W = cos(yaw/2),
    the convention measured on Workshop maps)."""
    return dict(X=0.0, Y=0.0, Z=math.sin(yaw_rad / 2), W=math.cos(yaw_rad / 2))


def quat_pitch_yaw(pitch_deg, yaw_deg):
    """Quaternion for a rotator with the given pitch and yaw in DEGREES and zero roll (Unreal's rotator to
    quaternion formula). Positive pitch tilts the local +X axis upwards; used for ramps and the menu camera."""
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2
    SP, CP, SY, CY = math.sin(P), math.cos(P), math.sin(Y), math.cos(Y)
    return dict(X=SP * SY, Y=-SP * CY, Z=CP * SY, W=CP * CY)


def quat_from_axes(X, Y, Z):
    """Quaternion (X,Y,Z,W) whose rotation maps local axes onto the given orthonormal world vectors.

    X, Y, Z are unit 3-vectors (the columns of the rotation matrix). The four branches are the usual
    matrix-to-quaternion conversion, picking the largest diagonal term to avoid dividing by a small number."""
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
    """Rotation for a wall decal on a facade whose OUTWARD normal has yaw `normal_yaw` (radians).

    Basis as the editor places wall decals (matches Workshop maps and UE's deferred-decal shader, user-confirmed):
    X into the surface (projection direction), Y straight down (texture V), Z = X x Y along the wall (texture U).
    The caller passes Scale3D = (depth, height / 4, width / 4) because the editor's decal size is 4 m. The PNG is
    drawn upright."""
    c, s = math.cos(normal_yaw), math.sin(normal_yaw)
    X = (-c, -s, 0.0)
    Y = (0.0, 0.0, -1.0)
    Z = (s, -c, 0.0)
    return quat_from_axes(X, Y, Z)


def add(row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0, store=None, rot=None):
    """Append one instance of asset `row` to the map.

    x, y, z: the actor PIVOT in metres (converted to cm, rounded to 0.01 cm). sx, sy, sz: Scale3D multipliers of
    the mesh's native size. yaw: radians about +Z; `rot` (a quaternion dict) overrides it. `store` lets the
    decal pass collect into its own dict instead of `instances`."""
    (store if store is not None else instances).setdefault(row, []).append(
        {
            'Rotation': rot if rot else quat_yaw(yaw),
            'Translation': dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)),
            'Scale3D': dict(X=round(sx, 4), Y=round(sy, 4), Z=round(sz, 4)),
        }
    )


def box(kind, cx, cy, z0, h, lx, ly, yaw=0.0):
    """Place a solid box with its BOTTOM at z0 (m): centre (cx, cy), height h, size lx along local X and ly
    along local Y, yaw in radians. `kind` is 'concrete' (textured floor), 'brick' (textured wall) or a CUBE colour.

    Each row has a different pivot, so the translation differs: SM_ConcreteFloor01 is 0.30 m thick with the
    pivot at the TOP (z -0.29..+0.01), so it is scaled to h / 0.30 and the pivot lifted by 0.29 * scale to put the
    bottom at z0; SM_ConcreteWall01 is base-pivoted, so z0 is used as is (scale = size / native 0.3 x 4 x 4 m);
    cubes are centre-pivoted, so the pivot goes to z0 + h / 2. Sizes are clamped to >= 0.1 m (h >= 1 cm)."""
    lx, ly, h = max(lx, 0.1), max(ly, 0.1), max(h, 0.01)
    if kind == 'concrete':
        sz = h / 0.30
        add(CONCRETE, cx, cy, z0 + 0.29 * sz, lx / 4, ly / 4, sz, yaw)
    elif kind == 'brick':
        add(BRICK, cx, cy, z0, lx / 0.3, ly / 4, h / 4, yaw)
    else:
        add(CUBE[kind], cx, cy, z0 + h / 2, lx, ly, h, yaw)


def pitched_slab(kind, x0, y0, z0, x1, y1, z1, width, thick=0.5):
    """Centre-pivot slab (cube rows only) from (x0,y0,z0) to (x1,y1,z1): a ramp.

    The slab's TOP surface runs between the two points (the centre pivot is dropped by thick / 2); `width` is
    across the ramp, `thick` vertical, all in metres. Yaw follows the plan direction and pitch the rise."""
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


def cylinder(kind, cx, cy, z0, h, d):
    """Vertical cylinder (CYL colour `kind`) with its bottom at z0, height h and diameter d (m); centre pivot."""
    add(CYL[kind], cx, cy, z0 + h / 2, d, d, h)


WATER = (
    'NewRow_183'  # BP_meWater_C: SM_BaseGround_Water 4 x 4 m, 2.1 m deep, pivot AT THE SURFACE (mesh z -2.05..+0.05)
)
# SM_BaseGround_0-1 ground planes, 4 x 4 x 0.1 m, centre pivot, triplanar materials (used by many Workshop maps)
ASPHALT, PAVE, PAVE2, DIRT, GRAVEL = 'NewRow_182', 'NewRow_185', 'NewRow_197', 'NewRow_180', 'NewRow_181'


def plane(row, x, y, z_top, lx, ly, yaw=0.0):
    """Textured ground plane (ASPHALT, PAVE, ...) of lx x ly m with its TOP at z_top. The 4 x 4 x 0.1 m plane is
    centre-pivoted, hence the -0.05, and scaled by size / 4 (minimum 0.5 m)."""
    add(row, x, y, z_top - 0.05, max(lx, 0.5) / 4, max(ly, 0.5) / 4, 1.0, yaw)
    stats['planes'] += 1


def lawn(x, y, z_top, lx, ly, yaw=0.0):
    """Lawn of lx x ly m with its top at z_top: a 5 cm green cube. Bp_Grass renders without its texture on macOS
    (wind grass material, no Mac override), so lawns are a plain green surface instead."""
    box('green', x, y, z_top - 0.05, 0.05, lx, ly, yaw)
    stats['lawn'] += 1


def l2w(cx, cy, yaw, u, v):
    """Local to world: point (u, v) in a frame centred at (cx, cy) and rotated by `yaw` (u along the yaw
    direction, v at yaw + 90 deg) -> world (x, y). Used for every "offset along a rectangle / segment"."""
    c, s = math.cos(yaw), math.sin(yaw)
    return cx + u * c - v * s, cy + u * s + v * c


# ---- geometry ---------------------------------------------------------------
# Pure 2-D helpers on lists of (x, y) metres. Rectangles are (cx, cy, lx, ly, th): centre, side lengths and the
# yaw (radians) of the lx side.
def poly_area(pts):
    """Area of a simple polygon (shoelace formula), m^2."""
    return 0.5 * abs(
        sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    )


def centroid(pts):
    """Area-weighted centroid of a polygon; falls back to the vertex mean for degenerate (zero-area) rings."""
    a = cx = cy = 0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if abs(a) < 1e-9:
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return cx / (3 * a), cy / (3 * a)


def convex_hull(pts):
    """Convex hull (Andrew's monotone chain), counter-clockwise, collinear points dropped."""
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        """2-D cross product of oa x ob: > 0 for a left turn."""
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def min_rect(pts):
    """Minimum-area enclosing rectangle -> (cx, cy, lx, ly, th). Rotating calipers: the optimum has a side
    collinear with a hull edge, so every hull edge direction is tried."""
    hull = convex_hull(pts)
    best = None
    for i in range(len(hull)):
        x0, y0 = hull[i]
        x1, y1 = hull[(i + 1) % len(hull)]
        th = math.atan2(y1 - y0, x1 - x0)
        c, s = math.cos(th), math.sin(th)
        us = [p[0] * c + p[1] * s for p in pts]
        vs = [-p[0] * s + p[1] * c for p in pts]
        lx, ly = max(us) - min(us), max(vs) - min(vs)
        if best is None or lx * ly < best[0]:
            cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (lx * ly, cu * c - cv * s, cu * s + cv * c, lx, ly, th)
    return best[1:]


def point_in_poly(x, y, pts):
    """Even-odd ray-casting point-in-polygon test."""
    inside = False
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x0 + (y - y0) * (x1 - x0) / (y1 - y0) > x:
            inside = not inside
    return inside


def largest_rect(grid):
    """Largest all-True axis-aligned rectangle in a boolean grid (rows x cols) -> (row0, col0, height, width),
    or None if the grid is all False. Classic histogram-stack algorithm, O(rows * cols)."""
    R, C = len(grid), len(grid[0])
    hist = [0] * C
    best = (0, None)
    for r in range(R):
        for c in range(C):
            hist[c] = hist[c] + 1 if grid[r][c] else 0
        stack = []
        for c in range(C + 1):
            cur = hist[c] if c < C else 0
            start = c
            while stack and stack[-1][1] > cur:
                s, hgt = stack.pop()
                area = hgt * (c - s)
                if area > best[0]:
                    best = (area, (r - hgt + 1, s, hgt, c - s))
                start = s
            stack.append((start, cur))
    return best[1]


GRID_SNAP = None  # yaw of the Manhattan avenue grid (radians); set once the street graph has been read


def aligned_rect(pts, th):
    """Bounding rectangle of pts in the frame rotated by `th` -> (cx, cy, lx, ly, th)."""
    c, s = math.cos(th), math.sin(th)
    us = [p[0] * c + p[1] * s for p in pts]
    vs = [-p[0] * s + p[1] * c for p in pts]
    cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    return (cu * c - cv * s, cu * s + cv * c, max(us) - min(us), max(vs) - min(vs), th)


def best_rect(pts):
    """Footprint rectangle: the grid-aligned box when it is within 18 % of the minimum-area one (so near-square
    footprints do not come out at odd angles), otherwise the minimum-area rectangle."""
    r = min_rect(pts)
    if GRID_SNAP is None:
        return r
    g = aligned_rect(pts, GRID_SNAP)
    return g if g[2] * g[3] <= 1.18 * r[2] * r[3] else r


def decompose(pts, max_rects=12):
    """Split a building footprint into up to `max_rects` rectangles (cx, cy, lx, ly, th).

    One rectangle when it covers >= 74 % of the polygon (or the footprint is under 7 m wide). Otherwise the
    polygon is rasterised in the rectangle's frame (cell = 2 m, or coarser so there are at most ~40 cells along
    the long side) and greedily covered with the largest free rectangle until 97 % of the cells are covered;
    rectangles under 2 cells are ignored. This keeps L- and U-shaped buildings."""
    area = poly_area(pts)
    cx, cy, lx, ly, th = best_rect(pts)
    if lx * ly <= 0 or area / (lx * ly) >= 0.74 or min(lx, ly) < 7:
        return [(cx, cy, lx, ly, th)]
    c, s = math.cos(th), math.sin(th)
    loc = [((p[0] - cx) * c + (p[1] - cy) * s, -(p[0] - cx) * s + (p[1] - cy) * c) for p in pts]
    cell = max(2.0, max(lx, ly) / 40)
    nu, nv = max(1, int(math.ceil(lx / cell))), max(1, int(math.ceil(ly / cell)))
    grid = [
        [point_in_poly(-lx / 2 + (i + 0.5) * cell, -ly / 2 + (j + 0.5) * cell, loc) for i in range(nu)]
        for j in range(nv)
    ]
    total = sum(sum(r) for r in grid)
    out = []
    covered = 0
    while len(out) < max_rects and total - covered > 0.03 * total:
        rect = largest_rect(grid)
        if not rect or rect[2] * rect[3] < 2:
            break
        r0, c0, hh, ww = rect
        for r in range(r0, r0 + hh):
            for cc in range(c0, c0 + ww):
                grid[r][cc] = False
        covered += hh * ww
        u = -lx / 2 + (c0 + ww / 2) * cell
        v = -ly / 2 + (r0 + hh / 2) * cell
        out.append((*l2w(cx, cy, th, u, v), ww * cell, hh * cell, th))
    return out or [(cx, cy, lx, ly, th)]


def clip_to_square(pts, half):
    """Sutherland-Hodgman clip of a polygon to the axis-aligned square [-half, half]^2. Returns [] when fewer
    than three vertices survive (used for park polygons that cross the board edge, e.g. Central Park)."""

    def clip(poly, inside, intersect):
        """Clip `poly` against one half-plane given by an `inside` test and an edge `intersect` function."""
        out = []
        for i in range(len(poly)):
            cur, prev = poly[i], poly[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(intersect(prev, cur))
        return out

    def ix(p, q, axis, val):
        """Point where segment p-q crosses the line `axis` = val."""
        t = (val - p[axis]) / (q[axis] - p[axis])
        return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))

    poly = pts
    for axis, val, keep in ((0, -half, 1), (0, half, -1), (1, -half, 1), (1, half, -1)):
        if len(poly) < 3:
            return []
        poly = clip(poly, lambda p: (p[axis] - val) * keep >= 0, lambda p, q: ix(p, q, axis, val))
    return poly if len(poly) >= 3 else []


def rect_faces(cx, cy, lx, ly, th):
    """4 facades: (fx, fy, length, normal_yaw, u_edge, v_edge, nu, nv).

    (fx, fy) is the face midpoint, `length` its width, `normal_yaw` the yaw (radians) of its OUTWARD normal,
    (u_edge, v_edge) the midpoint in the rectangle's local frame and (nu, nv) the outward normal there."""
    out = []
    for u, v, L, nu, nv in (
        (0, ly / 2, lx, 0, 1),
        (0, -ly / 2, lx, 0, -1),
        (lx / 2, 0, ly, 1, 0),
        (-lx / 2, 0, ly, -1, 0),
    ):
        fx, fy = l2w(cx, cy, th, u, v)
        out.append((fx, fy, L, th + math.atan2(nv, nu), u, v, nu, nv))
    return out


# ---- data & frame -----------------------------------------------------------
# Socrata GeoJSON: coordinates are [lon, lat]. The three landmark BINs (NYC Building Identification Numbers)
# get hand-tuned massing instead of the generic rules.
buildings = json.load(open(os.path.join(DATA, 'midtown_buildings.json')))
streets = json.load(open(os.path.join(DATA, 'midtown_streets.json')))
ESB_BIN, CHRYSLER_BIN, ONE_VANDERBILT_BIN = '1015862', '1036156', '1090825'


def rings(b):
    """Outer rings (lists of [lon, lat]) of a building's the_geom, Polygon or MultiPolygon; holes are ignored."""
    g = b['the_geom']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    return [p[0] for p in polys]


# Frame: origin at the 5 Ave / 38 St centreline node, rotated so the Empire State Building (vertex mean of its
# footprint) lies exactly on -Y, the direction the drone faces at spawn.
esb = next(b for b in buildings if b['bin'] == ESB_BIN)
esb_lon = sum(c[0] for c in rings(esb)[0]) / len(rings(esb)[0])
esb_lat = sum(c[1] for c in rings(esb)[0]) / len(rings(esb)[0])
NODES_LL = {}  # (lon, lat) rounded to 1e-6 -> set of street names meeting at that centreline end node
for s_ in streets:
    n = s_.get('stname_label', '')
    for line in s_['the_geom']['coordinates']:
        for p in (line[0], line[-1]):
            NODES_LL.setdefault((round(p[0], 6), round(p[1], 6)), set()).add(n)


def node_of(a, b):
    """(lon, lat) of the first centreline node where street `a` meets a street whose label ends with `b`
    (e.g. node_of('5 AVE', '38 ST')). Raises StopIteration if there is none."""
    return next(k for k, v in NODES_LL.items() if a in v and any(x.endswith(b) for x in v))


lon0, lat0 = node_of('5 AVE', '38 ST')  # spawn: 5th Avenue & 38th Street
# equirectangular projection: metres per degree of latitude / longitude at the origin (good enough over 3 km)
KLAT = 111320.0
KLON = 111320.0 * math.cos(math.radians(lat0))
# atan2(east, north) is the compass bearing of the ESB from the spawn; rotating by -90 deg minus that bearing
# puts the ESB at yaw -90 deg, i.e. on -Y. True north ends up at yaw FRAME_ROT.
FRAME_ROT = math.radians(-90) - math.atan2((esb_lon - lon0) * KLON, (esb_lat - lat0) * KLAT)


def proj(lon, lat):
    """Project (lon, lat) to map metres (x, y): local north/east offsets from the origin rotated by FRAME_ROT."""
    n, e = (lat - lat0) * KLAT, (lon - lon0) * KLON
    c, s_ = math.cos(FRAME_ROT), math.sin(FRAME_ROT)
    return (n * c - e * s_, n * s_ + e * c)


def in_range(x, y, margin=0.0):
    """True inside the central 2 km square shrunk by `margin` m (a negative margin enlarges it)."""
    return abs(x) <= MAX_RANGE - margin and abs(y) <= MAX_RANGE - margin


# landmark positions used later: Herald Square, the Times Square bowtie nodes (Broadway 42nd..47th), Duffy
# Square (47th) and the latitudes bounding the two Broadway pedestrian plazas
esb_x, esb_y = proj(esb_lon, esb_lat)
herald = proj(*node_of('BROADWAY', '34 ST'))
ts_nodes = [proj(*node_of('BROADWAY', f'{n} ST')) for n in (42, 43, 44, 45, 46, 47)]
duffy = proj(*node_of('BROADWAY', '47 ST'))
ts42 = proj(*node_of('BROADWAY', '42 ST'))
lat_42, lat_47 = node_of('BROADWAY', '42 ST')[1], node_of('BROADWAY', '47 ST')[1]
lat_33, lat_35 = node_of('BROADWAY', '33 ST')[1], node_of('BROADWAY', '35 ST')[1]


def dist_to_polyline(px, py, pts):
    """Distance from (px, py) to a polyline and the nearest point on it -> (d, (qx, qy))."""
    best = 1e9
    bp = None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        t = max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
        qx, qy = x0 + t * dx, y0 + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < best:
            best, bp = d, (qx, qy)
    return best, bp


# ---- streets graph ----------------------------------------------------------
# Every at-grade centreline becomes straight segments between consecutive vertices. Kept: level codes 13 (at
# grade; elevated codes are handled in the viaduct section) and rw_type 1 / 9 / missing (other roadway types
# are dropped). Width is `streetwidth` feet -> m, default 32 ft, clamped 6..26 m. node_w / node_deg record the
# widest street and the number of line ends at each node for intersection trimming later. `plaza` marks the
# Broadway blocks that are pedestrian plazas (42nd-47th: Times Square, 33rd-35th: Herald Square).
segments = []  # dicts: p0, p1 (m), w, name, ave, plaza, trafdir, L, yaw, k0, k1 (node keys), first, last
node_w = {}  # node key -> widest street meeting there (m)
node_deg = defaultdict(int)  # node key -> number of centreline ends meeting there
for s in streets:
    if s.get('from_level_code') not in (None, '13') or s.get('to_level_code') not in (None, '13'):
        continue
    if s.get('rw_type') not in ('1', '9', None):
        continue
    w = min(max(float(s.get('streetwidth') or 32) * FT, 6.0), 26.0)
    name = s.get('stname_label', '')
    ave = 'AVE' in name or 'BROADWAY' in name
    g = s['the_geom']
    lines = g['coordinates'] if g['type'] == 'MultiLineString' else [g['coordinates']]
    for line in lines:
        for k in (line[0], line[-1]):
            key = (round(k[0], 6), round(k[1], 6))
            node_w[key] = max(node_w.get(key, 0), w)
            node_deg[key] += 1
        pts = [proj(lon, lat) for lon, lat in line]
        midlat = (line[0][1] + line[-1][1]) / 2
        plaza = name == 'BROADWAY' and (
            lat_42 - 1e-4 < midlat < lat_47 + 1e-4 or lat_33 - 1e-4 < midlat < lat_35 + 1e-4
        )
        for i, ((x0, y0), (x1, y1)) in enumerate(zip(pts, pts[1:])):
            L = math.hypot(x1 - x0, y1 - y0)
            if L < 1 or not in_range((x0 + x1) / 2, (y0 + y1) / 2, -w):
                continue
            segments.append(
                dict(
                    p0=(x0, y0),
                    p1=(x1, y1),
                    w=w,
                    name=name,
                    ave=ave,
                    plaza=plaza,
                    trafdir=s.get('trafdir'),
                    L=L,
                    yaw=math.atan2(y1 - y0, x1 - x0),
                    k0=(round(line[i][0], 6), round(line[i][1], 6)),
                    k1=(round(line[i + 1][0], 6), round(line[i + 1][1], 6)),
                    first=i == 0,
                    last=i == len(pts) - 2,
                )
            )


def seg_mid(sg):
    """Midpoint (m) of a segment."""
    return ((sg['p0'][0] + sg['p1'][0]) / 2, (sg['p0'][1] + sg['p1'][1]) / 2)


def along(sg, u, v):
    """Segment-local offset -> world: u along the segment from its midpoint, v sideways (yaw + 90 deg)."""
    mx, my = seg_mid(sg)
    return l2w(mx, my, sg['yaw'], u, v)


def dist_point_seg(px, py, sg):
    """Distance (m) from a point to a segment's centreline."""
    (x0, y0), (x1, y1) = sg['p0'], sg['p1']
    dx, dy = x1 - x0, y1 - y0
    t = max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


# 50 m bucket index of segments (each registered in its bounding cells plus one cell of padding)
seg_index = defaultdict(list)
for i, sg in enumerate(segments):
    (x0, y0), (x1, y1) = sg['p0'], sg['p1']
    for gx in range(int(min(x0, x1) // 50) - 1, int(max(x0, x1) // 50) + 2):
        for gy in range(int(min(y0, y1) // 50) - 1, int(max(y0, y1) // 50) + 2):
            seg_index[(gx, gy)].append(i)


def road_nearby(px, py, maxd):
    """True if a road surface comes within `maxd` m of the point (distance to the kerb line, i.e. centreline
    distance minus half the width). A NEGATIVE maxd asks whether the point lies that far INSIDE a carriageway,
    which is how props are kept off the road. Only the point's own 50 m bucket is searched."""
    for i in seg_index.get((int(px // 50), int(py // 50)), ()):
        sg = segments[i]
        if dist_point_seg(px, py, sg) <= maxd + sg['w'] / 2:
            return True
    return False


# ---- buildings ---------------------------------------------------------------
# Street-grid yaw = circular mean of the avenue segment directions (Broadway runs diagonally and is excluded).
# Angles are doubled before averaging because a segment direction is only defined modulo 180 deg.
_ave = [sg['yaw'] for sg in segments if sg['ave'] and 'BROADWAY' not in sg['name']]
GRID_SNAP = math.atan2(sum(math.sin(2 * y) for y in _ave), sum(math.cos(2 * y) for y in _ave)) / 2


def material_for(h, year, key):
    """Box material from roof height h (m) and construction year: triplanar brick for low pre-war buildings,
    triplanar concrete for pre-war towers (reads as limestone), grey for post-war mid-rise and black for post-war
    glass towers. `key` (the BIN) seeds a stable per-building hash so the mix is varied but reproducible."""
    hv = int(hashlib.md5(key.encode()).hexdigest()[:4], 16) / 65535
    modern = year >= 1950
    if h >= 150:
        return 'black' if modern else 'concrete'
    if h >= 60:
        return ('black' if hv < 0.6 else 'grey') if modern else 'concrete'
    if h >= 25:
        return ('grey' if hv < 0.7 else 'black') if modern else ('concrete' if hv < 0.55 else 'brick')
    return 'brick' if (not modern or hv < 0.5) else 'grey'


def try_mesh(lx, ly, h):
    """Find a textured building mesh and an nx x ny x nz grid of it that fills an lx x ly x h m rectangle with
    at most ~30 % non-uniform stretch (per-axis scale 0.7..1.45, vertical 0.75..1.45). Returns
    (row, nx, ny, nz, sx, sy, sz, swap) or None. Single-storey rows (max_stack 1) must match the height within
    0.7..1.4 outright. Cost = total |log scale| + 0.04 per extra tile, so fewer, less-stretched tiles win."""
    best = None
    for row, (mx, my, mh, max_stack, flat) in MESHES.items():
        if max_stack == 1 and not (0.7 <= h / mh <= 1.4):
            continue
        for swap in (False, True):
            ax, ay = (my, mx) if swap else (mx, my)
            nx, ny = max(1, round(lx / ax)), max(1, round(ly / ay))
            sx, sy = lx / (nx * ax), ly / (ny * ay)
            if not (0.7 <= sx <= 1.45 and 0.7 <= sy <= 1.45):
                continue
            nz = max(1, min(max_stack, round(h / mh)))
            sz = h / (nz * mh)
            if not (0.75 <= sz <= 1.45):
                continue
            cost = abs(math.log(sx)) + abs(math.log(sy)) + abs(math.log(sz)) + 0.04 * (nx * ny * nz - 1)
            if best is None or cost < best[0]:
                best = (cost, row, nx, ny, nz, sx, sy, sz, swap)
    return best[1:] if best else None


def place_mesh(fit, cx, cy, lx, ly, th):
    """Place the try_mesh() grid: tiles centred in an nx x ny lattice over the rectangle, stacked nz high (the
    meshes are ground-pivoted, so each storey sits at k * mh * sz). `swap` rotates the mesh 90 deg."""
    row, nx, ny, nz, sx, sy, sz, swap = fit
    mx, my, mh, _, _ = MESHES[row]
    yaw = th + (math.pi / 2 if swap else 0)
    for i in range(nx):
        for j in range(ny):
            x, y = l2w(cx, cy, th, -lx / 2 + (i + 0.5) * lx / nx, -ly / 2 + (j + 0.5) * ly / ny)
            for k in range(nz):
                add(row, x, y, Z_GROUND + k * mh * sz, sx, sy, sz, yaw)
                stats['mesh_tiles'] += 1


box_faces = []  # (cx, cy, lx, ly, th, h_tier, kind) of ground-level box tiers: real flat facades for signage


def tier(kind, cx, cy, z0, h, lx, ly, th, style=None, key=''):
    """One box tier of a building (bottom z0, height h, m). Ground-level tiers are recorded in `box_faces` (the
    only true flat facades, used for signage and skybridges); tiers at least 30 m tall and 6 m wide with a window
    `style` ('punched' or 'glass') are recorded in `facades` for the decal pass."""
    box(kind, cx, cy, z0, h, lx, ly, th)
    stats['boxes'] += 1
    if abs(z0 - Z_GROUND) < 0.01:
        box_faces.append((cx, cy, lx, ly, th, h, kind))
    if style and h >= 30 and min(lx, ly) >= 6:
        facades.append((cx, cy, z0, h, lx, ly, th, style, key))


def rooftop(cx, cy, ztop, lx, ly, th, kind, key, flat=True):
    """New York roof clutter on a flat roof at ztop (m): a 0.9 m parapet wall on masonry (brick / concrete)
    roofs at least 8 m wide, a wooden-style water tower (36 % of roofs >= 150 m^2 below 130 m, the silo at
    0.75..1.1 scale) and one or two elevator bulkheads on roofs >= 90 m^2. Nothing on roofs under 6 m or on
    pitched meshes (`flat` False). `key` seeds the hash; placement inside the parapet uses the shared rng."""
    if not flat or ztop - Z_GROUND < 6:
        return
    hv = int(hashlib.md5((key + 'roof').encode()).hexdigest()[:6], 16) / 0xFFFFFF
    area = lx * ly
    if kind in ('brick', 'concrete') and min(lx, ly) >= 8:
        t = 0.35
        for u, v, L, W in (
            (0, ly / 2 - t / 2, lx, t),
            (0, -ly / 2 + t / 2, lx, t),
            (lx / 2 - t / 2, 0, t, ly - 2 * t),
            (-lx / 2 + t / 2, 0, t, ly - 2 * t),
        ):
            x, y = l2w(cx, cy, th, u, v)
            box(kind, x, y, ztop, 0.9, L, W, th)
            stats['parapet'] += 1
        inset = 1.6
    else:
        inset = 2.5
    if area >= 150 and ztop < 130 and hv < 0.36:
        s = 0.75 + 0.35 * hv
        u = rng.uniform(-lx / 2 + inset + 1.8 * s, lx / 2 - inset - 1.8 * s)
        v = rng.uniform(-ly / 2 + inset + 1.8 * s, ly / 2 - inset - 1.8 * s)
        x, y = l2w(cx, cy, th, u, v)
        add(WATER_TOWER, x, y, ztop, s, s, s, th + rng.uniform(0, 6.28))
        stats['roof'] += 1
    if area >= 90:
        for _ in range(1 if area < 400 else 2):
            bw, bl, bh = (
                rng.uniform(2.5, min(6, lx - 2 * inset)),
                rng.uniform(2.5, min(8, ly - 2 * inset)),
                rng.uniform(2.6, 4.2),
            )
            if bw < 2 or bl < 2:
                break
            u = rng.uniform(-lx / 2 + inset + bw / 2, lx / 2 - inset - bw / 2)
            v = rng.uniform(-ly / 2 + inset + bl / 2, ly / 2 - inset - bl / 2)
            x, y = l2w(cx, cy, th, u, v)
            box('grey' if hv > 0.5 else 'concrete', x, y, ztop, bh, bw, bl, th)
            stats['roof'] += 1


def stepped(ring, steps, kind, style, key, crown=None):
    """Hand-tuned stepped massing for a landmark: `steps` = [(top z m, x fraction, y fraction), ...] of the
    footprint's minimum rectangle stacked bottom-up, `crown` = [(top z m, diameter m, CYL colour), ...]
    cylinders on top (spires, antennas). Returns the (cx, cy, lx, ly, th, h, kind) building_rects entry, with h
    the top of the last step (the crown is not counted)."""
    cx, cy, lx, ly, th = min_rect(ring)
    z = 0.0
    for ztop, fx, fy in steps:
        tier(kind, cx, cy, Z_GROUND + z, ztop - z, lx * fx, ly * fy, th, style, key)
        z = ztop
    if crown:
        for ztop, d, k in crown:
            cylinder(k, cx, cy, Z_GROUND + z, ztop - z, d)
            z = ztop
    return (cx, cy, lx, ly, th, steps[-1][0], kind)


# Main building pass. For each footprint ring inside the core: landmarks get stepped() massing; otherwise
# decompose() into rectangles, tile each with textured meshes when try_mesh() fits (only unnamed buildings up to
# 60 m: named ones are landmarks that keep stone box massing), else a plain box with material_for(). Pre-1960
# towers of 45..250 m get three "wedding cake" setback tiers (the 1916 zoning look), everything gets rooftop().
building_rects = []  # (cx, cy, lx, ly, th, h, kind): every building rectangle, for collision and void tests
all_pts = []  # every projected footprint vertex, for the core ground-slab extent
for b in buildings:
    h = float(b.get('height_roof') or 0) * FT
    year = int(float(b.get('construction_year') or 0) or 0)
    for ring in rings(b):
        pts = [proj(lon, lat) for lon, lat in ring[:-1]]
        if len(pts) < 3 or poly_area(pts) < 12:
            stats['skipped'] += 1
            continue
        if h < 2.5:
            h = 4.0 if poly_area(pts) < 600 else 10.0  # heightless footprints: kiosks and sheds
        ccx, ccy = centroid(pts)
        if not in_range(ccx, ccy):
            stats['skipped'] += 1
            continue
        all_pts += pts
        stats['buildings'] += 1
        # Empire State Building: 381 m roof, antenna to 443 m; Chrysler: spire to 319 m; One Vanderbilt: 427 m
        if b['bin'] == ESB_BIN:
            building_rects.append(
                stepped(
                    pts,
                    [(20, 1.0, 1.0), (110, 0.85, 0.82), (290, 0.60, 0.56), (320, 0.42, 0.42), (335, 0.26, 0.26)],
                    'concrete',
                    'punched',
                    b['bin'],
                    crown=[(381, 17, 'grey'), (443, 3, 'black')],
                )
            )
            continue
        if b['bin'] == CHRYSLER_BIN:
            building_rects.append(
                stepped(
                    pts,
                    [
                        (40, 1.0, 1.0),
                        (200, 0.78, 0.78),
                        (240, 0.62, 0.62),
                        (255, 0.52, 0.52),
                        (266, 0.42, 0.42),
                        (276, 0.32, 0.32),
                        (284, 0.22, 0.22),
                    ],
                    'concrete',
                    'punched',
                    b['bin'],
                    crown=[(300, 5, 'grey'), (319, 1.5, 'grey')],
                )
            )
            continue
        if b['bin'] == ONE_VANDERBILT_BIN:
            building_rects.append(
                stepped(pts, [(300, 1.0, 1.0), (380, 0.72, 0.72), (427, 0.45, 0.45)], 'black', 'glass', b['bin'])
            )
            continue
        kind = material_for(h, year, b['bin'])
        if b.get('name') and kind in ('grey', 'black') and year and year < 1950:
            kind = 'concrete'  # named pre-war buildings (NYPL, hotels, churches) are stone, never glass
        for cx, cy, lx, ly, th in decompose(pts):
            building_rects.append((cx, cy, lx, ly, th, h, kind))
            fit = (
                try_mesh(lx, ly, h) if (h <= 60 and not b.get('name')) else None
            )  # named buildings (landmarks) keep stone massing
            if fit:
                place_mesh(fit, cx, cy, lx, ly, th)
                mh = MESHES[fit[0]][2]
                rooftop(
                    cx,
                    cy,
                    Z_GROUND + fit[3] * mh * fit[6],
                    lx * 0.98,
                    ly * 0.98,
                    th,
                    'mesh',
                    b['bin'] + str(cx),
                    MESHES[fit[0]][4],
                )
                continue
            style = 'glass' if kind == 'black' else ('punched' if kind in ('concrete', 'brick') else 'glass')
            # setbacks: 45 % of h at full size, 30 % at 82 % footprint, 25 % at 64 % (empirical proportions)
            if 45 <= h <= 250 and year and year < 1960 and min(lx, ly) >= 14:
                tier(kind, cx, cy, Z_GROUND, 0.45 * h, lx, ly, th, style, b['bin'])
                tier(kind, cx, cy, Z_GROUND + 0.45 * h, 0.30 * h, lx * 0.82, ly * 0.82, th, style, b['bin'])
                tier(kind, cx, cy, Z_GROUND + 0.75 * h, 0.25 * h, lx * 0.64, ly * 0.64, th, style, b['bin'])
                rooftop(cx, cy, Z_GROUND + h, lx * 0.64, ly * 0.64, th, kind, b['bin'] + str(cx))
            else:
                tier(kind, cx, cy, Z_GROUND, h, lx, ly, th, style, b['bin'])
                rooftop(cx, cy, Z_GROUND + h, lx, ly, th, kind, b['bin'] + str(cx))

# spatial index of building rects: 40 m buckets, each rect registered in every bucket its bounding circle touches
rect_index = defaultdict(list)
for i, (cx, cy, lx, ly, th, h, kind) in enumerate(building_rects):
    r = math.hypot(lx, ly) / 2
    for gx in range(int((cx - r) // 40), int((cx + r) // 40) + 1):
        for gy in range(int((cy - r) // 40), int((cy + r) // 40) + 1):
            rect_index[(gx, gy)].append(i)


def building_at(x, y, margin=0.5):
    """Index into building_rects of a rectangle containing (x, y) (grown by `margin` m on each side), or None.
    Oriented test in the rectangle's own frame."""
    for i in rect_index.get((int(x // 40), int(y // 40)), ()):
        cx, cy, lx, ly, th, h, kind = building_rects[i]
        c, s = math.cos(th), math.sin(th)
        u = (x - cx) * c + (y - cy) * s
        v = -(x - cx) * s + (y - cy) * c
        if abs(u) <= lx / 2 + margin and abs(v) <= ly / 2 + margin:
            return i
    return None


def inside_building(x, y, margin=0.5):
    """True if (x, y) is inside any building rectangle grown by `margin` m. The main "do not place here" test."""
    return building_at(x, y, margin) is not None


# ---- ground, roads, sidewalks -----------------------------------------------
# Core ground slab: a 0.30 m concrete slab with its top at Z_GROUND under the built-up extent (+60 m, clamped to
# 1040 m so it reaches just past the flyable square). The whole-board slab comes later, 1 cm lower.
xs = [p[0] for p in all_pts]
ys = [p[1] for p in all_pts]
gx0, gx1, gy0, gy1 = (
    max(min(xs) - 60, -1040),
    min(max(xs) + 60, 1040),
    max(min(ys) - 60, -1040),
    min(max(ys) + 60, 1040),
)
box('concrete', (gx0 + gx1) / 2, (gy0 + gy1) / 2, Z_GROUND - 0.30, 0.30, gx1 - gx0, gy1 - gy0)


def walk_width(sg, side, off, Lw):
    """Sidewalk width that reaches the building line (median over samples), clamped 3..14 m.

    Five sample points along the usable length Lw (centred at offset `off`) step outwards from the kerb in 0.5 m
    steps until they hit a building (14 m if none); the median plus 0.3 m overlap is the width for that side."""
    ds = []
    for t in (0.15, 0.35, 0.5, 0.65, 0.85):
        u = off - Lw / 2 + t * Lw
        for d in range(1, 29):
            x, y = along(sg, u, side * (sg['w'] / 2 + d * 0.5))
            if inside_building(x, y, 0.0):
                ds.append(d * 0.5)
                break
        else:
            ds.append(14.0)
    ds.sort()
    med = ds[len(ds) // 2]
    return max(3.0, min(14.0, med + 0.3))


# Road surfaces and sidewalks per segment. Plaza blocks are raised to sidewalk level and paved. Ordinary roads
# are asphalt planes whose top (`ztop`) is staggered Broadway 3.5 cm > avenues 3 cm > cross streets 2 cm above
# Z_GROUND so overlapping surfaces at intersections never z-fight. The asphalt of the first/last segment of a
# line is extended by half the widest street at the node (ext0/ext1) to fill the intersection; sidewalks are
# instead CUT back by the same amount (cut0/cut1) so they stop at the kerb line of the crossing street.
for sg in segments:
    (x0, y0), (x1, y1), w, L, yaw = sg['p0'], sg['p1'], sg['w'], sg['L'], sg['yaw']
    mx, my = seg_mid(sg)
    if sg['plaza']:
        sg['ztop'] = Z_WALK + 0.02
        box('concrete', mx, my, Z_GROUND, Z_WALK - Z_GROUND, L + w * 0.5, w, yaw)
        plane(PAVE2, mx, my, Z_WALK + 0.02, L + w * 0.5, w, yaw)
        stats['plaza_seg'] += 1
    else:
        sg['ztop'] = Z_GROUND + (0.035 if 'BROADWAY' in sg['name'] else 0.03 if sg['ave'] else 0.02)
        ext0 = node_w.get(sg['k0'], w) / 2 if (sg['first'] and node_deg.get(sg['k0'], 0) >= 2) else 0
        ext1 = node_w.get(sg['k1'], w) / 2 if (sg['last'] and node_deg.get(sg['k1'], 0) >= 2) else 0
        bx_, by_ = along(sg, (ext1 - ext0) / 2, 0)
        plane(ASPHALT, bx_, by_, sg['ztop'], L + ext0 + ext1, w, yaw)
        stats['roads'] += 1
        if sg['trafdir'] == 'TW' and L > 20:
            box('yellow', mx, my, sg['ztop'], 0.01, L - w * 0.9, 0.35, yaw)  # two-way streets: yellow centre line
    cut0 = node_w.get(sg['k0'], w) / 2 if sg['first'] else 0
    cut1 = node_w.get(sg['k1'], w) / 2 if sg['last'] else 0
    Lw = L - cut0 - cut1
    if Lw > 2:
        off = (cut0 - cut1) / 2
        zt = Z_WALK + (0.01 if sg['ave'] else 0.0)  # avenue pavements 1 cm higher: same z-fighting trick
        sg['walk'] = {}  # side (+1 / -1) -> (off, Lw, sw, zt): reused by every later street pass
        for side in (1, -1):
            sw = walk_width(sg, side, off, Lw)
            x, y = along(sg, off, side * (w / 2 + sw / 2))
            box('concrete', x, y, Z_GROUND, zt - 0.02 - Z_GROUND, Lw, sw, yaw)
            plane(PAVE, x, y, zt, Lw, sw, yaw)
            stats['sidewalks'] += 1
            sg['walk'][side] = (off, Lw, sw, zt)

# ---- road markings ----------------------------------------------------------
# Lane lines (1 cm thick white boxes, one per 3.4 m lane, stopping 4 m short of each end) and ladder crosswalks
# (2.8 x 0.55 m bars every 2.4 m) at the ends that meet a real intersection (node degree >= 3), 2.2 m back from
# the crossing street's kerb line.
WHITE = CUBE['default']
for sg in segments:
    if sg['plaza'] or 'walk' not in sg:
        continue
    off, Lw, sw, zt = sg['walk'][1]
    w = sg['w']
    zt_road = sg['ztop']
    lanes = max(1, round(w / 3.4))
    if lanes >= 2 and Lw > 12:
        for k in range(1, lanes):
            x, y = along(sg, off, -w / 2 + k * w / lanes)
            box('default', x, y, zt_road, 0.01, Lw - 8, 0.12, sg['yaw'])
            stats['lane_lines'] += 1
    for end, key, cut in ((1, sg['k1'], node_w.get(sg['k1'], w) / 2), (-1, sg['k0'], node_w.get(sg['k0'], w) / 2)):
        if node_deg.get(key, 0) < 3:
            continue
        u = end * (sg['L'] / 2 - cut - 2.2)
        n = int((w - 2.0) // 2.4)
        for i in range(n):
            v = -w / 2 + 1.0 + (i + 0.5) * (w - 2.0) / n
            x, y = along(sg, u, v)
            box('default', x, y, zt_road, 0.01, 2.8, 0.55, sg['yaw'])
            stats['crosswalk'] += 1


# ---- street furniture --------------------------------------------------------
def near_origin(x, y, r=14):
    """True within r m of the spawn point: keeps the take-off area clear of props, cars and sheds."""
    return math.hypot(x, y) < r


# Per sidewalk side: kerb trees (every 24 m on avenues, 20 m elsewhere, 7 m clear at each end, 1.3 m from the
# kerb), pedestrians (one chance per 2.5 / 7 / 9 m of plaza / avenue / street, 62 % skipped), props against the
# building line every 40 m; then lamps alternating sides and traffic in the lanes. The +pi/2 and side flips in
# the yaws orient each mesh's front (empirical per asset).
for sg in segments:
    if 'walk' not in sg:
        continue
    w = sg['w']
    for side in (1, -1):
        off, Lw, sw, zt = sg['walk'][side]
        # trees near the kerb
        spacing = 24.0 if sg['ave'] else 20.0
        n = int((Lw - 14) // spacing)
        for i in range(max(0, n)):
            u = off - Lw / 2 + 7 + (i + 0.5) * (Lw - 14) / n + rng.uniform(-1.5, 1.5)
            x, y = along(sg, u, side * (w / 2 + 1.3))
            if inside_building(x, y, 2.0) or near_origin(x, y):
                continue
            row = ELM if rng.random() < 0.55 else (MAPLE if rng.random() < 0.8 else SMALL_TREE)
            s = rng.uniform(0.85, 1.15)
            add(row, x, y, zt, s, s, s, rng.uniform(0, 6.28))
            stats['trees'] += 1
        # pedestrians
        pitch = 2.5 if sg['plaza'] else (7.0 if sg['ave'] else 9.0)
        n = int(Lw // pitch)
        for i in range(n):
            if rng.random() < 0.62:
                continue
            u = off - Lw / 2 + (i + rng.random()) * Lw / n
            x, y = along(sg, u, side * (w / 2 + rng.uniform(0.9, max(1.0, sw - 0.8))))
            if inside_building(x, y, 0.3) or near_origin(x, y):
                continue
            add(rng.choice(PEOPLE_STAND), x, y, zt, 1, 1, 1, rng.uniform(0, 6.28))
            stats['people'] += 1
        # props against the building line: fuse boxes, planters, benches; cones near sheds later
        n = int(Lw // 40)
        for i in range(n):
            u = off - Lw / 2 + (i + rng.random()) * Lw / n
            x, y = along(sg, u, side * (w / 2 + sw - 0.6))
            if inside_building(x, y, 0.0) or near_origin(x, y):
                continue
            r = rng.random()
            if r < 0.35:
                add(FUSEBOX, x, y, zt, 1, 1, 1, sg['yaw'] + (0 if side > 0 else math.pi) + math.pi / 2)
            elif r < 0.7:
                add(PLANTER, x, y, zt, 1, 1, 1, rng.uniform(0, 6.28))
                add(BUSH, x, y, zt + 0.5, 0.6, 0.6, 0.6, rng.uniform(0, 6.28))
            else:
                add(BENCH, x, y, zt, 1, 1, 1, sg['yaw'] + (math.pi if side > 0 else 0))
            stats['props'] += 1
    # lamps
    lamp = LAMP_TALL if sg['ave'] else LAMP_SHORT
    spacing = 62.0 if sg['ave'] else 75.0
    off, Lw, sw, zt = sg['walk'][1]
    n = int(Lw // spacing)
    for i in range(n):
        side = 1 if (i % 2 == 0) else -1
        u = off - Lw / 2 + (i + 0.5) * Lw / n
        x, y = along(sg, u, side * (w / 2 + 0.8))
        if inside_building(x, y, 1.0) or near_origin(x, y):
            continue
        add(lamp, x, y, zt, 1, 1, 1, sg['yaw'] + (math.pi if side < 0 else 0) + math.pi / 2)
        stats['lamps'] += 1
    # traffic: one chance per 30 m (avenues) / 50 m, 60 % skipped; 60 % hug a kerb lane (1.6 m in), the rest
    # anywhere in the carriageway. trafdir 'TF' flows against the digitised direction; 'TW' is two-way, where the
    # left lanes drive the other way.
    if sg['plaza']:
        continue
    density = 30.0 if sg['ave'] else 50.0
    n = int(sg['L'] // density)
    for i in range(n):
        if rng.random() < 0.6:
            continue
        u = -sg['L'] / 2 + (i + 0.5) * sg['L'] / n + rng.uniform(-6, 6)
        lane = rng.choice([-1, 1]) * (w / 2 - 1.6) if rng.random() < 0.6 else rng.uniform(-w / 2 + 4, w / 2 - 4)
        x, y = along(sg, u, lane)
        if not in_range(x, y, 5) or near_origin(x, y, 16):
            continue
        row, length, fix, wt = rng.choices(CARS, weights=[c[3] for c in CARS])[0]
        forward = sg['yaw'] if sg['trafdir'] != 'TF' else sg['yaw'] + math.pi
        if sg['trafdir'] == 'TW' and lane < 0:
            forward += math.pi
        add(row, x, y, sg['ztop'] + 0.02, 1, 1, 1, forward + math.radians(fix))
        stats['cars'] += 1

# corners: trash cans, food carts, people waiting. Each node keeps the widest street meeting there; props are
# scattered on a ring just outside the carriageway and dropped if they land in a building or on a road.
corners = {}
for sg in segments:
    for k, p in ((sg['k0'], sg['p0']), (sg['k1'], sg['p1'])):
        corners[k] = (p, max(corners.get(k, (p, 0))[1], sg['w']))
for k, (p, w) in corners.items():
    if not in_range(*p, 20) or near_origin(*p, 2):
        continue
    for _ in range(2):
        ang = rng.uniform(0, 6.28)
        r = w / 2 + 2.5
        x, y = p[0] + r * math.cos(ang), p[1] + r * math.sin(ang)
        if inside_building(x, y, 1.0) or road_nearby(x, y, -1.0):
            continue
        add(TRASH_CAN, x, y, Z_WALK, 1, 1, 1, ang)
        stats['props'] += 1
    if rng.random() < 0.16:
        ang = rng.uniform(0, 6.28)
        r = w / 2 + 3.5
        x, y = p[0] + r * math.cos(ang), p[1] + r * math.sin(ang)
        if not inside_building(x, y, 2.5) and not road_nearby(x, y, -1.0):
            add(FOOD_CART if rng.random() < 0.7 else FOOD_STALL, x, y, Z_WALK, 1, 1, 1, ang)
            stats['props'] += 1
    for _ in range(rng.randint(0, 3)):
        ang = rng.uniform(0, 6.28)
        r = w / 2 + rng.uniform(1.5, 4)
        x, y = p[0] + r * math.cos(ang), p[1] + r * math.sin(ang)
        if not inside_building(x, y, 0.3) and not road_nearby(x, y, -0.5):
            add(rng.choice(PEOPLE_STAND), x, y, Z_WALK, 1, 1, 1, rng.uniform(0, 6.28))
            stats['people'] += 1

# sidewalk sheds (scaffolding) along street-facing frontages: up to 70 buildings of 14..60 m and >= 12 m tall
# get one face (the first that is outside other buildings, within 3 m of a road and > 30 m from the spawn) lined
# with 2.4 m scaffold modules two high. The module's base is 0.57 m below its pivot, hence Z_WALK + 0.6.
cands = [r for r in building_rects if 14 <= max(r[2], r[3]) <= 60 and r[5] >= 12]
rng.shuffle(cands)
sheds = 0
for cx, cy, lx, ly, th, h, kind in cands:
    if sheds >= 70:
        break
    for fx, fy, length, nyaw, u_edge, v_edge, nu, nv in rect_faces(cx, cy, lx, ly, th):
        px, py = l2w(cx, cy, th, u_edge + nu * 6, v_edge + nv * 6)
        if inside_building(px, py, 0.5) or not road_nearby(px, py, 3.0) or near_origin(px, py, 30):
            continue
        n = int(length // 2.4)
        yaw_mod = nyaw  # module Y runs along the facade
        for i in range(n):
            t = -length / 2 + i * 2.4 + 1.2
            u = u_edge + nu * 1.6 + (t if nu == 0 else 0)
            v = v_edge + nv * 1.6 + (t if nv == 0 else 0)
            x, y = l2w(cx, cy, th, u, v)
            for k in range(2):
                add(SCAFFOLD, x, y, Z_WALK + 0.6 + k * 2.0, 1, 1, 1, yaw_mod)
                stats['scaffold'] += 1
        # cones, barriers and pallets around the shed
        for i in range(max(1, n // 3)):
            t = rng.uniform(-length / 2, length / 2)
            x, y = l2w(cx, cy, th, u_edge + nu * 3.6 + (t if nu == 0 else 0), v_edge + nv * 3.6 + (t if nv == 0 else 0))
            if not road_nearby(x, y, -0.5):
                add(
                    rng.choice([CONE, CONE, BARRIER, PALLET, CRATE, BARREL]),
                    x,
                    y,
                    Z_WALK,
                    1,
                    1,
                    1,
                    rng.uniform(0, 6.28),
                )
                stats['props'] += 1
        sheds += 1
        break


# ---- parks (NYC Parks Properties) --------------------------------------------
# Parks are laid out BEFORE the void filler so nothing else lands on them. Each park polygon is covered with
# rectangles and dressed by its `typecategory`; Bryant Park is laid out by hand afterwards.
parks = json.load(open(os.path.join(DATA, 'midtown_parks.json')))
PLAYGROUND = ['NewRow_287', 'NewRow_288', 'NewRow_289', 'NewRow_293', 'NewRow_295', 'NewRow_296', 'NewRow_643']
FENCE = 'NewRow_780'  # SM_Fence04 chain link 0.1 x 4 x 2.7 m, Y along the fence
park_rects = []  # (cx, cy, lx, ly, th) for coverage marking


def decompose_fine(pts, cell=4.0, max_rects=30):
    """Cover a polygon with up to `max_rects` rectangles (cx, cy, lx, ly, th) on a `cell` m raster in its
    minimum-rectangle frame, largest first, until no free rectangle of 2 cells remains. Unlike decompose() it
    never settles for the single bounding rectangle, so odd-shaped parks keep their outline."""
    cx, cy, lx, ly, th = min_rect(pts)
    c, s = math.cos(th), math.sin(th)
    loc = [((p[0] - cx) * c + (p[1] - cy) * s, -(p[0] - cx) * s + (p[1] - cy) * c) for p in pts]
    nu, nv = max(1, int(math.ceil(lx / cell))), max(1, int(math.ceil(ly / cell)))
    grid = [
        [point_in_poly(-lx / 2 + (i + 0.5) * cell, -ly / 2 + (j + 0.5) * cell, loc) for i in range(nu)]
        for j in range(nv)
    ]
    out = []
    while len(out) < max_rects:
        r = largest_rect(grid)
        if not r or r[2] * r[3] < 2:
            break
        r0, c0, hh, ww = r
        for rr in range(r0, r0 + hh):
            for cc in range(c0, c0 + ww):
                grid[rr][cc] = False
        out.append(
            (*l2w(cx, cy, th, -lx / 2 + (c0 + ww / 2) * cell, -ly / 2 + (r0 + hh / 2) * cell), ww * cell, hh * cell, th)
        )
    return out


def scatter_rect(x, y, lx, ly, th, rows_, n, z, scale=(1, 1), inset=1.0, yaw=None):
    """Scatter `n` random picks from `rows_` inside a rotated rectangle (shrunk by `inset` m), at height z, with
    a uniform scale drawn from `scale` and a random yaw unless one is given. Picks that land in a building or
    near the spawn are dropped, so fewer than n may be placed."""
    for _ in range(n):
        u, v = rng.uniform(-lx / 2 + inset, lx / 2 - inset), rng.uniform(-ly / 2 + inset, ly / 2 - inset)
        px, py = l2w(x, y, th, u, v)
        if inside_building(px, py, 0.3) or near_origin(px, py):
            continue
        sc = rng.uniform(*scale)
        add(rng.choice(rows_), px, py, z, sc, sc, sc, rng.uniform(0, 6.28) if yaw is None else yaw)
        stats['park_props'] += 1


def park_paths(x, y, lx, ly, th, z_top, width=2.6, inset=5.0, cross=True):
    """Gravel perimeter path (inset) and a cross path through the middle.

    Also a lamp near the middle of each side of the loop and (ix + iy) / 18 benches along the inside edge of
    the loop, facing the park. Skipped when the rectangle is too small for the loop plus a 6 m middle."""
    if min(lx, ly) < 2 * inset + 6:
        return
    ix, iy = lx - 2 * inset, ly - 2 * inset
    for u, v, L, W in (
        (0, iy / 2, ix, width),
        (0, -iy / 2, ix, width),
        (ix / 2, 0, width, iy),
        (-ix / 2, 0, width, iy),
    ):
        px, py = l2w(x, y, th, u, v)
        plane(GRAVEL, px, py, z_top, L, W, th)
    if cross:
        plane(GRAVEL, x, y, z_top, ix, width, th)
        if min(ix, iy) > 30:
            plane(GRAVEL, x, y, z_top, width, iy, th)
    for u, v in ((ix / 2 - 1.8, 0), (-ix / 2 + 1.8, 0), (0, iy / 2 - 1.8), (0, -iy / 2 + 1.8)):
        px, py = l2w(x, y, th, u, v)
        add(LAMP_SHORT, px, py, z_top, 1, 1, 1, th)
        stats['park_props'] += 1
    for k in range(max(1, int((ix + iy) // 18))):
        edge = rng.choice(
            (
                (0, iy / 2 - width / 2 - 0.8, th + math.pi),
                (0, -iy / 2 + width / 2 + 0.8, th),
                (ix / 2 - width / 2 - 0.8, 0, th - math.pi / 2),
                (-ix / 2 + width / 2 + 0.8, 0, th + math.pi / 2),
            )
        )
        t = rng.uniform(-0.45, 0.45)
        u = edge[0] + (t * ix if edge[0] == 0 else 0)
        v = edge[1] + (t * iy if edge[1] == 0 else 0)
        px, py = l2w(x, y, th, u, v)
        if not inside_building(px, py, 0.3):
            add(BENCH, px, py, z_top, 1, 1, 1, edge[2])
            stats['park_props'] += 1


def fence_around(cx, cy, lx, ly, th, z):
    """Chain-link fence (4 m panels at 0.75 vertical scale = 2 m high) around a rotated rectangle, skipping panels
    that would stand inside a building. The fence mesh runs along its Y, hence the -pi/2 in the yaw. The Y-scale
    expression is effectively 1 (n * 4 never exceeds L), so panels are spaced out rather than stretched."""
    for u0, v0, u1, v1 in (
        (-lx / 2, -ly / 2, lx / 2, -ly / 2),
        (-lx / 2, ly / 2, lx / 2, ly / 2),
        (-lx / 2, -ly / 2, -lx / 2, ly / 2),
        (lx / 2, -ly / 2, lx / 2, ly / 2),
    ):
        L = math.hypot(u1 - u0, v1 - v0)
        n = max(1, int(L // 4))
        ang = math.atan2(v1 - v0, u1 - u0)
        for i in range(n):
            t = (i + 0.5) / n
            px, py = l2w(cx, cy, th, u0 + (u1 - u0) * t, v0 + (v1 - v0) * t)
            if inside_building(px, py, 0.0):
                continue
            add(FENCE, px, py, z, 1, min(1.0, L / (n * 4)) if n * 4 > L else 1, 0.75, th + ang - math.pi / 2)
            stats['park_props'] += 1


PARK_Z = Z_WALK + 0.02  # park props sit just above the sidewalk level
bryant = None  # (min_rect, rects) of Bryant Park, kept for the hand layout below
# Park loop: skip waterfront facilities / esplanades (off the board), tiny or out-of-range polygons. Types:
# 'Mall' = the Park Avenue planted medians; 'Playground' = paved, play equipment, fenced; 'Triangle/Plaza' =
# paved with cafe furniture (statue if >= 0.1 acres); anything else is a neighbourhood park with lawn and paths.
# Prop counts are one per N m^2 of rectangle (empirical densities).
for pk in parks:
    name = pk.get('signname', '')
    typ = pk.get('typecategory', '')
    if typ in ('Waterfront Facility',) or 'Esplanade' in name:
        continue
    g = pk['multipolygon']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in polys:
        pts = [proj(lon, lat) for lon, lat in poly[0][:-1]]
        if len(pts) < 3 or poly_area(pts) < 40:
            continue
        ccx, ccy = centroid(pts)
        if not in_range(ccx, ccy, 10):
            continue
        stats['parks'] += 1
        rects = decompose_fine(pts)
        park_rects += rects
        mr = min_rect(pts)
        if name == 'Bryant Park':
            bryant = (mr, rects)
            continue  # laid out by hand below
        for x, y, lx, ly, th in rects:
            if typ == 'Mall':  # Park Avenue planted medians
                lawn(x, y, Z_WALK + 0.03, lx, ly, th)
                scatter_rect(x, y, lx, ly, th, [BUSH, BUSH2], max(1, int(lx * ly / 25)), PARK_Z, (0.7, 1.1), inset=0.8)
                scatter_rect(
                    x, y, lx, ly, th, [SMALL_TREE, MAPLE], max(0, int(lx * ly / 120)), PARK_Z, (0.7, 1.0), inset=1.5
                )
            elif typ == 'Playground':
                box('concrete', x, y, Z_GROUND, PARK_Z - 0.02 - Z_GROUND, lx, ly, th)
                plane(PAVE2, x, y, PARK_Z, lx, ly, th)
                scatter_rect(x, y, lx, ly, th, PLAYGROUND, max(1, int(lx * ly / 110)), PARK_Z, (1, 1), inset=3)
                scatter_rect(
                    x, y, lx, ly, th, [BENCH, TRASH_CAN, PLANTER], max(1, int(lx * ly / 150)), PARK_Z, (1, 1), inset=1.5
                )
                scatter_rect(x, y, lx, ly, th, [ELM, MAPLE], max(0, int(lx * ly / 300)), PARK_Z, (0.8, 1.1), inset=3)
                scatter_rect(x, y, lx, ly, th, PEOPLE_STAND, max(1, int(lx * ly / 120)), PARK_Z)
                fence_around(x, y, lx, ly, th, PARK_Z)
            elif typ == 'Triangle/Plaza':
                box('concrete', x, y, Z_GROUND, PARK_Z - 0.02 - Z_GROUND, lx, ly, th)
                plane(PAVE2, x, y, PARK_Z, lx, ly, th)
                scatter_rect(
                    x,
                    y,
                    lx,
                    ly,
                    th,
                    [PLANTER, BENCH, CAFE_TABLE, TRASH_CAN],
                    max(2, int(lx * ly / 30)),
                    PARK_Z,
                    (1, 1),
                    inset=1.2,
                )
                scatter_rect(
                    x, y, lx, ly, th, [MAPLE, ELM, SMALL_TREE], max(1, int(lx * ly / 80)), PARK_Z, (0.8, 1.1), inset=2
                )
                scatter_rect(x, y, lx, ly, th, [BUSH, BUSH2], max(1, int(lx * ly / 60)), PARK_Z, (0.7, 1.0), inset=1)
                scatter_rect(x, y, lx, ly, th, PEOPLE_STAND, max(2, int(lx * ly / 25)), PARK_Z)
                scatter_rect(x, y, lx, ly, th, [CHAIR], max(1, int(lx * ly / 50)), PARK_Z)
                if min(lx, ly) > 10:
                    add(LAMP_SHORT, *l2w(x, y, th, lx / 2 - 2, ly / 2 - 2), PARK_Z, 1, 1, 1, th)
            else:  # neighbourhood parks: lawn, gravel paths, trees, benches, people
                lawn(x, y, Z_WALK + 0.03, lx, ly, th)
                park_paths(x, y, lx, ly, th, Z_WALK + 0.05)
                scatter_rect(
                    x,
                    y,
                    lx,
                    ly,
                    th,
                    [ELM, MAPLE, ELM, SMALL_TREE],
                    max(2, int(lx * ly / 70)),
                    PARK_Z,
                    (0.9, 1.4),
                    inset=2,
                )
                scatter_rect(x, y, lx, ly, th, [BUSH, BUSH2], max(2, int(lx * ly / 60)), PARK_Z, (0.7, 1.1), inset=1)
                scatter_rect(x, y, lx, ly, th, [BENCH, TRASH_CAN, PLANTER, BENCH], max(2, int(lx * ly / 90)), PARK_Z)
                scatter_rect(x, y, lx, ly, th, PEOPLE_STAND + PEOPLE_SIT, max(2, int(lx * ly / 45)), PARK_Z)
        if typ == 'Triangle/Plaza' and float(pk.get('acres') or 0) >= 0.1:
            add(STATUE, ccx, ccy, PARK_Z, 0.9, 0.9, 0.9, rng.uniform(0, 6.28))
# Bryant Park: great lawn, gravel paths, plane-tree allees with tables and chairs, fountain, kiosks.
# Worked in a frame (tha) along the park's LONG axis (u) with Lp x Wp the park rectangle. The park polygon also
# contains the New York Public Library, so `blocked` finds the u positions a building covers, `runs` the free
# stretches, and the longest run [a, b_] is the usable park; it is flipped so the open end (where the fountain
# is, the west end in reality) is at -u. The lawn then spans a+30..b_-12 at half the park width.
if bryant:
    (cx, cy, lx, ly, th), rects = bryant
    long_u = lx >= ly
    Lp, Wp = (lx, ly) if long_u else (ly, lx)
    tha = th if long_u else th + math.pi / 2
    box('concrete', cx, cy, Z_GROUND, Z_WALK - 0.02 - Z_GROUND, lx, ly, th)
    plane(GRAVEL, cx, cy, Z_WALK, lx, ly, th)  # gravel over the whole park
    blocked = {
        u
        for u in range(int(-Lp / 2) + 2, int(Lp / 2) - 1, 2)
        if any(inside_building(*l2w(cx, cy, tha, u, v), 0.0) for v in (0, Wp / 4, -Wp / 4))
    }
    runs = []
    start = None
    for u in range(int(-Lp / 2) + 2, int(Lp / 2) + 1, 2):
        free = u not in blocked and u < int(Lp / 2)
        if free and start is None:
            start = u
        if not free and start is not None:
            runs.append((start, u - 2))
            start = None
    a, b_ = max(runs, key=lambda r: r[1] - r[0]) if runs else (-Lp / 2 + 2, Lp / 2 - 2)
    if b_ >= Lp / 2 - 4 and a > -Lp / 2 + 4:
        tha += math.pi
        a, b_ = -b_, -a  # put the open end at -u (fountain end)
    stats['bryant_run'] = (round(a), round(b_), round(Lp))
    lawn_u0, lawn_u1 = a + 30, b_ - 12
    lawn_L, lawn_W = max(20, lawn_u1 - lawn_u0), Wp * 0.5
    lx0, ly0 = l2w(cx, cy, tha, (lawn_u0 + lawn_u1) / 2, 0)
    lawn(lx0, ly0, Z_WALK + 0.03, lawn_L, lawn_W, tha)
    for _ in range(40):  # people and chairs on the lawn
        px, py = l2w(
            lx0, ly0, tha, rng.uniform(-lawn_L / 2 + 2, lawn_L / 2 - 2), rng.uniform(-lawn_W / 2 + 2, lawn_W / 2 - 2)
        )
        add(rng.choice(PEOPLE_SIT + [CHAIR]), px, py, Z_WALK + 0.03, 1, 1, 1, rng.uniform(0, 6.28))
    for side in (1, -1):  # two rows of planes each side, tables under them
        for row_off in (Wp / 2 - 6, Wp / 2 - 12):
            n = max(2, int((b_ - a - 10) // 6.5))
            for i in range(n):
                u = a + 5 + (i + 0.5) * (b_ - a - 10) / n
                px, py = l2w(cx, cy, tha, u, side * row_off)
                if inside_building(px, py, 1.0):
                    continue
                add(ELM, px, py, Z_WALK, 1.35, 1.35, 1.4, rng.uniform(0, 6.28))
                stats['park_props'] += 1
                if rng.random() < 0.6:
                    tx, ty = l2w(cx, cy, tha, u + 3.2, side * (row_off - 3))
                    add(CAFE_TABLE, tx, ty, Z_WALK, 1, 1, 1, rng.uniform(0, 6.28))
                    for a in (0.3, 2.4, 4.3):
                        add(CHAIR, tx + 0.9 * math.cos(a), ty + 0.9 * math.sin(a), Z_WALK, 1, 1, 1, a + math.pi)
                    if rng.random() < 0.5:
                        add(rng.choice(PEOPLE_SIT), tx + 0.9, ty, Z_WALK, 1, 1, 1, rng.uniform(0, 6.28))
    fx, fy = l2w(cx, cy, tha, a + 13, 0)  # fountain at the open end
    # 9 m basin, a blue "water" slab just below its rim, pedestal and upper bowl, ring of 14 onlookers facing in
    cylinder('grey', fx, fy, Z_WALK, 0.9, 9.0)
    add(CUBE['blue'], fx, fy, Z_WALK + 0.85, 7.6, 7.6, 0.1)
    cylinder('grey', fx, fy, Z_WALK, 2.4, 2.4)
    cylinder('grey', fx, fy, Z_WALK + 2.4, 0.5, 4.2)
    for i in range(14):
        a = i / 14 * 6.283
        add(rng.choice(PEOPLE_STAND), fx + 7 * math.cos(a), fy + 7 * math.sin(a), Z_WALK, 1, 1, 1, a + math.pi)
    # kiosks in the four corners, eight lamps down each long side
    for u, v in ((a + 6, Wp / 2 - 4), (a + 6, -Wp / 2 + 4), (b_ - 8, Wp / 2 - 4), (b_ - 8, -Wp / 2 + 4)):
        px, py = l2w(cx, cy, tha, u, v)
        if not inside_building(px, py, 1.0):
            add(FOOD_STALL, px, py, Z_WALK, 1, 1, 1, tha + rng.uniform(-0.3, 0.3))
    for i in range(8):
        u = a + 4 + i * (b_ - a - 8) / 7
        for v in (Wp / 2 - 3, -Wp / 2 + 3):
            px, py = l2w(cx, cy, tha, u, v)
            if not inside_building(px, py, 1.0):
                add(LAMP_SHORT, px, py, Z_WALK, 1, 1, 1, tha)
    stats['bryant'] = 1

# ---- void filling: parking lots, plazas, rear yards --------------------------
# A 2 m coverage raster over the core square, axis-aligned with the STREET GRID (not the map axes) so that the
# rectangles it finds line up with the blocks. `covered` = building, park or street (with margins); `built` =
# building only, used to find the urban area. Cells that are urban but not covered are voids.
GRID_YAW = GRID_SNAP  # dominant street-grid orientation
CELL = 2.0
N = int(2 * MAX_RANGE / CELL)


def to_grid(x, y):
    """World (x, y) -> grid-frame (u, v) metres (rotated by -GRID_YAW)."""
    u, v = l2w(0, 0, -GRID_YAW, x, y)
    return u, v


def from_grid(u, v):
    """Grid-frame (u, v) metres -> world (x, y)."""
    return l2w(0, 0, GRID_YAW, u, v)


covered = bytearray(N * N)
built = bytearray(N * N)


def mark_rect(cx, cy, lx, ly, th, margin, arr):
    """Set every raster cell of `arr` (N x N bytearray, index i * N + j, cell centres at (i + 0.5) * CELL -
    MAX_RANGE in the grid frame) whose centre lies in the rotated rectangle grown by `margin` m."""
    gcx, gcy = to_grid(cx, cy)
    r = math.hypot(lx, ly) / 2 + margin
    a = th - GRID_YAW
    c, s = math.cos(a), math.sin(a)
    i0, i1 = max(0, int((gcx - r + MAX_RANGE) / CELL)), min(N - 1, int((gcx + r + MAX_RANGE) / CELL))
    j0, j1 = max(0, int((gcy - r + MAX_RANGE) / CELL)), min(N - 1, int((gcy + r + MAX_RANGE) / CELL))
    for i in range(i0, i1 + 1):
        du = (i + 0.5) * CELL - MAX_RANGE - gcx
        for j in range(j0, j1 + 1):
            dv = (j + 0.5) * CELL - MAX_RANGE - gcy
            uu = du * c + dv * s
            vv = -du * s + dv * c
            if abs(uu) <= lx / 2 + margin and abs(vv) <= ly / 2 + margin:
                arr[i * N + j] = 1


for cx, cy, lx, ly, th, h, kind in building_rects:
    mark_rect(cx, cy, lx, ly, th, 1.0, covered)
    mark_rect(cx, cy, lx, ly, th, 0, built)
for cx, cy, lx, ly, th in park_rects:
    mark_rect(cx, cy, lx, ly, th, 1.5, covered)
for sg in segments:
    mx, my = seg_mid(sg)
    wtot = sg['w'] + 2 * (max(v[2] for v in sg['walk'].values()) if 'walk' in sg else 4)
    mark_rect(mx, my, sg['L'] + sg['w'], wtot, sg['yaw'], 1.0, covered)
# urban mask: 20 m blocks (B = 10 cells) containing buildings, dilated by one block in all 8 directions, so
# voids are only looked for between buildings and not in open space at the edge of the data
B = 10
NB = N // B
blk = bytearray(NB * NB)
for i in range(N):
    for j in range(N):
        if built[i * N + j]:
            blk[(i // B) * NB + (j // B)] = 1
urban = bytearray(NB * NB)
for bi in range(NB):
    for bj in range(NB):
        if any(
            blk[ii * NB + jj]
            for ii in range(max(0, bi - 1), min(NB, bi + 2))
            for jj in range(max(0, bj - 1), min(NB, bj + 2))
        ):
            urban[bi * NB + bj] = 1
void = bytearray(N * N)
for i in range(N):
    for j in range(N):
        if not covered[i * N + j] and urban[(i // B) * NB + (j // B)]:
            void[i * N + j] = 1
# connected components of void cells (4-neighbour flood fill), one per patch
seen = bytearray(N * N)
comps = []
for i in range(N):
    for j in range(N):
        if void[i * N + j] and not seen[i * N + j]:
            stack = [(i, j)]
            seen[i * N + j] = 1
            cells = []
            while stack:
                a, b_ = stack.pop()
                cells.append((a, b_))
                for na, nb in ((a + 1, b_), (a - 1, b_), (a, b_ + 1), (a, b_ - 1)):
                    if 0 <= na < N and 0 <= nb < N and void[na * N + nb] and not seen[na * N + nb]:
                        seen[na * N + nb] = 1
                        stack.append((na, nb))
            comps.append(cells)


def comp_rects(cells, max_rects=6, min_cells=6):
    """Cover one void component (list of (i, j) cells) with up to `max_rects` grid-aligned rectangles of at least
    `min_cells` cells -> [(x, y, lx, ly)] in world metres (yaw is implicitly GRID_YAW)."""
    i0, i1 = min(c[0] for c in cells), max(c[0] for c in cells)
    j0, j1 = min(c[1] for c in cells), max(c[1] for c in cells)
    grid = [[False] * (i1 - i0 + 1) for _ in range(j1 - j0 + 1)]
    for a, b_ in cells:
        grid[b_ - j0][a - i0] = True
    out = []
    while len(out) < max_rects:
        r = largest_rect(grid)
        if not r or r[2] * r[3] < min_cells:
            break
        r0, c0, hh, ww = r
        for rr in range(r0, r0 + hh):
            for cc in range(c0, c0 + ww):
                grid[rr][cc] = False
        gu = (i0 + c0 + ww / 2) * CELL - MAX_RANGE
        gv = (j0 + r0 + hh / 2) * CELL - MAX_RANGE
        x, y = from_grid(gu, gv)
        out.append((x, y, ww * CELL, hh * CELL))
    return out


def scatter(x, y, lx, ly, rows_, n, z, scale=(1, 1)):
    """scatter_rect() for grid-aligned void rectangles (yaw GRID_YAW, 1 m inset), counted as fill_props."""
    for _ in range(n):
        u, v = rng.uniform(-lx / 2 + 1, lx / 2 - 1), rng.uniform(-ly / 2 + 1, ly / 2 - 1)
        px, py = l2w(x, y, GRID_YAW, u, v)
        if inside_building(px, py, 0.3) or near_origin(px, py):
            continue
        s = rng.uniform(*scale)
        add(rng.choice(rows_), px, py, z, s, s, s, rng.uniform(0, 6.28))
        stats['fill_props'] += 1


# Dress the voids: < 16 m^2 ignored; "big" (>= 420 m^2 with a rectangle >= 12 m wide) become parking lots
# (60 %) or plazas, the rest rear yards. Lots at least 22 m wide away from the spawn are reserved in
# `lot_rects` (up to 12) for the FPV construction sites and parking decks later instead of being paved here.
lot_rects = []
for cells in comps:
    area = len(cells) * CELL * CELL
    if area < 16:
        continue
    rects = comp_rects(cells)
    if not rects:
        continue
    big = area >= 420 and max(min(r[2], r[3]) for r in rects) >= 12
    if not big:
        for x, y, lx, ly in rects:
            n = max(1, int(lx * ly / 70))
            scatter(x, y, lx, ly, [DUMPSTER, PALLET, CRATE, BARREL, BARREL, BUSH, BUSH2], n, Z_GROUND)
            if min(lx, ly) >= 8 and rng.random() < 0.5:
                scatter(x, y, lx, ly, [SMALL_TREE, MAPLE], 1, Z_GROUND, (0.8, 1.1))
        stats['yards'] += 1
        continue
    kind_fill = 'lot' if rng.random() < 0.6 else 'plaza'
    for x, y, lx, ly in rects:
        if kind_fill == 'lot' and min(lx, ly) >= 10:
            if min(lx, ly) >= 22 and len(lot_rects) < 12 and not near_origin(x, y, 60) and max(abs(x), abs(y)) < 820:
                lot_rects.append((x, y, lx, ly))
                continue  # reserved for FPV sites
            plane(ASPHALT, x, y, Z_GROUND + 0.03, lx, ly, GRID_YAW)
            stats['lots'] += 1
            # parked cars: rows 6 m apart along the long side, 2.9 m bays, 72 % of bays empty, a lamp in the middle
            along_u = lx >= ly
            span, depth = (lx, ly) if along_u else (ly, lx)
            nrows = max(1, int((depth - 2) // 6.0))
            ncar = max(1, int((span - 2) // 2.9))
            for r in range(nrows):
                for c in range(ncar):
                    if rng.random() < 0.72:
                        continue
                    a = -span / 2 + 1.5 + (c + 0.5) * (span - 3) / ncar
                    b_ = -depth / 2 + 3 + r * 6.0
                    u, v = (a, b_) if along_u else (b_, a)
                    px, py = l2w(x, y, GRID_YAW, u, v)
                    if near_origin(px, py, 16):
                        continue
                    row, length, fix, wt = rng.choices(CARS, weights=[c_[3] for c_ in CARS])[0]
                    add(
                        row,
                        px,
                        py,
                        Z_GROUND + 0.04,
                        1,
                        1,
                        1,
                        GRID_YAW + (math.pi / 2 if along_u else 0) + math.radians(fix) + rng.uniform(-0.05, 0.05),
                    )
                    stats['cars'] += 1
            px, py = l2w(x, y, GRID_YAW, 0, 0)
            add(LAMP_SHORT, px, py, Z_GROUND, 1, 1, 1, GRID_YAW)
            stats['lamps'] += 1
        elif kind_fill == 'plaza' and min(lx, ly) >= 10:
            box('concrete', x, y, Z_GROUND, Z_WALK - 0.02 - Z_GROUND, lx, ly, GRID_YAW)
            plane(PAVE2, x, y, Z_WALK, lx, ly, GRID_YAW)
            stats['plazas'] += 1
            nt = max(1, int(lx * ly / 90))
            scatter(x, y, lx, ly, [ELM, MAPLE, SMALL_TREE], nt, Z_WALK, (0.8, 1.1))
            scatter(x, y, lx, ly, [BENCH, PLANTER, CAFE_TABLE, TRASH_CAN], max(1, int(lx * ly / 60)), Z_WALK)
            scatter(x, y, lx, ly, PEOPLE_STAND, max(1, int(lx * ly / 50)), Z_WALK)
        else:
            scatter(
                x,
                y,
                lx,
                ly,
                [DUMPSTER, PALLET, CRATE, BARREL, BUSH, BUSH2, SMALL_TREE],
                max(1, int(lx * ly / 40)),
                Z_GROUND,
            )

# ---- plazas: Times Square and Herald Square --------------------------------
# The Broadway plaza blocks: cafe tables with two chairs (70 %) or a planter with a bush every 7 m along both
# edges 3.5 m in from the kerb, and a crowd of one person per 2.5 m of length anywhere on the plaza.
for sg in segments:
    if not sg['plaza']:
        continue
    w, L, zt = sg['w'], sg['L'], sg['ztop']
    n = int(L // 7)
    for i in range(n):
        u = -L / 2 + (i + 0.5) * L / n
        for v in (-w / 2 + 3.5, w / 2 - 3.5):
            x, y = along(sg, u, v + rng.uniform(-1, 1))
            if near_origin(x, y):
                continue
            if rng.random() < 0.7:
                add(CAFE_TABLE, x, y, zt, 1, 1, 1, rng.uniform(0, 6.28))
                for a in (0, 2.2):
                    cx_, cy_ = x + 0.9 * math.cos(a + rng.random()), y + 0.9 * math.sin(a + rng.random())
                    add(CHAIR, cx_, cy_, zt, 1, 1, 1, rng.uniform(0, 6.28))
                if rng.random() < 0.5:
                    add(rng.choice(PEOPLE_SIT), x + 0.8, y, zt, 1, 1, 1, rng.uniform(0, 6.28))
            else:
                add(PLANTER, x, y, zt, 1.3, 1.3, 1.3, 0)
                add(BUSH2, x, y, zt + 0.7, 0.7, 0.7, 0.7, rng.uniform(0, 6.28))
            stats['plaza_props'] += 1
    for i in range(int(L // 2.5)):
        x, y = along(sg, -L / 2 + rng.random() * L, rng.uniform(-w / 2 + 1, w / 2 - 1))
        if not near_origin(x, y):
            add(rng.choice(PEOPLE_STAND), x, y, zt, 1, 1, 1, rng.uniform(0, 6.28))
            stats['people'] += 1
# TKTS red steps at Duffy Square: nine 1.25 m treads rising 0.55 m each, 15 m wide, starting 14 m back from the
# 47th Street node towards 42nd, with two people sitting on each step facing 42nd (the bowtie).
bway_yaw = math.atan2(duffy[1] - ts42[1], duffy[0] - ts42[0])  # direction 42nd -> 47th along Broadway
for i in range(9):
    x, y = l2w(duffy[0], duffy[1], bway_yaw, -14 - i * 1.25, 0)
    box('red', x, y, Z_WALK + 0.02, 0.55 * (i + 1), 1.25, 15, bway_yaw)
    stats['tkts'] += 1
    for _ in range(2):
        px, py = l2w(duffy[0], duffy[1], bway_yaw, -14 - i * 1.25 + 0.3, rng.uniform(-7, 7))
        add(rng.choice(PEOPLE_SIT), px, py, Z_WALK + 0.02 + 0.55 * (i + 1), 1, 1, 1, bway_yaw + math.pi)

# ---- Times Square screens, neon, billboards ----------------------------------
# LED screens go only on true ground-level box facades (box_faces) that look at the Times Square bowtie
# polyline (Broadway 42nd..47th) or at Herald Square. LED_V is 3 x 8 m with its screen facing local +Y, so a
# facade whose outward normal is `nyaw` needs yaw nyaw - pi/2.
ts_poly = ts_nodes
SCREEN_PRESETS = [
    (1.6, 1.2),
    (2.4, 1.3),
    (1.4, 1.9),
    (3.0, 1.1),
    (2.0, 1.6),
]  # (width scale, height scale) of the 3 x 8 m screen


def signage_faces(target_poly, max_d):
    """Facades suitable for signage facing `target_poly` within `max_d` m -> [(fx, fy, length, normal_yaw, h, d)]
    sorted by distance. Only ground-level box tiers >= 14 m tall, faces >= 9 m long, whose outward normal points
    at the polyline (cosine >= 0.35) and that are not buried in a neighbouring building 1.5 m out."""
    out = []
    for cx, cy, lx, ly, th, h, kind in box_faces:
        if h < 14 or dist_to_polyline(cx, cy, target_poly)[0] > max_d:
            continue
        for fx, fy, length, nyaw, u_edge, v_edge, nu, nv in rect_faces(cx, cy, lx, ly, th):
            if length < 9:
                continue
            dd, bpf = dist_to_polyline(fx, fy, target_poly)
            facing = (bpf[0] - fx) * math.cos(nyaw) + (bpf[1] - fy) * math.sin(nyaw)
            if facing / max(dd, 1) < 0.35 or inside_building(fx + 1.5 * math.cos(nyaw), fy + 1.5 * math.sin(nyaw), 0.0):
                continue
            out.append((fx, fy, length, nyaw, h, dd))
    out.sort(key=lambda f: f[5])
    return out


# up to three varied screens per facade (one slot per 11 m), 4.5..24 m up but below the roof; neon tubes at
# 3.8 m on the first 60 facades wider than 12 m
screen_facades = signage_faces(ts_poly, 110)
neon_count = 0
for fx, fy, length, nyaw, h, dd in screen_facades:
    slots = min(3, max(1, int(length // 11)))
    used = []
    for i in range(slots):
        t = -length / 2 + (i + 0.5) * length / slots + rng.uniform(-1.5, 1.5)
        sw, sh = rng.choice([p for p in SCREEN_PRESETS if p not in used] or SCREEN_PRESETS)
        used.append((sw, sh))
        z = rng.uniform(4.5, max(4.6, min(h - 8 * sh - 1, 24)))
        x, y = fx + t * math.cos(nyaw + math.pi / 2), fy + t * math.sin(nyaw + math.pi / 2)
        add(LED_V, x, y, Z_GROUND + z, sw, 1, sh, nyaw - math.pi / 2)
        stats['screens'] += 1
    if neon_count < 60 and length > 12:
        for t in (-length / 3, length / 3):
            x, y = fx + t * math.cos(nyaw + math.pi / 2), fy + t * math.sin(nyaw + math.pi / 2)
            add(
                rng.choice(NEONS),
                x + 0.3 * math.cos(nyaw),
                y + 0.3 * math.sin(nyaw),
                Z_GROUND + 3.8,
                1,
                1,
                1,
                nyaw + math.pi / 2,
            )
            neon_count += 1
for fx, fy, length, nyaw, h, dd in screen_facades[:4]:  # a few giant screens (15 x 32 m) closest to the bowtie
    if h > 45 and length > 20:
        add(LED_V, fx + 0.1 * math.cos(nyaw), fy + 0.1 * math.sin(nyaw), Z_GROUND + 26, 5.0, 1, 4.0, nyaw - math.pi / 2)
        stats['screens'] += 1
# Herald Square: ten 6 x 12.8 m screens on the nearest facades (a 1 m stub polyline stands in for the square)
for fx, fy, length, nyaw, h, dd in signage_faces([herald, (herald[0] + 1, herald[1] + 1)], 90)[:10]:
    add(LED_V, fx, fy, Z_GROUND + rng.uniform(5, 12), 2.0, 1, 1.6, nyaw - math.pi / 2)
    stats['herald_screens'] += 1


# ---- decals (variant): windows + billboards -----------------------------------
# Window-grid and billboard textures are generated PNGs projected onto facades as wall decals (the editor's
# custom-decal loader, as Workshop maps use). Grid sizes are bucketed so only a few hundred distinct PNGs are
# written. Collected into `decal_rows` / `decal_files` and only written when WITH_WINDOWS.
def window_png(style, cols, rows, path):
    """Write a cols x rows window-grid texture (48 px cells, transparent background) to `path`.

    'punched': inset dark window panes with a light sill line and a pale frame (masonry buildings).
    Otherwise (curtain wall / 'glass'): full-cell blue glass with a darker spandrel band over the bottom 26 % and
    light mullion lines. A sine shading per row breaks up the repetition."""
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


BILLBOARD_TEXT = [
    'NYC',
    'FPV',
    'LIVE',
    'BROADWAY',
    'TIMES SQ',
    'DRONE',
    'NEW YORK',
    'UNCRASHED',
    'MIDTOWN',
    '34',
    'SHOW',
    'TONIGHT',
]


def billboard_png(i, path):
    """Write billboard texture number `i` (768 x 480): a two-colour gradient, a few translucent blobs, a word
    from BILLBOARD_TEXT in Impact (falls back to PIL's default font) and a dark border. Seeded by `i` so the
    same number always gives the same artwork."""
    from PIL import Image, ImageDraw, ImageFont

    r = random.Random(i)
    W, H = 768, 480
    img = Image.new('RGBA', (W, H))
    d = ImageDraw.Draw(img)
    c0 = tuple(r.randint(20, 255) for _ in range(3))
    c1 = tuple(r.randint(20, 255) for _ in range(3))
    for y in range(H):
        t = y / H
        d.line((0, y, W, y), fill=tuple(int(c0[k] * (1 - t) + c1[k] * t) for k in range(3)) + (255,))
    for _ in range(r.randint(2, 5)):
        x, y = r.randint(0, W), r.randint(0, H)
        rad = r.randint(40, 200)
        col = tuple(r.randint(0, 255) for _ in range(3)) + (160,)
        d.ellipse((x - rad, y - rad, x + rad, y + rad), fill=col)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Impact.ttf', 150)
    except Exception:
        font = ImageFont.load_default()
    text = BILLBOARD_TEXT[i % len(BILLBOARD_TEXT)]
    try:
        bb = d.textbbox((0, 0), text, font=font)
        tw, th_ = bb[2] - bb[0], bb[3] - bb[1]
    except Exception:
        tw, th_ = 300, 100
    d.text(((W - tw) / 2, (H - th_) / 2 - 20), text, fill=(255, 255, 255, 255), font=font)
    d.rectangle((0, 0, W - 1, H - 1), outline=(20, 20, 20, 255), width=12)
    img.save(path)


# allowed window-grid sizes (columns x rows); each distinct pair becomes one PNG shared by every matching facade
COLS_B = [3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32]
ROWS_B = [6, 8, 10, 12, 15, 18, 22, 26, 30, 36, 42, 50, 60, 72, 85, 100]


def nearest(v, buckets):
    """The bucket value closest to v."""
    return min(buckets, key=lambda b: abs(b - v))


# Window decals: one per outer face of every recorded facade tier. Rows = height / floor pitch (3.6 m punched,
# 4.0 m glass), columns = width / window module (2.6 m punched, 1.6 m glass). A face is skipped as a party wall
# when a building rectangle 0.8 m outside it reaches at least half way up this tier. The decal's row name IS
# the PNG filename (fixed numeric stamp + md5 of the grid key); Scale3D = (2 m depth, h / 4, length / 4) and
# the pivot is the face centre at mid-height.
decal_rows = {}  # decal row name (PNG filename) -> transforms, merged into the map by write_map()
decal_files = {}  # PNG filename -> ('win', style, cols, rows) or ('bb', index), rendered by write_map()
for cx, cy, z0, h, lx, ly, th, style, key in facades:
    fl = 3.6 if style == 'punched' else 4.0
    wm = 2.6 if style == 'punched' else 1.6
    rows_n = nearest(h / fl, ROWS_B)
    for fx, fy, length, nyaw, u_edge, v_edge, nu, nv in rect_faces(cx, cy, lx, ly, th):
        px, py = fx + 0.8 * math.cos(nyaw), fy + 0.8 * math.sin(nyaw)
        j = building_at(px, py, 0.0)
        if j is not None and building_rects[j][5] + 1 >= z0 + h * 0.5:
            continue  # party wall / internal face: no windows
        cols_n = nearest(length / wm, COLS_B)
        k = f'{style}_{cols_n}x{rows_n}'
        name = 'decal_1791400000-' + hashlib.md5(k.encode()).hexdigest().upper() + '.png'
        decal_files[name] = ('win', style, cols_n, rows_n)
        add(name, fx, fy, z0 + h / 2, 2.0, h / 4, length / 4, rot=decal_rot(nyaw), store=decal_rows)
        stats['win_decals'] += 1
# Billboard decals on the Times Square facades >= 36 m tall and 14 m wide: 9 x 14.4 m (scale 2.25 x 3.6) at 32 m
# and 52 m up (capped 10 m below the roof, dropped below 14 m), cycling through twelve generated artworks.
for idx, (fx, fy, length, nyaw, h, dd) in enumerate(screen_facades):
    if h < 36 or length < 14:
        continue
    i = idx % 12
    name = 'decal_1791400001-' + hashlib.md5(f'bb{i}'.encode()).hexdigest().upper() + '.png'
    decal_files[name] = ('bb', i)
    for z in (min(h - 10, 32), min(h - 10, 52)):
        if z < 14:
            continue
        t = rng.uniform(-length / 2 + 8, length / 2 - 8) if length > 16 else 0
        x, y = fx + t * math.cos(nyaw + math.pi / 2), fy + t * math.sin(nyaw + math.pi / 2)
        add(name, x, y, Z_GROUND + z, 2.0, 2.25, 3.6, rot=decal_rot(nyaw), store=decal_rows)
        stats['billboards'] += 1


# ---- FPV fun: construction skeletons, open parking decks, skybridges ---------
# Things to fly through. The reserved void lots (largest first, at least 22 m wide, > 60 m from the spawn and
# inside 820 m) become four construction sites and three parking decks, each capped at 60 x 60 m.
CRANES = ['NewRow_338', 'NewRow_335']  # BP_YellowCrane_C, BP_RedCrane_C
CONTAINER, FORKLIFT, MIXER, TOILET = 'NewRow_190', 'NewRow_196', 'NewRow_191', 'NewRow_188'
lot_rects_big = sorted(
    [
        r
        for r in lot_rects
        if min(r[2], r[3]) >= 22 and not near_origin(r[0], r[1], 60) and max(abs(r[0]), abs(r[1])) < 820
    ],
    key=lambda r: -r[2] * r[3],
)


def construction_site(x, y, lx, ly, th, floors):
    """Open concrete skeleton on a dirt lot: `floors` storeys of 3.6 m with 0.55 m columns on a ~7 m grid (6 %
    missing) and a slab on every floor except, half the time, the top one; a stair core, a tower crane in one
    corner, a chain-link fence, scaffolding three high along one side, and scattered plant, containers,
    cones, a forklift and workers. The lot is lx x ly m centred at (x, y) with yaw th; columns are inset 2 m."""
    fh = 3.6
    ix, iy = lx - 4, ly - 4
    plane(DIRT, x, y, Z_GROUND + 0.03, lx, ly, th)
    cols_u = max(2, int(ix // 7))
    cols_v = max(2, int(iy // 7))
    for k in range(floors):
        z = Z_GROUND + 0.5 + k * fh
        for i in range(cols_u + 1):
            for j in range(cols_v + 1):
                if rng.random() < 0.06:
                    continue
                px, py = l2w(x, y, th, -ix / 2 + i * ix / cols_u, -iy / 2 + j * iy / cols_v)
                box('grey', px, py, z, fh, 0.55, 0.55, th)
        if k < floors - 1 or rng.random() < 0.5:
            box('concrete', x, y, z + fh - 0.3, 0.3, ix, iy, th)
    cx_, cy_ = l2w(x, y, th, ix / 2 - 3.5, -iy / 2 + 4)
    box('concrete', cx_, cy_, Z_GROUND, floors * fh + 3, 5, 6, th)  # stair core
    cr_x, cr_y = l2w(x, y, th, -lx / 2 + 4, ly / 2 - 4)
    add(rng.choice(CRANES), cr_x, cr_y, Z_GROUND, 1, 1, 1, th + rng.uniform(0, 6.28))
    fence_around(x, y, lx, ly, th, Z_GROUND)
    for i in range(int(lx // 2.4)):
        px, py = l2w(x, y, th, -lx / 2 + 1.2 + i * 2.4, iy / 2 + 0.6)
        for k in range(min(3, floors)):
            add(SCAFFOLD, px, py, Z_GROUND + 0.6 + k * 2.0, 1, 1, 1, th + math.pi / 2)
    scatter_rect(
        x,
        y,
        lx,
        ly,
        th,
        [CONTAINER, DUMPSTER, PALLET, PALLET, CRATE, BARREL, CONE, CONE, BARRIER, MIXER, TOILET],
        max(6, int(lx * ly / 60)),
        Z_GROUND + 0.02,
        inset=2.5,
    )
    scatter_rect(x, y, lx, ly, th, [FORKLIFT], 1, Z_GROUND + 0.02, inset=5)
    scatter_rect(x, y, lx, ly, th, PEOPLE_STAND, 6, Z_GROUND + 0.02, inset=2)
    stats['construction'] += 1
    stats.setdefault('sites', []).append((round(x), round(y), 'construction'))


def parking_deck(x, y, lx, ly, th, levels):
    """Open multi-storey car park: `levels` decks of 3.2 m. Level 0 is asphalt, every deck above is a 0.35 m
    concrete slab with 1 m parapets; 0.5 m columns on an ~8 m grid hold up the next deck, a 4 m wide ramp along
    the long side climbs to it (so a drone can follow the ramp up), parked cars line both sides of each level
    (50 % of bays) and a lamp sits in the middle. No roof above the top deck."""
    dh = 3.2
    along_u = lx >= ly
    for k in range(levels + 1):
        z = Z_GROUND + k * dh
        if k > 0:
            box('concrete', x, y, z - 0.35, 0.35, lx, ly, th)
            for u, v, L, W in (
                (0, ly / 2 - 0.2, lx, 0.4),
                (0, -ly / 2 + 0.2, lx, 0.4),
                (lx / 2 - 0.2, 0, 0.4, ly),
                (-lx / 2 + 0.2, 0, 0.4, ly),
            ):
                px, py = l2w(x, y, th, u, v)
                box('concrete', px, py, z, 1.0, L, W, th)
        else:
            plane(ASPHALT, x, y, Z_GROUND + 0.03, lx, ly, th)
        if k < levels:
            for i in range(max(2, int(lx // 8)) + 1):
                for j in range(max(2, int(ly // 8)) + 1):
                    px, py = l2w(
                        x,
                        y,
                        th,
                        -lx / 2 + 1 + i * (lx - 2) / max(2, int(lx // 8)),
                        -ly / 2 + 1 + j * (ly - 2) / max(2, int(ly // 8)),
                    )
                    box('grey', px, py, z, dh, 0.5, 0.5, th)
            # ramp to the next deck along the long side
            ru0 = -lx / 2 + 3 if along_u else 0
            rv0 = 0 if along_u else -ly / 2 + 3
            x0, y0 = l2w(
                x, y, th, (-lx / 2 + 3) if along_u else (lx / 2 - 3.5), (ly / 2 - 3.5) if along_u else (-ly / 2 + 3)
            )
            x1, y1 = l2w(
                x, y, th, (lx / 2 - 3) if along_u else (lx / 2 - 3.5), (ly / 2 - 3.5) if along_u else (ly / 2 - 3)
            )
            pitched_slab('grey', x0, y0, z + 0.05, x1, y1, z + dh - 0.3, 4.0, 0.4)
            n = int((lx if along_u else ly) // 3.0)
            for c in range(n):
                if rng.random() < 0.5:
                    continue
                a = -(lx if along_u else ly) / 2 + 2 + (c + 0.5) * ((lx if along_u else ly) - 4) / n
                for side in (-1, 1):
                    b_ = side * ((ly if along_u else lx) / 2 - 7.5) - (3.5 if side > 0 else 0)
                    u, v = (a, b_) if along_u else (b_, a)
                    px, py = l2w(x, y, th, u, v)
                    row, length, fix, wt = rng.choices(CARS, weights=[c_[3] for c_ in CARS])[0]
                    add(row, px, py, z + 0.04, 1, 1, 1, th + (math.pi / 2 if along_u else 0) + math.radians(fix))
                    stats['cars'] += 1
            px, py = l2w(x, y, th, 0, 0)
            add(LAMP_SHORT, px, py, z, 0.7, 0.7, 0.7, th)
    stats['garages'] += 1
    stats.setdefault('sites', []).append((round(x), round(y), 'garage'))


for i, (x, y, lx, ly) in enumerate(lot_rects_big[:7]):
    if i < 4:
        construction_site(x, y, min(lx, 60), min(ly, 60), GRID_YAW, rng.randint(5, 9))
    else:
        parking_deck(x, y, min(lx, 60), min(ly, 60), GRID_YAW, rng.randint(3, 4))
# skybridges between facing box buildings across a street: from a ground-level box face >= 24 m tall, probe
# along its outward normal every 2 m from 6 to 44 m; the first building hit must be >= 16 m away (a street
# width) and >= 24 m tall, with a road at the midpoint. The deck is a floor slab, a roof slab and a glazed
# (blue cube) box 2.4 m tall at a random height 14 m .. (lower roof - 6 m). At most 12, none within 80 m of spawn.
bridges = 0
rng.shuffle(box_faces)
for cx, cy, lx, ly, th, h, kind in box_faces:
    if bridges >= 12 or h < 24 or near_origin(cx, cy, 80):
        continue
    for fx, fy, length, nyaw, u_edge, v_edge, nu, nv in rect_faces(cx, cy, lx, ly, th):
        if length < 12:
            continue
        gap = None
        for d in range(6, 46, 2):
            px, py = fx + d * math.cos(nyaw), fy + d * math.sin(nyaw)
            j = building_at(px, py, 0.0)
            if j is not None:
                if d >= 16 and building_rects[j][5] >= 24:
                    gap = (d, j)
                break
        if not gap or not road_nearby(fx + gap[0] / 2 * math.cos(nyaw), fy + gap[0] / 2 * math.sin(nyaw), 0):
            continue
        z = rng.uniform(14, min(h, building_rects[gap[1]][5]) - 6)
        mx, my = fx + gap[0] / 2 * math.cos(nyaw), fy + gap[0] / 2 * math.sin(nyaw)
        box('concrete', mx, my, Z_GROUND + z, 0.5, gap[0] + 1, 4.0, nyaw)
        box('concrete', mx, my, Z_GROUND + z + 3.4, 0.4, gap[0] + 1, 4.0, nyaw)
        add(CUBE['blue'], mx, my, Z_GROUND + z + 1.95, gap[0] + 1, 3.6, 2.4, nyaw)
        bridges += 1
        stats['skybridges'] += 1
        break

# ---- Park Avenue viaduct and other elevated roadways -------------------------
# The centreline file's level codes: 13 = at grade (built above), 17 / 21 / 22 = elevated. LEVEL_Z gives each
# elevated code a deck height (m, empirical: the viaduct round Grand Central). A line whose ends have different
# levels is a ramp: z is interpolated linearly along its length (unknown codes count as 0.3 m, i.e. ground),
# built from pitched slabs; level stretches are flat black boxes. Both get 1 m grey parapets and concrete piers
# every 14 m wherever the deck is above 2.5 m and not inside a building. Code 9 lines are skipped.
LEVEL_Z = {'17': 7.5, '21': 11.0, '22': 8.5}
for st in streets:
    f, t = st.get('from_level_code'), st.get('to_level_code')
    if f == '13' and t == '13' or f == '9' or t == '9':
        continue
    if f not in LEVEL_Z and t not in LEVEL_Z:
        continue
    w = min(max(float(st.get('streetwidth') or 32) * FT, 7.0), 20.0)
    g = st['the_geom']
    lines = g['coordinates'] if g['type'] == 'MultiLineString' else [g['coordinates']]
    for line in lines:
        pts = [proj(lon, lat) for lon, lat in line]
        total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        acc = 0
        z_from = LEVEL_Z.get(f, 0.3)
        z_to = LEVEL_Z.get(t, 0.3)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            if L < 1 or not in_range((x0 + x1) / 2, (y0 + y1) / 2, -w):
                acc += L
                continue
            za = z_from + (z_to - z_from) * acc / total
            zb = z_from + (z_to - z_from) * (acc + L) / total
            acc += L
            yaw = math.atan2(y1 - y0, x1 - x0)
            if abs(zb - za) > 0.05:
                pitched_slab('black', x0, y0, Z_GROUND + za + 0.6, x1, y1, Z_GROUND + zb + 0.6, w, 0.6)
                for side in (-1, 1):
                    ox, oy = -math.sin(yaw) * side * (w / 2 - 0.2), math.cos(yaw) * side * (w / 2 - 0.2)
                    pitched_slab(
                        'grey', x0 + ox, y0 + oy, Z_GROUND + za + 1.6, x1 + ox, y1 + oy, Z_GROUND + zb + 1.6, 0.4, 1.0
                    )
            else:
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                box('black', mx, my, Z_GROUND + za, 0.6, L + 1, w, yaw)
                for side in (-1, 1):
                    px, py = l2w(mx, my, yaw, 0, side * (w / 2 - 0.2))
                    box('grey', px, py, Z_GROUND + za + 0.6, 1.0, L + 1, 0.4, yaw)
            # piers under the deck
            n = max(1, int(L // 14))
            for i in range(n):
                tt = (i + 0.5) / n
                px, py = x0 + (x1 - x0) * tt, y0 + (y1 - y0) * tt
                zc = za + (zb - za) * tt
                if zc > 2.5 and not inside_building(px, py, 0.5):
                    box('concrete', px, py, Z_GROUND, zc, 1.4, min(w - 3, 6.0), yaw)
            stats['viaduct'] += 1

# ---- whole board: mid ring (1-2 km) and outer ring (2-3 km), rivers -----------
# The Empty board is a flat 6 km square; the flyable box is the central 2 km. Beyond it: the mid ring gets every
# building over 5 m as a box, roads with sidewalks and street trees, parks with paths; the outer ring gets
# buildings over 14 m, roads and lawns. The ring datasets were fetched for a +-4.3 km square (README).
BOARD = 3000.0  # half-size of the board, m


def zone(x, y):
    """'core' (|x|,|y| <= 1 km), 'mid' (<= 2 km), 'outer' (<= 2.96 km) or None beyond the board."""
    d = max(abs(x), abs(y))
    return 'core' if d <= MAX_RANGE else ('mid' if d <= 2000 else ('outer' if d <= BOARD - 40 else None))


box('concrete', 0, 0, Z_GROUND - 0.31, 0.30, 2 * BOARD, 2 * BOARD)  # ground slab under the whole board
# buildings: plain boxes on best_rect() footprints; core footprints are skipped (already built in full)
ring = json.load(open(os.path.join(DATA, 'ring_buildings.json')))
for b in ring:
    h = float(b.get('height_roof') or 0) * FT
    year = int(float(b.get('construction_year') or 0) or 0)
    g = b['the_geom']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in polys:
        pts = [proj(lon, lat) for lon, lat in poly[0][:-1]]
        if len(pts) < 3:
            continue
        ccx, ccy = centroid(pts)
        zn = zone(ccx, ccy)
        if zn in (None, 'core'):
            continue
        if h < 2.5:
            h = 4.0
        if (zn == 'mid' and (h < 5 or poly_area(pts) < 25)) or (zn == 'outer' and (h < 14 or poly_area(pts) < 60)):
            continue
        cx, cy, lx, ly, th = best_rect(pts)
        box(material_for(h, year, b['bin']), cx, cy, Z_GROUND, h, lx, ly, th)
        stats['ring_' + zn] += 1
# streets: mid ring gets roads + sidewalks + sparse trees, outer ring roads only. Same filters and intersection
# extension as the core streets, but fixed 4.5 m sidewalks and a tree every 32 m alternating sides.
rstreets = json.load(open(os.path.join(DATA, 'ring_streets.json')))
rnode_w = {}
for st in rstreets:
    w = min(max(float(st.get('streetwidth') or 32) * FT, 6.0), 26.0)
    for line in (
        st['the_geom']['coordinates']
        if st['the_geom']['type'] == 'MultiLineString'
        else [st['the_geom']['coordinates']]
    ):
        for k in (line[0], line[-1]):
            key = (round(k[0], 6), round(k[1], 6))
            rnode_w[key] = max(rnode_w.get(key, 0), w)
for st in rstreets:
    if st.get('from_level_code') not in (None, '13') or st.get('to_level_code') not in (None, '13'):
        continue
    if st.get('rw_type') not in ('1', '9', None):
        continue
    w = min(max(float(st.get('streetwidth') or 32) * FT, 6.0), 26.0)
    name = st.get('stname_label', '')
    ave = 'AVE' in name or 'BROADWAY' in name
    for line in (
        st['the_geom']['coordinates']
        if st['the_geom']['type'] == 'MultiLineString'
        else [st['the_geom']['coordinates']]
    ):
        pts = [proj(lon, lat) for lon, lat in line]
        for i, ((x0, y0), (x1, y1)) in enumerate(zip(pts, pts[1:])):
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            zn = zone(mx, my)
            L = math.hypot(x1 - x0, y1 - y0)
            if zn in (None, 'core') or L < 1:
                continue
            yaw = math.atan2(y1 - y0, x1 - x0)
            k0 = (round(line[i][0], 6), round(line[i][1], 6))
            k1 = (round(line[i + 1][0], 6), round(line[i + 1][1], 6))
            ext0 = rnode_w.get(k0, w) / 2 if i == 0 else 0
            ext1 = rnode_w.get(k1, w) / 2 if i == len(pts) - 2 else 0
            bx_, by_ = l2w(mx, my, yaw, (ext1 - ext0) / 2, 0)
            plane(ASPHALT, bx_, by_, Z_GROUND + (0.025 if ave else 0.02), L + ext0 + ext1, w, yaw)
            stats['ring_roads'] += 1
            if zn == 'mid':
                Lw = L - ext0 - ext1
                if Lw > 4:
                    off = (ext0 - ext1) / 2
                    for side in (1, -1):
                        sx_, sy_ = l2w(mx, my, yaw, off, side * (w / 2 + 2.25))
                        box('concrete', sx_, sy_, Z_GROUND, Z_WALK - 0.02 - Z_GROUND, Lw, 4.5, yaw)
                        plane(PAVE, sx_, sy_, Z_WALK, Lw, 4.5, yaw)
                        stats['ring_walks'] += 1
                    for j in range(int(Lw // 32)):
                        side = 1 if j % 2 == 0 else -1
                        u = off - Lw / 2 + (j + 0.5) * Lw / max(1, int(Lw // 32))
                        tx, ty = l2w(mx, my, yaw, u, side * (w / 2 + 1.3))
                        add(ELM if rng.random() < 0.6 else MAPLE, tx, ty, Z_WALK, 1, 1, 1, rng.uniform(0, 6.28))
                        stats['ring_trees'] += 1
# parks outside the core: lawns and trees (one per 110 m^2 in the mid ring, 300 m^2 outer), plus paths, bushes
# and rocks (rows 71 / 162 are rocks), benches and people in the mid ring. Polygons that cross the board edge
# (Central Park) are clipped first; 6 m raster, up to 60 rectangles each.
rparks = json.load(open(os.path.join(DATA, 'ring_parks.json')))
for pk in rparks:
    typ = pk.get('typecategory', '')
    if typ in ('Waterfront Facility',):
        continue
    g = pk['multipolygon']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in polys:
        pts = clip_to_square([proj(lon, lat) for lon, lat in poly[0][:-1]], BOARD - 40)
        if len(pts) < 3 or poly_area(pts) < 60:
            continue
        ccx, ccy = centroid(pts)
        zn = zone(ccx, ccy)
        if zn in (None, 'core'):
            continue
        for x, y, lx, ly, th in decompose_fine(pts, cell=6.0, max_rects=60):
            if zone(x, y) in (None, 'core'):
                continue
            lawn(x, y, Z_WALK + 0.03, lx, ly, th)
            if zn == 'mid':
                park_paths(x, y, lx, ly, th, Z_WALK + 0.05, cross=min(lx, ly) > 25)
            n = int(lx * ly / (110 if zn == 'mid' else 300))
            for _ in range(n):
                px, py = l2w(x, y, th, rng.uniform(-lx / 2 + 2, lx / 2 - 2), rng.uniform(-ly / 2 + 2, ly / 2 - 2))
                sc = rng.uniform(0.9, 1.4)
                add(rng.choice([ELM, MAPLE, ELM]), px, py, Z_WALK, sc, sc, sc, rng.uniform(0, 6.28))
                stats['ring_trees'] += 1
            if zn == 'mid':
                scatter_rect(
                    x,
                    y,
                    lx,
                    ly,
                    th,
                    [BUSH, BUSH2, 'NewRow_71', 'NewRow_162'],
                    max(1, int(lx * ly / 150)),
                    Z_WALK + 0.03,
                    (0.8, 1.3),
                    inset=1,
                )
                scatter_rect(x, y, lx, ly, th, PEOPLE_STAND + [BENCH], max(1, int(lx * ly / 200)), Z_WALK + 0.03)
            stats['ring_parks'] += 1
# rivers: water tiles wherever the shoreline-clipped census tracts show no land
tracts = json.load(open(os.path.join(DATA, 'land_tracts.json')))
land_polys = []  # (xmin, xmax, ymin, ymax, pts): bbox-prefiltered land polygons
for t in tracts:
    g = t['the_geom']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in polys:
        pts = [proj(lon, lat) for lon, lat in poly[0][:-1]]
        xs_ = [p[0] for p in pts]
        ys_ = [p[1] for p in pts]
        land_polys.append((min(xs_), max(xs_), min(ys_), max(ys_), pts))
for pk in rparks:  # parks are land too: the 2020 tracts leave Central Park uncovered
    g = pk['multipolygon']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in polys:
        pts = [proj(lon, lat) for lon, lat in poly[0][:-1]]
        if len(pts) < 3:
            continue
        xs_ = [p[0] for p in pts]
        ys_ = [p[1] for p in pts]
        land_polys.append((min(xs_), max(xs_), min(ys_), max(ys_), pts))


def on_land(x, y):
    """True if (x, y) lies in any land tract or park polygon (bounding-box test first)."""
    for x0, x1, y0, y1, pts in land_polys:
        if x0 <= x <= x1 and y0 <= y <= y1 and point_in_poly(x, y, pts):
            return True
    return False


# 100 m water tiles (the 4 m BP_meWater scaled 25x, 3x deep) outside the core wherever none of nine sample
# points (centre and +-33 m) is on land. The pivot is the water SURFACE, so Z_WATER is the surface height.
TILE = 100.0
Z_WATER = Z_GROUND + 0.10  # water surface: above the board (0.012) and the slabs
for i in range(int(2 * BOARD / TILE)):
    for j in range(int(2 * BOARD / TILE)):
        x, y = -BOARD + (i + 0.5) * TILE, -BOARD + (j + 0.5) * TILE
        if max(abs(x), abs(y)) < MAX_RANGE:
            continue
        if not any(on_land(x + dx, y + dy) for dx in (-33, 0, 33) for dy in (-33, 0, 33)):
            add(WATER, x, y, Z_WATER, TILE / 4, TILE / 4, 3.0)
            stats['water_tiles'] += 1


# ---- output ------------------------------------------------------------------
def tf(x, y, z, rot):
    """Transform dict (metres -> cm, unit scale) with a given rotation quaternion, for Race / CamLoc."""
    return dict(
        Rotation=rot,
        Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)),
        Scale3D=dict(X=1, Y=1, Z=1),
    )


# menu camera: 520 m along -X and 470 m along +Y from the ESB at 170 m, aimed at a point 150 m up its shaft
cam = (esb_x - 520.0, esb_y + 470.0, 170.0)
cam_yaw = math.degrees(math.atan2(esb_y - cam[1], esb_x - cam[0]))
cam_pitch = math.degrees(math.atan2(150 - cam[2], math.hypot(esb_x - cam[0], esb_y - cam[1])))


def thumbnail(path, title):
    """Render a 1024 px top-down Thumbnail.jpg of the core extent: every box, floor, mesh tile and tree footprint
    as a filled polygon (map +Y to the right, +X up), painted lowest first so tall buildings end up on top,
    masonry shaded lighter with height. Skips the huge ground slabs and thin floor surfaces."""
    from PIL import Image, ImageDraw

    W = 1024
    img = Image.new('RGB', (W, W), (18, 20, 24))
    d = ImageDraw.Draw(img)
    span = max(gx1 - gx0, gy1 - gy0)
    sc = W / span

    def px(x, y):
        """World metres -> image pixels (+Y right, +X up, centred on the core extent)."""
        return ((y - (gy0 + gy1) / 2) * sc + W / 2, W / 2 - (x - (gx0 + gx1) / 2) * sc)

    colors = dict(
        black=(40, 44, 52),
        grey=(120, 124, 130),
        concrete=(190, 180, 160),
        brick=(150, 85, 65),
        yellow=(230, 190, 40),
        mesh=(165, 170, 160),
        tree=(60, 110, 50),
        red=(200, 40, 40),
        green=(70, 140, 60),
        blue=(60, 120, 220),
        violet=(150, 90, 180),
        default=(230, 230, 230),
    )
    kind_of = {v: k for k, v in CUBE.items()}
    kind_of.update({CONCRETE: 'concrete', BRICK: 'brick'})
    kind_of.update({r: 'mesh' for r in MESHES})
    kind_of.update({ELM: 'tree', MAPLE: 'tree', SMALL_TREE: 'tree'})
    dims = {CONCRETE: (4, 4, 0.30), BRICK: (0.3, 4, 4)}
    dims.update({r: (m[0], m[1], m[2]) for r, m in MESHES.items()})
    items = []
    for row, trs in instances.items():
        k = kind_of.get(row)
        if not k:
            continue
        bx, by, bz = dims.get(row, (1, 1, 1))
        for t in trs:
            s = t['Scale3D']
            lx, ly, h = s['X'] * bx, s['Y'] * by, s['Z'] * bz
            if k == 'tree':
                lx = ly = 2.5
            if lx > 1500 or (k == 'concrete' and h < 0.5):
                continue
            items.append(
                (
                    t['Translation']['Z'] / 100 + h,
                    t['Translation']['X'] / 100,
                    t['Translation']['Y'] / 100,
                    lx,
                    ly,
                    2 * math.atan2(t['Rotation']['Z'], t['Rotation']['W']),
                    k,
                )
            )
    items.sort(key=lambda i: i[0])
    for ztop, x, y, lx, ly, yaw, k in items:
        c, s_ = math.cos(yaw), math.sin(yaw)
        corners_ = [
            px(x + ux * c - vy * s_, y + ux * s_ + vy * c)
            for ux, vy in ((-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2))
        ]
        col = colors[k]
        if k not in ('black', 'yellow', 'tree', 'default', 'red', 'green', 'blue', 'violet'):
            f = min(1.0, 0.55 + ztop / 400)
            col = tuple(int(v * f) for v in col)
        d.polygon(corners_, fill=col)
    d.text((24, W - 48), title, fill=(240, 240, 240))
    img.save(path, quality=88)


def write_map(folder, display, extra_rows=None, decals=None):
    """Write maps/<folder>/ (<folder>.json, .info, Thumbnail.jpg, Decals/) and install a copy into the game's
    MapEditor/User/<folder>/, replacing any previous build of both. Returns (installed path, instance count).

    The JSON follows the measured map format: S_AssetsTransform rows, BaseMapRow 'BaseBoard' (flat Empty board),
    an empty Race (Track: false in the .info, so the drone spawns at the board's PlayerStart), CamLoc = the menu
    camera and CustomWeather.northyaw = FRAME_ROT in degrees. `extra_rows` (the decal transforms) are merged in
    and `decals` (PNG name -> spec) are rendered and also copied into the editor's UserDecals and MapDecals
    libraries, which is where it loads user PNGs from."""
    rows_all = dict(instances)
    if extra_rows:
        rows_all.update(extra_rows)
    map_json = {
        'S_AssetsTransform': [
            dict(Rname=row, Transform=tr, UniqueGroupTag=['None'] * len(tr)) for row, tr in rows_all.items()
        ],
        'BaseMapRow': 'BaseBoard',
        'WeatherIndex': 0,
        'Race': dict(
            CheckPoints=[], StartTransform=tf(0, 0, 0, dict(X=0, Y=0, Z=0, W=1)), Laps=1, BestTime=-1, Spoints=[]
        ),
        'CamLoc': tf(cam[0], cam[1], cam[2], quat_pitch_yaw(cam_pitch, cam_yaw)),
        'CustomWeather': dict(timeOfDay=17.5, northyaw=round(math.degrees(FRAME_ROT), 2), Cloud=0.25),
    }
    info = {
        'BaseMapRow': 'BaseBoard',
        'Name': display,
        'CreatorSteamID': STEAM_ID,
        'CreationTimeUnix': int(time.time()),
        'Track': False,
    }
    out_dir = os.path.join(ROOT, 'maps', folder)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    json.dump(map_json, open(os.path.join(out_dir, folder + '.json'), 'w'))
    open(os.path.join(out_dir, folder + '.info'), 'w').write(json.dumps(info))
    if decals:
        ddir = os.path.join(out_dir, 'Decals')
        os.makedirs(ddir)
        for name, spec in decals.items():
            if spec[0] == 'win':
                window_png(spec[1], spec[2], spec[3], os.path.join(ddir, name))
            else:
                billboard_png(spec[1], os.path.join(ddir, name))
        for lib in (
            'UserDecals',
            'MapDecals',
        ):  # the editor loads user PNGs from these libraries (UI_MapEditor strings)
            ld = os.path.join(os.path.dirname(GAME_USER_MAPS), lib)
            os.makedirs(ld, exist_ok=True)
            for name in decals:
                shutil.copy(os.path.join(ddir, name), os.path.join(ld, name))
    thumbnail(os.path.join(out_dir, 'Thumbnail.jpg'), display)
    dst = os.path.join(GAME_USER_MAPS, folder)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(out_dir, dst)
    return dst, sum(len(v) for v in rows_all.values())


WITH_WINDOWS = (
    '--no-windows' not in sys.argv
)  # window-grid and billboard decals are part of the map unless --no-windows
d1, n1 = write_map(
    'NYC',
    'New York City - Midtown Manhattan',
    decal_rows if WITH_WINDOWS else None,
    decal_files if WITH_WINDOWS else None,
)
print(
    f"origin (5 Ave & 38 St) {lat0:.6f},{lon0:.6f}; frame rotated {math.degrees(FRAME_ROT):.1f} deg; grid yaw {math.degrees(GRID_YAW):.1f}; extent N {gx0:.0f}..{gx1:.0f} E {gy0:.0f}..{gy1:.0f} m"
)
print(dict(stats))
print(
    f"NYC: {n1} instances in {len(instances)} rows -> {d1}"
    + (
        f" (with {sum(len(v) for v in decal_rows.values())} decals, {len(decal_files)} textures)"
        if WITH_WINDOWS
        else ""
    )
)
print(
    'landmarks m: herald',
    [round(v) for v in herald],
    'duffy',
    [round(v) for v in duffy],
    'ts42',
    [round(v) for v in ts42],
    'esb',
    [round(esb_x), round(esb_y)],
)
print('bryant centre m:', [round(v) for v in bryant[0][:2]] if bryant else None)
print('top rows:', {r: len(v) for r, v in sorted(instances.items(), key=lambda kv: -len(kv[1]))[:16]})
