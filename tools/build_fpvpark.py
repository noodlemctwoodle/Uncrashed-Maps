#!/usr/bin/env python3
"""FPV Airspace Park: a dense freestyle + race map for Uncrashed on the Mountain landscape (BaseLandscape04).

Every object is placed on the real terrain, sampled from the level's decoded heightmap (tools/landscape.py; the
valley floor is -15.00 m at the spawn and only flat inside an irregular ~900 x 750 m bowl). Race storage follows
Workshop track maps (start and gate yaw = flight bearing - 90 deg; respawn 0 = start, then one per gate).
Advertising for FPV Airspace is solid geometry (cube letters, a fly-through logo); PNG decals only with --decals.
"""
import json, math, os, sys, time, hashlib, shutil, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from landscape import Landscape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
STEAM_ID = os.environ.get('UNCRASHED_STEAM_ID', '76561197969360950')   # your Steam ID64: the game loads maps from MapEditor/User under it
GAME_USER_MAPS = os.path.expanduser(f'~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User')
ROOKIE = '--rookie' in sys.argv
NAME, DISPLAY = ('FPVParkRookie', 'FPV Airspace Park: Rookie') if ROOKIE else ('FPVPark', 'FPV Airspace Park')
WITH_DECALS = '--no-decals' not in sys.argv
rng = random.Random(11)
LAND = Landscape(os.path.join(DATA, 'extracted/Uncrashed/Content/MapEditor/BaseLevel/L_BaseLandscape04'))
def gz(x, y):
    h = LAND.height_cm(x * 100, y * 100); return (h if h is not None else -1500.0) / 100.0
def has_ground(x, y): return LAND.height_cm(x * 100, y * 100) is not None
CATB = json.load(open(os.path.join(DATA, 'catalog.json')))
def rest(row):
    """Height to sink a mesh so its lowest point touches the ground: meshes whose base sits above their pivot (train
    boxcar 0.68 m) would otherwise hover. Meshes whose base is below the pivot (trees, rocks, houses) are left alone."""
    b = CATB.get(row, {}).get('bounds')
    if not b: return 0.0
    bot = (b['origin'][2] - b['extent'][2]) / 100.0; return -bot if bot > 0.05 else 0.0
def flat(x, y, r=0.0, tol=1.2):
    pts = [(x, y)] + ([(x + r, y), (x - r, y), (x, y + r), (x, y - r), (x + r * .7, y + r * .7), (x - r * .7, y - r * .7), (x + r * .7, y - r * .7), (x - r * .7, y + r * .7)] if r else [])
    hs = [gz(px, py) for px, py in pts]; return max(hs) - min(hs) <= tol
G0 = gz(0, 0)

# ---- rows ---------------------------------------------------------------------
CUBE = dict(default='NewRow_13', yellow='NewRow_46', blue='NewRow_79', red='NewRow_84', green='NewRow_268', grey='NewRow_256', violet='NewRow_378', black='NewRow_109')
CUBE_HOLE = dict(default='NewRow_39', yellow='NewRow_55', blue='NewRow_80', red='NewRow_85', black='NewRow_110', grey='NewRow_260', green='NewRow_270', violet='NewRow_379')
CYL = dict(default='NewRow_14', grey='NewRow_261', black='NewRow_113', yellow='NewRow_64', blue='NewRow_81', red='NewRow_89')
CONCRETE, BRICK = 'NewRow_303', 'NewRow_318'
FLOOR_HOLE_R, FLOOR_HOLE_SQ = 'NewRow_327', 'NewRow_330'
WALL_WIN = ['NewRow_207', 'NewRow_224', 'NewRow_214', 'NewRow_321', 'NewRow_348']; WALL_TRI = 'NewRow_237'
COLUMN, COLUMN_BRICK, STAIRS = 'NewRow_42', 'NewRow_122', 'NewRow_106'
PENTE, CORNER, COIN, COIN_HALF, COIN_ANGLE = 'NewRow_277', 'NewRow_317', 'NewRow_361', 'NewRow_362', 'NewRow_360'
ASPHALT, PAVE, DIRT, GRAVEL, SAND = 'NewRow_182', 'NewRow_185', 'NewRow_180', 'NewRow_181', 'NewRow_662'
WATER = 'NewRow_183'
CONTAINER_L, CONTAINER_S, TANK_CONT, BOXCAR = 'NewRow_1', 'NewRow_190', 'NewRow_48', 'NewRow_50'
HESCO, TIRE_WALL, TIRE_PILE, BARRIER, CONE, FENCE = 'NewRow_776', 'NewRow_291', 'NewRow_290', 'NewRow_100', 'NewRow_202', 'NewRow_777'
TURBINE, WINDMILL, WINDMILL_L, BALLOON = 'NewRow_344', 'NewRow_342', 'NewRow_339', 'NewRow_165'
CRANE_Y, CRANE_R, TOWER_CRANE = 'NewRow_338', 'NewRow_335', 'NewRow_201'
TRIBUNE, ARCH, RIG, TANK_V, SCAFFOLD_W, PIPES, PIPE = 'NewRow_271', 'NewRow_45', 'NewRow_35', 'NewRow_49', 'NewRow_157', 'NewRow_18', 'NewRow_156'
NEO_LG = ['NewRow_119', 'NewRow_123', 'NewRow_120']; NEO_MD = ['NewRow_129', 'NewRow_11']; NEO_DOME, NEO_SM = 'NewRow_118', ['NewRow_10', 'NewRow_24', 'NewRow_23']
STATUE = 'NewRow_213'
TENT_CANOPY, TENT, TENT_BIG, SIGN, LED_V, GENERATOR = 'NewRow_245', 'NewRow_687', 'NewRow_770', 'NewRow_798', 'NewRow_217', 'NewRow_263'
TABLE, CHAIR, BENCH, DUMPSTER, PALLET, BARREL, CRATE = 'NewRow_353', 'NewRow_352', 'NewRow_204', 'NewRow_52', 'NewRow_54', 'NewRow_187', 'NewRow_189'
PEOPLE = ['NewRow_252', 'NewRow_255', 'NewRow_801', 'NewRow_802']; PEOPLE_SIT = ['NewRow_254', 'NewRow_800']
CARS = ['NewRow_103', 'NewRow_257', 'NewRow_93', 'NewRow_775']; FORKLIFT, BOAT, TRACTOR = 'NewRow_196', 'NewRow_329', 'NewRow_297'
PINES = ['NewRow_279', 'NewRow_280', 'NewRow_281']; TREES = ['NewRow_168', 'NewRow_269', 'NewRow_34']; BIG_TREES = ['NewRow_78', 'NewRow_169']; BUSHES = ['NewRow_164', 'NewRow_226']; ROCKS = ['NewRow_71', 'NewRow_162']; CLIFF = 'NewRow_175'
LAMP_TALL, LAMP_SHORT, NEONS = 'NewRow_3', 'NewRow_20', ['NewRow_4', 'NewRow_148', 'NewRow_343']
BALLOONS_SMALL = ['NewRow_104', 'NewRow_105', 'NewRow_107']; HANDRAIL, HAY = 'NewRow_276', ['NewRow_315', 'NewRow_316']
GRAFFITI = ['NewRow_706', 'NewRow_705', 'NewRow_763', 'NewRow_764', 'NewRow_766', 'NewRow_765', 'NewRow_768', 'NewRow_767', 'NewRow_762', 'NewRow_761', 'NewRow_701']
POLE, BARN, SILO, HOUSES = 'NewRow_74', 'NewRow_310', 'NewRow_322', ['NewRow_788', 'NewRow_789', 'NewRow_790', 'NewRow_791', 'NewRow_793']
OFFICE = ['NewRow_794', 'NewRow_795', 'NewRow_796', 'NewRow_797']; WORKSHOP = ['NewRow_95', 'NewRow_96', 'NewRow_97', 'NewRow_98']
GATE_PIVOT = {'DefaultGate': 1.0, 'DefaultOneW': 1.0, 'STARTGATE': 1.0, 'Invisible': 1.5, 'InflRond02': 1.73}

instances = {}; decal_rows = {}; decal_files = {}; stats = {}
def st(k, n=1): stats[k] = stats.get(k, 0) + n
def quat_yaw(yaw): return dict(X=0.0, Y=0.0, Z=math.sin(yaw / 2), W=math.cos(yaw / 2))
def quat_pitch_yaw(pitch_deg, yaw_deg):
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2
    SP, CP, SY, CY = math.sin(P), math.cos(P), math.sin(Y), math.cos(Y)
    return dict(X=SP * SY, Y=-SP * CY, Z=CP * SY, W=CP * CY)

def quat_from_axes(X, Y, Z):
    """Quaternion (X,Y,Z,W) whose rotation maps local axes onto the given orthonormal world vectors."""
    m = [[X[0], Y[0], Z[0]], [X[1], Y[1], Z[1]], [X[2], Y[2], Z[2]]]
    t = m[0][0] + m[1][1] + m[2][2]
    if t > 0:
        s = math.sqrt(t + 1) * 2; w = s / 4; x = (m[2][1] - m[1][2]) / s; y = (m[0][2] - m[2][0]) / s; z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1 + m[0][0] - m[1][1] - m[2][2]) * 2; w = (m[2][1] - m[1][2]) / s; x = s / 4; y = (m[0][1] + m[1][0]) / s; z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1 + m[1][1] - m[0][0] - m[2][2]) * 2; w = (m[0][2] - m[2][0]) / s; x = (m[0][1] + m[1][0]) / s; y = s / 4; z = (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1 + m[2][2] - m[0][0] - m[1][1]) * 2; w = (m[1][0] - m[0][1]) / s; x = (m[0][2] + m[2][0]) / s; y = (m[1][2] + m[2][1]) / s; z = s / 4
    return dict(X=x, Y=y, Z=z, W=w)
def decal_rot(normal_yaw):
    """Wall decal basis as the editor places them and as UE's decal shader expects: X into the surface (projection
    direction), Y straight down (texture V), Z = X x Y along the wall (texture U). Scale: X depth, Y height/4, Z width/4."""
    c, s = math.cos(normal_yaw), math.sin(normal_yaw)
    X = (-c, -s, 0.0); Y = (0.0, 0.0, -1.0); Z = (s, -c, 0.0)
    return quat_from_axes(X, Y, Z)
def tf(x, y, z, rot, s=(1, 1, 1)):
    return dict(Rotation=rot, Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)), Scale3D=dict(X=round(s[0], 4), Y=round(s[1], 4), Z=round(s[2], 4)))
def add(row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0, rot=None, store=None):
    (store if store is not None else instances).setdefault(row, []).append(tf(x, y, z, rot if rot else quat_yaw(yaw), (sx, sy, sz)))
def box(kind, cx, cy, z0, h, lx, ly, yaw=0.0):
    lx, ly, h = max(lx, 0.1), max(ly, 0.1), max(h, 0.01)
    if kind == 'concrete': sz = h / 0.30; add(CONCRETE, cx, cy, z0 + 0.29 * sz, lx / 4, ly / 4, sz, yaw)
    elif kind == 'brick': add(BRICK, cx, cy, z0, lx / 0.3, ly / 4, h / 4, yaw)
    else: add(CUBE[kind], cx, cy, z0 + h / 2, lx, ly, h, yaw)
def cylinder(kind, cx, cy, z0, h, d): add(CYL[kind], cx, cy, z0 + h / 2, d, d, h)
def plane(row, x, y, z_top, lx, ly, yaw=0.0): add(row, x, y, z_top - 0.05, lx / 4, ly / 4, 1.0, yaw)
def pitched(kind, x0, y0, z0, x1, y1, z1, width, thick=0.4):
    L = math.hypot(x1 - x0, y1 - y0); yaw = math.degrees(math.atan2(y1 - y0, x1 - x0)); pitch = math.degrees(math.atan2(z1 - z0, L))
    add(CUBE[kind], (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2 - thick / 2, math.hypot(L, z1 - z0), width, thick, rot=quat_pitch_yaw(pitch, yaw))
def l2w(cx, cy, yaw, u, v): c, s = math.cos(yaw), math.sin(yaw); return cx + u * c - v * s, cy + u * s + v * c
def ground(x, y): return gz(x, y)
def put(row, x, y, dz=0.0, sx=1.0, sy=1.0, sz=1.0, yaw=0.0):
    if not has_ground(x, y): st('skipped_off_landscape'); return
    add(row, x, y, ground(x, y) + dz + rest(row) * sz, sx, sy, sz, yaw)
def post(kind, x, y, h, lx, ly, yaw=0.0, top=None):
    """Vertical member standing on the terrain at its own (x, y), with a 1 m footing sunk into the ground so slopes
    never leave a gap under it. `top` (absolute) overrides the height so columns of one structure share a top."""
    g = ground(x, y); z1 = top if top is not None else g + h; box(kind, x, y, g - 1.0, z1 - g + 1.0, lx, ly, yaw)
TUBES = []
def tube(x0, y0, z0, x1, y1, z1, r, strict=True):
    """A flight gap the feature promises: props are cleared out of it; `strict` also forbids any structure in it."""
    TUBES.append((x0, y0, z0, x1, y1, z1, r, strict))
def scatter(rows, cx, cy, lx, ly, n, dz=0.0, yaw=0.0, scale=(1, 1), need_flat=False):
    for _ in range(n):
        x, y = l2w(cx, cy, yaw, rng.uniform(-lx / 2, lx / 2), rng.uniform(-ly / 2, ly / 2)); s = rng.uniform(*scale)
        if need_flat and not flat(x, y, 2): continue
        put(rng.choice(rows), x, y, dz, s, s, s, rng.uniform(0, 6.28))
def people(cx, cy, r, n, dz=0.0, face=None):
    for _ in range(n):
        a = rng.uniform(0, 6.28); d = rng.uniform(0, r); x, y = cx + d * math.cos(a), cy + d * math.sin(a)
        put(rng.choice(PEOPLE), x, y, dz, 1, 1, 1, (math.atan2(face[1] - y, face[0] - x) if face else rng.uniform(0, 6.28)))
def pad(row, cx, cy, lx, ly, yaw=0.0):
    """Ground plane on terrain. Zones are flat within 1.2 m, not perfectly flat, so a 1.5 m concrete skirt under the
    plane hides any gap where the ground falls away and the plane reads as a raised slab, never a floating sheet."""
    top = ground(cx, cy) + 0.03; plane(row, cx, cy, top, lx, ly, yaw)
    if lx * ly > 150: box('concrete', cx, cy, top - 2.05, 2.0, lx, ly, yaw)

# ---- cube-letter signage (5 x 7 font) -----------------------------------------
FONT = {
 'A': ['01110','10001','10001','11111','10001','10001','10001'], 'C': ['01111','10000','10000','10000','10000','10000','01111'],
 'E': ['11111','10000','10000','11110','10000','10000','11111'], 'F': ['11111','10000','10000','11110','10000','10000','10000'],
 'I': ['11111','00100','00100','00100','00100','00100','11111'], 'P': ['11110','10001','10001','11110','10000','10000','10000'],
 'R': ['11110','10001','10001','11110','10100','10010','10001'], 'S': ['01111','10000','10000','01110','00001','00001','11110'],
 'V': ['10001','10001','10001','10001','10001','01010','00100'], 'L': ['10000','10000','10000','10000','10000','10000','11111'],
 'Y': ['10001','10001','01010','00100','00100','00100','00100'], 'N': ['10001','11001','10101','10011','10001','10001','10001'],
 'O': ['01110','10001','10001','10001','10001','10001','01110'], 'U': ['10001','10001','10001','10001','10001','10001','01110'],
 'K': ['10001','10010','10100','11000','10100','10010','10001'], 'H': ['10001','10001','10001','11111','10001','10001','10001'],
 'D': ['11110','10001','10001','10001','10001','10001','11110'], 'T': ['11111','00100','00100','00100','00100','00100','00100'],
 'G': ['01111','10000','10000','10111','10001','10001','01111'], 'M': ['10001','11011','10101','10101','10001','10001','10001'],
 'W': ['10001','10001','10001','10101','10101','11011','10001'], 'B': ['11110','10001','10001','11110','10001','10001','11110'],
 '-': ['00000','00000','00000','11111','00000','00000','00000'], '.': ['00000','00000','00000','00000','00000','00000','00100'], ' ': ['00000'] * 7,
}
def cube_text(text, x, y, yaw, cell=1.0, z0=None, colour='default', on_terrain=True, standing=True):
    """Letters built from cubes. Text runs along local +Y (left to right when viewed from +X side), standing upright (height = 7 cells)."""
    cols = len(text) * 6 - 1; u0 = -cols * cell / 2
    for ci, ch in enumerate(text.upper()):
        g = FONT.get(ch, FONT[' '])
        for r in range(7):
            for c in range(5):
                if g[r][c] != '1': continue
                v = u0 + (ci * 6 + c) * cell + cell / 2
                px, py = l2w(x, y, yaw, 0, v)
                zb = (ground(px, py) if on_terrain else z0) + (6 - r) * cell + 0.05
                add(CUBE[colour], px, py, zb + cell / 2, cell * 0.95, cell * 0.95, cell * 0.95, yaw); st('letter_cubes')
    if standing and not on_terrain:                                # baseline bar only for signs on a flat built base
        px, py = l2w(x, y, yaw, 0, 0); box('black', px, py, ground(px, py) - 0.3, 0.35, cell * 1.2, cols * cell + cell, yaw)
def logo_3d(x, y, yaw, size=10.0):
    """FPV Airspace quad logo as a fly-through sculpture: four blue cube-rings on the arms of an X, a square centre."""
    base = ground(x, y) + 4.0; r = size * 0.42; ring = size * 0.34
    for a in (0.785, 2.356, 3.927, 5.498):
        px, py = l2w(x, y, yaw, 0, 0); cx_, cy_ = px + r * math.cos(yaw + a) * 0, py   # keep in a vertical plane: offsets in (v, z)
        v = r * math.cos(a); zz = r * math.sin(a); qx, qy = l2w(x, y, yaw, 0, v)
        add(CUBE_HOLE['blue'], qx, qy, base + size / 2 + zz, ring, ring, ring, yaw + math.pi / 2)   # hole axis along local X (fly through)
        ax_, ay_ = l2w(x, y, yaw, 0, v / 2); add(CUBE['blue'], ax_, ay_, base + size / 2 + zz / 2, 0.5, 0.5, math.hypot(v, zz), rot=quat_pitch_yaw(math.degrees(math.atan2(zz, v)) * (1 if v != 0 else 1), math.degrees(yaw) + 90))
    add(CUBE['blue'], x, y, base + size / 2, 0.9, size * 0.22, size * 0.22, yaw)
    add(CUBE['default'], x, y, base + size / 2, 1.0, size * 0.08, size * 0.08, yaw)
    for s in (-1, 1): cylinder('grey', *l2w(x, y, yaw, 0, s * size * 0.55), ground(x, y), 4.0, 0.6)
    st('logos')

# ---- decals (opt-in) -----------------------------------------------------------
STRAPS = ['Can I legally take off and fly here?', 'Airspace  ·  NOTAMs  ·  Rights of way  ·  Weather', 'Where a drone can legally take off and fly in the UK', 'Pre-flight briefing in one tap']
def billboard_png(i, path, wide=True):
    from PIL import Image, ImageDraw, ImageFont
    W, H = (1536, 768) if wide else (768, 768); img = Image.new('RGBA', (W, H), (18, 24, 40, 255)); d = ImageDraw.Draw(img)
    icon = Image.open(os.path.join(DATA, 'fpv_airspace_icon.png')).convert('RGBA'); ic = int(H * 0.62); icon = icon.resize((ic, ic))
    mask = Image.new('L', (ic, ic), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, ic, ic), radius=ic // 5, fill=255)
    def font(sz):
        for f in ('/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/System/Library/Fonts/Helvetica.ttc'):
            try: return ImageFont.truetype(f, sz)
            except Exception: pass
        return ImageFont.load_default()
    def fit(text, max_w, start):
        sz = start
        while sz > 10:
            f_ = font(sz); bb = d.textbbox((0, 0), text, font=f_)
            if bb[2] - bb[0] <= max_w: return f_
            sz -= 4
        return font(10)
    if wide:
        img.paste(icon, (int(H * 0.12), int(H * 0.19)), mask); x0 = int(H * 0.85); maxw = W - x0 - int(H * 0.1)
        d.text((x0, int(H * 0.2)), 'FPV AIRSPACE', fill=(255, 255, 255, 255), font=fit('FPV AIRSPACE', maxw, int(H * 0.2)))
        d.text((x0, int(H * 0.5)), STRAPS[i % len(STRAPS)], fill=(120, 190, 255, 255), font=fit(STRAPS[i % len(STRAPS)], maxw, int(H * 0.075)))
        d.text((x0, int(H * 0.66)), 'fpv-airspace.app', fill=(200, 215, 235, 255), font=fit('fpv-airspace.app', maxw, int(H * 0.08)))
    else:
        img.paste(icon, ((W - ic) // 2, int(H * 0.06)), mask)
        f1 = fit('FPV AIRSPACE', int(W * 0.86), int(W * 0.12)); bb = d.textbbox((0, 0), 'FPV AIRSPACE', font=f1)
        d.text(((W - (bb[2] - bb[0])) / 2, int(H * 0.72)), 'FPV AIRSPACE', fill=(255, 255, 255, 255), font=f1)
    d.rectangle((0, 0, W - 1, H - 1), outline=(70, 140, 255, 255), width=14); img.save(path)
def decal(key, x, y, z, w, h, normal_yaw, wide=True, variant=0):
    if not WITH_DECALS: return
    name = 'decal_1791500000-' + hashlib.md5(key.encode()).hexdigest().upper() + '.png'; decal_files[name] = (variant, wide)
    add(name, x, y, z, 2.0, h / 4, w / 4, rot=decal_rot(normal_yaw), store=decal_rows); st('ad_decals')
def billboard(x, y, yaw, w=24.0, h=8.0, post_h=5.0, variant=0):
    """Free-standing two-sided board on posts with the FPV Airspace artwork as decals; yaw = facing direction of the front."""
    g = ground(x, y)
    for s in (-1, 1): cylinder('grey', *l2w(x, y, yaw, 0, s * (w / 2 - 1.2)), g, post_h + h, 0.5)
    box('black', x, y, g + post_h, h, 0.4, w, yaw)
    for side in (1, -1):
        fx, fy = l2w(x, y, yaw, side * 0.2, 0); decal(f'bb{variant}', fx, fy, g + post_h + h / 2, w - 0.6, h - 0.4, yaw + (0 if side > 0 else math.pi), wide=True, variant=variant)
    for s in (-1, 1): put(LAMP_SHORT, *l2w(x, y, yaw, 2.0, s * (w / 2 + 0.5)), 0, 1, 1, 1, yaw)
    occupied.append((x, y, 24)); st('billboards')

# ---- zone helpers ---------------------------------------------------------------
def bando(bx, by, bl, bw, yaw, floors=3):
    pad(DIRT, bx, by, bl + 16, bw + 16, yaw); g = ground(bx, by)
    for k in range(floors):
        z = g + k * 4.0
        for (u0, v0, u1, v1) in ((-bl / 2, -bw / 2, bl / 2, -bw / 2), (-bl / 2, bw / 2, bl / 2, bw / 2), (-bl / 2, -bw / 2, -bl / 2, bw / 2), (bl / 2, -bw / 2, bl / 2, bw / 2)):
            L = math.hypot(u1 - u0, v1 - v0); n = int(L // 4); ang = math.atan2(v1 - v0, u1 - u0)
            for i in range(n):
                if rng.random() < 0.18: continue
                t = (i + 0.5) / n; x, y = l2w(bx, by, yaw, u0 + (u1 - u0) * t, v0 + (v1 - v0) * t)
                add(rng.choice(WALL_WIN) if rng.random() < 0.75 else BRICK, x, y, z, 1, 1, 1, yaw + ang - math.pi / 2)
        if k > 0:
            for i in range(int(bl // 4)):
                for j in range(int(bw // 4)):
                    if rng.random() < 0.22: continue
                    x, y = l2w(bx, by, yaw, -bl / 2 + 2 + i * 4, -bw / 2 + 2 + j * 4); row = rng.choice([CONCRETE, CONCRETE, FLOOR_HOLE_R, FLOOR_HOLE_SQ]); add(row, x, y, z, 1, 1, 1, yaw)
                    if row == CONCRETE and rng.random() < 0.25: add(rng.choice([BARREL, PALLET, CRATE]), *l2w(x, y, yaw, rng.uniform(-1, 1), rng.uniform(-1, 1)), z, 1, 1, 1, rng.uniform(0, 6.28))   # props only on solid tiles
        for i in range(int(bl // 8) + 1):
            for j in range(int(bw // 8) + 1):
                x, y = l2w(bx, by, yaw, -bl / 2 + i * 8, -bw / 2 + j * 8); add(COLUMN_BRICK, x, y, z, 1, 1, 1, yaw)
    for i in range(int(bl // 4)):
        for j in range(int(bw // 4)):
            if rng.random() < 0.45: continue
            x, y = l2w(bx, by, yaw, -bl / 2 + 2 + i * 4, -bw / 2 + 2 + j * 4); add(CONCRETE, x, y, g + floors * 4.0, 1, 1, 1, yaw)
    for k in range(floors - 1): add(STAIRS, *l2w(bx, by, yaw, -bl / 2 + 3, bw / 2 - 3), g + k * 4, 1, 1, 1, yaw)
    scatter([BARREL, PALLET, CRATE, DUMPSTER, TIRE_PILE], bx, by, bl - 6, bw - 6, int(bl * bw / 30), 0, yaw)
    for i in range(10):
        side = rng.choice(((0, -bw / 2, -math.pi / 2), (0, bw / 2, math.pi / 2), (-bl / 2, 0, math.pi), (bl / 2, 0, 0.0)))
        t = rng.uniform(-0.4, 0.4); u = side[0] + (t * bl if side[0] == 0 else 0); v = side[1] + (t * bw if side[1] == 0 else 0)
        x, y = l2w(bx, by, yaw, u, v); nyaw = yaw + side[2]
        add(rng.choice(GRAFFITI), x - 0.15 * math.cos(nyaw), y - 0.15 * math.sin(nyaw), g + rng.uniform(1.2, 2.6), 1, rng.uniform(1.2, 2.2), rng.uniform(1.0, 1.6), nyaw)
    scatter([DUMPSTER, PALLET, BARREL, CONE, BARRIER, 'NewRow_93'], *l2w(bx, by, yaw, 0, bw / 2 + 7), bl, 6, 8, 0, yaw)
    for i in range(3): add(rng.choice(NEONS), *l2w(bx, by, yaw, -bl / 3 + i * bl / 3, -bw / 2 - 0.4), g + 3.0, 1, 1, 1, yaw)
    st('bandos')
def dive_tower(tx, ty, levels=10, step=5.0):
    pad(GRAVEL, tx, ty, 30, 30); g = ground(tx, ty)
    for (u, v) in ((-4, -4), (4, -4), (4, 4), (-4, 4)): post('grey', tx + u, ty + v, 0, 0.5, 0.5, top=g + (levels + 1) * step)
    tube(tx, ty, g + 1.0, tx, ty, g + (levels + 1) * step + 4, 1.2, strict=False)
    for k in range(levels + 1):
        z = g + k * step
        if k > 0: add(FLOOR_HOLE_SQ, tx, ty, z, 2.0, 2.0, 1.0, (k % 2) * math.pi / 4)
        for i in range(4):
            a = i * math.pi / 2; add(rng.choice(NEONS), tx + 4.3 * math.cos(a), ty + 4.3 * math.sin(a), z + step / 2, 1, 1, 1, a + math.pi / 2)
    top = g + levels * step + step
    box('concrete', tx, ty, top, 0.3, 10, 10); add(LED_V, tx, ty + 5.2, top + 0.3, 2.0, 1, 1.2, 0)
    scatter([CONE, BARRIER, TIRE_PILE], tx, ty, 24, 24, 8); st('dive_towers')
    return top
def gap_field(fx, fy, yaw=0.0):
    pad(ASPHALT, fx, fy, 90, 80, yaw)
    for i in range(7):
        x, y = l2w(fx, fy, yaw, -30 + i * 10, -25 + (i % 2) * 6); put(CONTAINER_L, x, y, 0, 1, 1, 1, yaw)
        if i % 2 == 0: add(CONTAINER_S, x, y, ground(x, y) + 3.0, 1, 1, 1, yaw + 0.2)
    for i in range(5):
        x, y = l2w(fx, fy, yaw, -20 + i * 10, 5); put(CUBE_HOLE['grey'] if i % 2 else CUBE_HOLE['blue'], x, y, 2.2, 4 + i * 3, 4.4, 4.4, yaw + math.pi / 2)
    for i in range(8): put(TIRE_WALL, *l2w(fx, fy, yaw, -32 + i * 9, 25), 0, 1, 1, 1, yaw + 0.4 * (i % 2))
    for i in range(6): put(HESCO, *l2w(fx, fy, yaw, -25 + i * 10, 35), 0, 2, 2, 2, yaw)
    scatter([CONE, BARRIER, TIRE_PILE, 'NewRow_150'], fx, fy, 70, 60, 16, 0, yaw)
    for i in range(4): put(ARCH, *l2w(fx, fy, yaw, -30 + i * 20, -40), 0, 1.4, 1.4, 1.4, yaw)
    st('gap_fields')
def skatepark(sx, sy, yaw=0.0):
    pad(PAVE, sx, sy, 50, 40, yaw); g = ground(sx, sy)
    for (u, v, y2) in ((-18, 0, 0), (18, 0, math.pi), (0, -14, math.pi / 2), (0, 14, -math.pi / 2)): add(PENTE, *l2w(sx, sy, yaw, u, v), g + 1.5, 6, 10, 3, yaw + y2)
    for (u, v) in ((-18, -14), (18, -14), (18, 14), (-18, 14)): add(CORNER, *l2w(sx, sy, yaw, u, v), g + 1.5, 6, 6, 3, yaw + math.atan2(v, u))
    add(COIN, sx, sy, g + 0.3, 2.0, 2.0, 2.0, yaw); add(COIN_HALF, *l2w(sx, sy, yaw, -8, 6), g + 0.3, 1.5, 1.5, 1.5, yaw + 1.0); add(COIN_ANGLE, *l2w(sx, sy, yaw, 8, -6), g + 0.3, 1.5, 1.5, 1.5, yaw + 2.0)
    bx_, by_ = l2w(sx, sy, yaw, 0, -7); box('concrete', bx_, by_, g, 1.2, 8, 2, yaw)
    for du in (-2, 2): add(HANDRAIL, *l2w(sx, sy, yaw, du, -7), g + 1.2, 1, 1, 1, yaw)
    x0, y0 = l2w(sx, sy, yaw, -6, 8); x1, y1 = l2w(sx, sy, yaw, 6, 8); pitched('grey', x0, y0, g + 0.05, x1, y1, g + 2.4, 3.0)
    people(*l2w(sx, sy, yaw, 0, 18), 8, 8); scatter([BENCH, CONE], *l2w(sx, sy, yaw, 0, 20), 40, 4, 5, 0, yaw)
    for i in range(4): add(rng.choice(NEONS), *l2w(sx, sy, yaw, -15 + i * 10, -19), g + 2.0, 1, 1, 1, yaw)
    st('skateparks')
def forest(cx, cy, lx, ly, n):
    for _ in range(n):
        x, y = cx + rng.uniform(-lx / 2, lx / 2), cy + rng.uniform(-ly / 2, ly / 2); s = rng.uniform(0.8, 1.3)
        put(rng.choice(PINES + PINES + TREES), x, y, 0, s, s, s, rng.uniform(0, 6.28))
    scatter(ROCKS + BUSHES, cx, cy, lx, ly, n // 3, 0, scale=(0.8, 1.6)); st('forests')
def crane_yard(cx, cy, yaw=0.0):
    pad(ASPHALT, cx, cy, 110, 90, yaw)
    put(CRANE_R, *l2w(cx, cy, yaw, 40, 30), 0, 1, 1, 1, yaw + 0.6); put(CRANE_Y, *l2w(cx, cy, yaw, -40, -30), 0, 1, 1, 1, yaw + 2.4); put(TOWER_CRANE, *l2w(cx, cy, yaw, 10, -40), 0, 1.8, 1.8, 1.8, yaw + 1.0)
    for i in range(4):
        for j in range(3):
            for k in range(3 if (i + j) % 2 == 0 else 2):
                x, y = l2w(cx, cy, yaw, -25 + i * 7, -15 + j * 8); add(rng.choice([CONTAINER_S, CONTAINER_S, TANK_CONT]), x, y, ground(x, y) + k * 2.6, 1, 1, 1, yaw + math.pi / 2)
    put(BOXCAR, *l2w(cx, cy, yaw, 10, 20), 0, 1, 1, 1, yaw); put(BOXCAR, *l2w(cx, cy, yaw, 25, 20), 0, 1, 1, 1, yaw); put(FORKLIFT, *l2w(cx, cy, yaw, -5, 10), 0, 1, 1, 1, yaw + 0.8)
    scatter([PALLET, CRATE, BARREL, CONE], cx, cy, 90, 70, 16, 0, yaw); people(cx, cy, 10, 4)
    for u in range(-50, 55, 10): put(LAMP_TALL, *l2w(cx, cy, yaw, u, -42), 0, 1, 1, 1, yaw); st('crane_yards')
def lake(lx_, ly_, a=55, b=38):
    g = ground(lx_, ly_); pad(SAND, lx_, ly_, 2 * a + 30, 2 * b + 30)
    for i in range(-16, 16):
        for j in range(-12, 12):
            x, y = lx_ + i * 4 + 2, ly_ + j * 4 + 2
            if (x - lx_) ** 2 / a ** 2 + (y - ly_) ** 2 / b ** 2 <= 1: add(WATER, x, y, g + 0.12, 1.0, 1.0, 1.5)
    for i in range(10): box('concrete', lx_ - a - 2 + i * 2.2, ly_, g + 0.3, 0.3, 2.0, 3.0)
    pitched('grey', lx_ - 20, ly_ + b + 12, g + 0.05, lx_ - 20, ly_ + b + 38, g + 6.0, 5.0)
    add(BOAT, lx_ + 10, ly_ + 12, g + 0.1, 1, 1, 1, 0.5); add(BOAT, lx_ + 25, ly_ - 15, g + 0.1, 1, 1, 1, 2.0)
    scatter(ROCKS, lx_, ly_ + b + 6, 2 * a, 8, 10); scatter(ROCKS, lx_, ly_ - b - 6, 2 * a, 8, 10); st('lakes')
def jump_track(pts):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0); yaw = math.atan2(y1 - y0, x1 - x0)
        for k in range(int(L // 8)):
            t = (k + 0.5) * 8 / L; px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if free(px, py, 5): pad(DIRT, px, py, 9, 10, yaw)
        for k in range(1, int(L // 28) + 1):
            t = k * 28 / L; jx, jy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t; g = ground(jx, jy)
            if not free(jx, jy, 8): continue
            ax, ay = jx - 6 * math.cos(yaw), jy - 6 * math.sin(yaw); bx_, by_ = jx + 6 * math.cos(yaw), jy + 6 * math.sin(yaw)
            pitched('grey', ax, ay, g + 0.05, jx, jy, g + 2.6, 6.0); pitched('grey', jx, jy, g + 2.6, bx_, by_, g + 0.05, 6.0)
            for s in (-1, 1): put(TIRE_PILE, *l2w(jx, jy, yaw, 0, s * 4.5), 0); st('jumps')
def scaffold_tower(x, y, levels=5):
    for k in range(levels): add(SCAFFOLD_W, x, y, ground(x, y) + k * 4.2, 1.4, 1.4, 1.0, 0)
    top = ground(x, y) + levels * 4.2; box('concrete', x, y, top, 0.3, 4, 4); add(rng.choice(NEONS), x, y + 2.1, top + 1.5, 1, 1, 1, 0); st('scaffold_towers')
def farm(cx, cy, yaw=0.0):
    pad(DIRT, cx, cy, 70, 50, yaw); put(BARN, *l2w(cx, cy, yaw, -15, 0), 0, 1, 1, 1, yaw); put(SILO, *l2w(cx, cy, yaw, 12, 12), 0, 1, 1, 1, yaw); put(SILO, *l2w(cx, cy, yaw, 20, 12), 0, 1, 1, 1, yaw)
    put(TRACTOR, *l2w(cx, cy, yaw, 15, -12), 0, 1, 1, 1, yaw + 1.2); scatter(HAY, cx, cy, 60, 40, 30, 0, yaw); put(WINDMILL, *l2w(cx, cy, yaw, 28, -18), 0, 1, 1, 1, yaw); st('farms')
def village(cx, cy, yaw=0.0):
    pad(GRAVEL, cx, cy, 80, 60, yaw)
    for i, r in enumerate(HOUSES): put(r, *l2w(cx, cy, yaw, -30 + i * 15, (i % 2) * 24 - 12), 0, 1, 1, 1, yaw + (i % 2) * math.pi)
    for i, r in enumerate(WORKSHOP): put(r, *l2w(cx, cy, yaw, -30 + i * 18, 24), 0, 1, 1, 1, yaw + math.pi)
    scatter(CARS + [DUMPSTER, BENCH], cx, cy, 70, 10, 8, 0.05, yaw); scatter(TREES + BUSHES, cx, cy, 80, 60, 14, 0, yaw); people(cx, cy, 25, 10); st('villages')
def office_block(cx, cy, yaw=0.0):
    pad(PAVE, cx, cy, 60, 50, yaw)
    for i, r in enumerate(OFFICE): put(r, *l2w(cx, cy, yaw, -18 + (i % 2) * 36, -12 + (i // 2) * 24), 0, 1, 1, 1, yaw)
    for s in (-1, 1): box('concrete', *l2w(cx, cy, yaw, 0, s * 12), ground(cx, cy) + 16, 3.0, 20, 3.5, yaw)   # skybridges between the blocks
    scatter(CARS, cx, cy, 50, 4, 6, 0.05, yaw); people(cx, cy, 15, 8); st('office_blocks')

# =============================== LAYOUT =========================================
# Order matters for overlap: road first (reserves space), then zones (flat AND clear), then flight-line features,
# then modules, then scatter. Everything registers its true footprint in `occupied`.
occupied = [(0, 0, 60), (420, 60, 45)]
def free(x, y, r): return all(math.hypot(x - ox, y - oy) > r + orad for ox, oy, orad in occupied)
def spot(x, y, r, max_slide=200):
    tol = 1.2 if r < 40 else 1.8
    for dr in range(0, max_slide + 1, 10):
        for a in range(0, 360, 20):
            px, py = x + dr * math.cos(math.radians(a)), y + dr * math.sin(math.radians(a))
            if flat(px, py, r, tol) and flat(px, py, r * 0.5, tol * 0.7) and free(px, py, r): return px, py
    return None
def at(x, y, r, max_slide=200):
    p = spot(x, y, r, max_slide)
    if p is None: st('skipped_no_spot')
    return p
ZONE_AT = {}                                                                # zone name -> (x, y, yaw) actually used
def zone(fn, x, y, r, *a, max_slide=200, **k):
    p = at(x, y, r, max_slide)
    if not p: return None
    occupied.append((p[0], p[1], r)); ZONE_AT[fn.__name__] = (p[0], p[1], a[0] if a and isinstance(a[0], float) else 0.0); return fn(p[0], p[1], *a, **k)
def putf(row, x, y, r, dz=0.0, sx=1.0, sy=1.0, sz=1.0, yaw=0.0):
    p = at(x, y, r)
    if p: put(row, p[0], p[1], dz, sx, sy, sz, yaw); occupied.append((p[0], p[1], r))
    return p

# ---- 1. Road loop (reserved first) ----
road = [(-40, -40), (150, -60), (260, 60), (200, 230), (0, 240), (-200, 260), (-400, 120), (-420, -60), (-260, -200), (-60, -280), (40, -170), (-40, -40)]
road_pieces = []
def road_dist(x, y):
    best = 1e9
    for (x0, y0), (x1, y1) in zip(road, road[1:]):
        dx, dy = x1 - x0, y1 - y0; d2 = dx * dx + dy * dy
        if d2 < 1e-6: continue
        t = max(0, min(1, ((x - x0) * dx + (y - y0) * dy) / d2))
        best = min(best, math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)))
    return best
for (x0, y0), (x1, y1) in zip(road, road[1:]):
    L = math.hypot(x1 - x0, y1 - y0); yaw = math.atan2(y1 - y0, x1 - x0)
    for k in range(int(L // 10) + 1):
        t = min(1, (k + 0.5) * 10 / L); px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        if not flat(px, py, 5): continue
        pad(ASPHALT, px, py, 11, 9, yaw); box('default', px, py, ground(px, py) + 0.035, 0.01, 7, 0.14, yaw); occupied.append((px, py, 7)); road_pieces.append((px, py, yaw, k))
    st('road_segments')
for (px, py, yaw, k) in road_pieces:
    if k % 5 == 0: put(LAMP_SHORT, *l2w(px, py, yaw, 0, 5.5), 0, 1, 1, 1, yaw + math.pi / 2)
    if rng.random() < 0.12: put(rng.choice(CARS), *l2w(px, py, yaw, 0, rng.choice([-2.5, 2.5])), 0.05, 1, 1, 1, yaw + (0 if rng.random() < 0.5 else math.pi))
    if rng.random() < 0.15: put(CONE, *l2w(px, py, yaw, 0, rng.choice([-4.2, 4.2])), 0)

# ---- 2. Pits / start (origin) ----
pad(ASPHALT, -10, 0, 90, 60); g = G0
put(SIGN, -30, -24, 0.2, 2.5, 2.5, 2.5, math.pi / 2)
for tx, ty in ((-18, -24), (-18, -15), (-18, 15), (-18, 24)):
    put(TENT_CANOPY, tx, ty); put(TABLE, tx + 0.5, ty); put(CHAIR, tx + 0.5, ty - 1.2, 0, 1, 1, 1, 1.6); put(CHAIR, tx + 0.5, ty + 1.2, 0, 1, 1, 1, -1.6); put(rng.choice(PEOPLE_SIT), tx + 0.6, ty - 1.1, 0, 1, 1, 1, 1.6)
put(TENT_BIG, -32, -20); put(GENERATOR, -30, 22, 0, 1, 1, 1, 0.3)
for i, cx in enumerate((-38, -38, -38)): put(CARS[i], cx, -8 + i * 6, 0.05, 1, 1, 1, math.pi / 2)
put(LED_V, -24, 24, 0, 3.0, 1, 1.6, math.pi)
people(-30, 14, 5, 8, 0, face=(10, 0)); people(-30, -14, 5, 8, 0, face=(10, 0))
for sgn in (-1, 1):
    for u in range(-20, 30, 4): put(FENCE, u, sgn * 30)
for u in range(-35, 35, 9): put(LAMP_TALL, u, -31, 0, 1, 1, 1, math.pi / 2)
for sgn in (-1, 1): post('black', 2, sgn * 9, 0, 1.2, 1.2, top=g + 7.5)
box('black', 2, 0, g + 7.5, 1.4, 1.2, 19.2)
cube_text('FPV AIRSPACE', 1.3, 0, 0.0, cell=0.22, z0=g + 8.95 - 0.8, colour='blue', on_terrain=False, standing=False)
put(TRIBUNE, -2, 44, 0, 1.3, 1.3, 1.3, -math.pi / 2); people(-2, 34, 7, 14, 0, face=(0, 0)); occupied.append((-2, 44, 16))   # crowd stands in front of the tribune (its step heights are unknown)
logo_3d(-2, 66, -math.pi / 2, size=12); occupied.append((-2, 66, 10))
for i in range(4): put(rng.choice(NEONS), -8 + i * 4, 31, 2.5)
cube_text('FPV-AIRSPACE.APP', -70, -30, math.pi, cell=0.45, colour='blue'); occupied.append((-70, -30, 26))   # behind the tribune side, out of the start line
cube_text('FPV AIRSPACE', 420, 60, 0.0, cell=3.0, colour='default'); st('hillside_sign')

# ---- 3. Freestyle structures (the designed line) ----
def spire(x, y, levels=12, step=6.0):
    """72 m dive spire: four columns, holed floors with alternating hole positions so the dive is a slalom, ledges."""
    pad(GRAVEL, x, y, 34, 34); g = ground(x, y)
    for (u, v) in ((-5, -5), (5, -5), (5, 5), (-5, 5)): post('grey', x + u, y + v, 0, 0.6, 0.6, top=g + (levels + 1) * step)
    tube(x, y, g + 1.0, x, y, g + (levels + 1) * step + 4, 1.2, strict=False)
    for k in range(levels + 1):
        z = g + k * step
        if k > 0:
            off = 2.2 if k % 2 else -2.2
            add(FLOOR_HOLE_SQ, x + off, y, z, 2.6, 2.6, 1.0, 0)               # 10 m floor, ~4 m hole, offset left/right
            for sgn in (-1, 1): box('concrete', x, y + sgn * 5.8, z - 0.3, 0.3, 10.4, 1.6)   # ledges to flick over
        for i in range(4):
            a = i * math.pi / 2; add(rng.choice(NEONS), x + 5.3 * math.cos(a), y + 5.3 * math.sin(a), z + step / 2, 1, 1, 1, a + math.pi / 2)
    top = g + (levels + 1) * step; add(FLOOR_HOLE_SQ, x, y, top + 0.3, 3.0, 3.0, 1.0, 0); add(LED_V, x, y + 6.2, top + 0.3, 2.0, 1, 1.2, 0)   # holed top floor: dive in from above
    box('concrete', x + 9, y, g + levels * step * 0.5, 0.4, 6, 4)              # split-S platform halfway
    st('spires'); return top
def power_loop_bars(x, y, yaw):
    """Three goalposts of rising height to loop around, then an overhang slab on two columns."""
    for i, h in enumerate((10.0, 13.0, 16.0)):
        px, py = l2w(x, y, yaw, -20 + i * 20, 0); g = ground(px, py)
        for sgn in (-1, 1): post('grey', *l2w(px, py, yaw, 0, sgn * 9), 0, 0.7, 0.7, top=g + h)
        box('red', px, py, g + h, 0.7, 0.7, 18.7, yaw)
    px, py = l2w(x, y, yaw, 30, 0); g = ground(px, py)
    for sgn in (-1, 1): post('grey', *l2w(px, py, yaw, 0, sgn * 5), 0, 1.0, 1.0, top=g + 11)
    box('concrete', px, py, g + 11, 0.5, 14, 12, yaw)
    a_, b_ = l2w(x, y, yaw, -34, 0), l2w(x, y, yaw, 42, 0); tube(a_[0], a_[1], ground(*a_) + 2.0, b_[0], b_[1], ground(*b_) + 2.0, 2.5); st('power_loops')
def gap_panels(x, y, yaw):
    """Vertical holed floor tiles standing in a row, holes tightening from ~1.6 m to ~0.9 m; a 2 m slot wall at the end."""
    for i, sc in enumerate((1.0, 0.9, 0.8, 0.7, 0.6)):
        px, py = l2w(x, y, yaw, -24 + i * 9, 0); g = ground(px, py)
        add(FLOOR_HOLE_SQ if i % 2 == 0 else FLOOR_HOLE_R, px, py, g + 2.0 * sc + 0.3, sc, sc, 1.0, rot=quat_pitch_yaw(90, math.degrees(yaw) + 90))
        for sgn in (-1, 1): post('grey', *l2w(px, py, yaw, 0, sgn * 2.4 * sc), 4.0 * sc + 0.6, 0.3, 0.8 * sc)
        a_, b_ = l2w(px, py, yaw, -4, 0), l2w(px, py, yaw, 4, 0); tube(a_[0], a_[1], g + 2.0 * sc + 0.3, b_[0], b_[1], g + 2.0 * sc + 0.3, 0.7 * sc, strict=False)
    px, py = l2w(x, y, yaw, 24, 0); g = ground(px, py)
    for sgn in (-1, 1): post('brick', *l2w(px, py, yaw, 0, sgn * 4.0), 6.0, 0.3, 6.0)
    a_, b_ = l2w(px, py, yaw, -8, 0), l2w(px, py, yaw, 8, 0); tube(a_[0], a_[1], g + 2.5, b_[0], b_[1], g + 2.5, 0.8)     # the 2 m slot
    scatter([CONE, TIRE_PILE], *l2w(x, y, yaw, 0, 8), 50, 4, 6, 0, yaw); st('gap_panels')
def bridge(x, y, yaw, L=44.0, h=8.0):
    """Concrete deck on pillars: underpass, loop target, ledge."""
    g = ground(x, y)
    for i in range(4):
        px, py = l2w(x, y, yaw, -L / 2 + 4 + i * (L - 8) / 3, 0)
        for sgn in (-1, 1): post('grey', *l2w(px, py, yaw, 0, sgn * 3.2), 0, 1.0, 1.0, top=g + h)
    for i in range(3):
        u = -L / 2 + 4 + (i + 0.5) * (L - 8) / 3; a_, b_ = l2w(x, y, yaw, u, -9), l2w(x, y, yaw, u, 9); tube(a_[0], a_[1], g + 3.0, b_[0], b_[1], g + 3.0, 2.0)
    box('concrete', x, y, g + h, 0.6, L, 8.0, yaw)
    for sgn in (-1, 1): box('concrete', *l2w(x, y, yaw, 0, sgn * 3.8), g + h + 0.6, 1.0, L, 0.4, yaw)
    for i in range(int(L // 8)): add(rng.choice(NEONS), *l2w(x, y, yaw, -L / 2 + 4 + i * 8, 4.1), g + h + 1.0, 1, 1, 1, yaw)
    st('bridges')
def bent_tunnel(x, y, yaw):
    for i, dy in enumerate((0.0, 0.0, 0.35, 0.7, 0.7)):
        px, py = l2w(x, y, yaw, -19 + i * 9.5, (-6, -6, -3.5, 1.5, 6.5)[i]); put(CUBE_HOLE[rng.choice(['blue', 'grey', 'yellow'])], px, py, 2.6, 10, 5.2, 5.2, yaw + dy + math.pi / 2)
        a_, b_ = l2w(px, py, yaw + dy, -5, 0), l2w(px, py, yaw + dy, 5, 0); tube(a_[0], a_[1], ground(px, py) + 2.6, b_[0], b_[1], ground(px, py) + 2.6, 1.5, strict=False)
    st('tunnels')
def container_stacks(x, y, yaw):
    for i in range(5):
        px, py = l2w(x, y, yaw, -24 + i * 12, 0); g = ground(px, py)
        for k in range(3):
            off = (0, 1.5, 3.0)[k] * (1 if i % 2 else -1); add(CONTAINER_S, *l2w(px, py, yaw, 0, off), g + k * 2.6, 1, 1, 1, yaw + math.pi / 2)
    for i in range(4):
        px, py = l2w(x, y, yaw, -18 + i * 12, 12); add(CONTAINER_L, px, py, ground(px, py) + 2.6, 1, 1, 1, yaw)   # bridged pairs: fly under
        a_, b_ = l2w(px, py, yaw, -8, 0), l2w(px, py, yaw, 8, 0); tube(a_[0], a_[1], ground(px, py) + 1.3, b_[0], b_[1], ground(px, py) + 1.3, 1.0, strict=False)
        for sgn in (-1, 1): add(CONTAINER_S, *l2w(px, py, yaw, 0, sgn * 4.6), ground(px, py), 1, 1, 1, yaw + math.pi / 2)
    st('container_stacks')
def tree_tunnel(x, y, yaw, L=100.0):
    for i in range(int(L // 4.5)):
        for sgn in (-1, 1):
            px, py = l2w(x, y, yaw, -L / 2 + i * 4.5, sgn * 3.2); s_ = rng.uniform(1.0, 1.3); put(rng.choice(TREES), px, py, 0, s_, s_, s_, rng.uniform(0, 6.28))
    pad(GRAVEL, x, y, L, 4.5, yaw); a_, b_ = l2w(x, y, yaw, -L / 2 - 10, 0), l2w(x, y, yaw, L / 2 + 10, 0); tube(a_[0], a_[1], ground(*a_) + 2.0, b_[0], b_[1], ground(*b_) + 2.0, 2.0, strict=False); st('tree_tunnels')
def orbit_tower(x, y):
    g = ground(x, y)
    for k in range(5): cylinder('grey', x, y, g + k * 6 - (1.0 if k == 0 else 0), 6.0 + (1.0 if k == 0 else 0), 4.0 - k * 0.3)
    box('concrete', x, y, g + 30, 0.4, 9, 9); cylinder('red', x, y, g + 30.4, 3.0, 5.0); add(LED_V, x, y + 2.6, g + 33.4, 1.2, 1, 0.8, 0)
    put(STATUE if rng.random() < 0.5 else TANK_V, x + 12, y, 0, 1.8, 1.8, 1.8, 0); st('orbit_towers')
def pole_line(x, y, yaw, n=8):
    for i in range(n): put(POLE, *l2w(x, y, yaw, i * 11, 0), 0, 1.5, 1.5, 1.5, yaw); st('pole_lines')
def gauntlet_bando(bx, by, yaw):
    """Main hall (bando) plus a 30 m gauntlet wing: single-window walls both sides, column corridor, holed roof."""
    bando(bx, by, 40, 24, yaw, floors=3)
    wx, wy = l2w(bx, by, yaw, 0, 32); g = ground(wx, wy)            # wing 32 m north of the hall, parallel to it, open at both ends with a clear run-in/run-out
    for i in range(8):
        for sgn in (-1, 1):
            px, py = l2w(wx, wy, yaw, -14 + i * 4, sgn * 3.0); add(WALL_WIN[i % len(WALL_WIN)], px, py, g, 1, 1, 1, yaw + math.pi / 2)
            add(WALL_WIN[(i + 2) % len(WALL_WIN)], px, py, g + 4.0, 1, 1, 1, yaw + math.pi / 2)
        px, py = l2w(wx, wy, yaw, -14 + i * 4, 0); add(FLOOR_HOLE_SQ if i % 2 else CONCRETE, px, py, g + 4.0, 1, 1, 1, yaw)
        add(FLOOR_HOLE_R if i % 3 else CONCRETE, px, py, g + 8.0, 1, 1, 1, yaw)
    for i in range(12): add(COLUMN_BRICK, *l2w(wx, wy, yaw, -14 + i * 2.5, 0), g, 1, 1, 1, yaw)   # 2.5 m column corridor on the ground floor
    a_, b_ = l2w(wx, wy, yaw, -24, 0), l2w(wx, wy, yaw, 24, 0); tube(a_[0], a_[1], g + 5.9, b_[0], b_[1], g + 5.9, 1.5)          # first floor: the race line
    for v in (-1.6, 1.6):
        a_, b_ = l2w(wx, wy, yaw, -24, v), l2w(wx, wy, yaw, 24, v); tube(a_[0], a_[1], g + 1.8, b_[0], b_[1], g + 1.8, 0.9)        # ground floor: either side of the columns
    for k in range(2): add(STAIRS, *l2w(wx, wy, yaw, 16, -5.5), g + k * 4, 1, 1, 1, yaw + math.pi)   # stairs beside the wing, not on its axis
    st('gauntlets')

# ---- 4. Layout: a central arena of chained freestyle features (in race order) ringed by themed districts ----
# Nothing is placed at random: every zone belongs to the arena or to a district, slides at most `max_slide` m to find
# flat free ground (skipped otherwise), and every module faces the nearest road piece so the park reads as one place.
def road_yaw(x, y):
    p = min(road_pieces, key=lambda p: math.hypot(p[0] - x, p[1] - y)); return p[2]
zone(gauntlet_bando, 130, 85, 46, 0.0)
zone(bent_tunnel, 200, 150, 26, -0.6)
zone(gap_field, 290, 0, 44, 0.0)
zone(gap_panels, 200, -60, 30, 1.2)
zone(container_stacks, 110, -14, 30, 0.0)
zone(power_loop_bars, 60, -120, 40, 0.3)
zone(lake, 90, -220, 50)
zone(skatepark, -120, -200, 26, 0.2)
zone(tree_tunnel, -250, -120, 52, 0.5)
zone(orbit_tower, -200, 20, 13)
zone(bridge, -60, 160, 24, 0.4)
top_spire = zone(spire, -150, 120, 20, levels=12) or (G0 + 78)
def tower(cx, cy, row, yaw=0.0):
    """Neo tower on a paved apron with a 40 m dive ledge, lamps, parked cars and people at its foot."""
    pad(PAVE, cx, cy, 110, 100, yaw); put(row, cx, cy, 0, 1, 1, 1, yaw)
    lx_, ly_ = l2w(cx, cy, yaw, 50, 0); post('grey', lx_, ly_, 0, 2.0, 2.0, yaw, top=ground(lx_, ly_) + 40)     # dive platform on its own 40 m pillar beside the tower
    box('concrete', lx_, ly_, ground(lx_, ly_) + 40, 0.5, 14, 10, yaw)
    for i in range(8): put(LAMP_TALL, *l2w(cx, cy, yaw, -45 + i * 13, -44), 0, 1, 1, 1, yaw)
    for i in range(10): put(rng.choice(CARS), *l2w(cx, cy, yaw, -40 + i * 8, 42), 0.05, 1, 1, 1, yaw + math.pi / 2)
    people(*l2w(cx, cy, yaw, 0, -30), 12, 14); st('towers')
def dome(cx, cy, yaw=0.0): pad(PAVE, cx, cy, 60, 60); put(NEO_DOME, cx, cy, 31.1, 1, 1, 1, yaw); people(cx, cy + 28, 6, 6); st('domes')
def midrise(cx, cy, row, yaw=0.0):
    pad(PAVE, cx, cy, 70, 60, yaw); put(row, cx, cy, 0, 1, 1, 1, yaw)
    for i in range(6): put(rng.choice(CARS), *l2w(cx, cy, yaw, -25 + i * 8, 26), 0.05, 1, 1, 1, yaw + math.pi / 2)
    for i in range(4): put(LAMP_TALL, *l2w(cx, cy, yaw, -30 + i * 20, -26), 0, 1, 1, 1, yaw); people(cx, cy - 20, 8, 8); st('midrise')
def container_city(cx, cy, yaw=0.0):
    """A dense container block: 6 x 5 stacks up to three high with alleys to thread and bridged gaps to fly under."""
    pad(ASPHALT, cx, cy, 90, 70, yaw)
    for i in range(6):
        for j in range(5):
            px, py = l2w(cx, cy, yaw, -35 + i * 14, -24 + j * 12); n = (i * 7 + j * 3) % 4
            for k in range(n): add(rng.choice([CONTAINER_S, CONTAINER_S, CONTAINER_L]), px, py, ground(px, py) + k * 2.6, 1, 1, 1, yaw + (math.pi / 2 if k % 2 else 0))
    for j in range(5):
        a_, b_ = l2w(cx, cy, yaw, -48, -24 + j * 12 + 6), l2w(cx, cy, yaw, 48, -24 + j * 12 + 6); tube(a_[0], a_[1], ground(cx, cy) + 1.8, b_[0], b_[1], ground(cx, cy) + 1.8, 1.2, strict=False)
    scatter([PALLET, BARREL, CRATE, CONE, FORKLIFT], cx, cy, 80, 60, 20, 0, yaw); people(cx, cy, 20, 8); st('container_cities')
def train_yard(cx, cy, yaw=0.0):
    pad(GRAVEL, cx, cy, 100, 36, yaw)
    for t in range(2):
        for i in range(6): put(BOXCAR, *l2w(cx, cy, yaw, -41 + i * 14.5, -10 + t * 20), 0, 1, 1, 1, yaw)
    for i in range(8): put(POLE, *l2w(cx, cy, yaw, -44 + i * 12.5, 0), 0, 1.3, 1.3, 1.3, yaw)
    a_, b_ = l2w(cx, cy, yaw, -55, 0), l2w(cx, cy, yaw, 55, 0); tube(a_[0], a_[1], ground(cx, cy) + 2.0, b_[0], b_[1], ground(cx, cy) + 2.0, 2.0, strict=False); st('train_yards')
def hamlet(cx, cy, yaw=0.0):
    """Twenty houses on two lanes with gardens, fences, cars and people."""
    pad(GRAVEL, cx, cy, 100, 90, yaw)
    for i in range(7):
        for side in (-1, 1):
            r = HOUSES[(i + side) % len(HOUSES)]; px, py = l2w(cx, cy, yaw, -45 + i * 15, side * 26)
            put(r, px, py, 0, 1, 1, 1, yaw + (math.pi / 2 if side > 0 else -math.pi / 2))
            for u in (-6, -2, 2, 6): put(FENCE, *l2w(cx, cy, yaw, -45 + i * 15 + u, side * 12), 0, 1, 1, 1, yaw)
            put(rng.choice(TREES + BUSHES), *l2w(cx, cy, yaw, -45 + i * 15 + 7, side * 38), 0, 1, 1, 1, rng.uniform(0, 6.28))
            if rng.random() < 0.5: put(rng.choice(CARS), *l2w(cx, cy, yaw, -45 + i * 15, side * 8), 0.05, 1, 1, 1, yaw)
    for i in range(5): put(LAMP_SHORT, *l2w(cx, cy, yaw, -40 + i * 20, 0), 0, 1, 1, 1, yaw)
    people(cx, cy, 30, 16); st('hamlets')
def junkyard(cx, cy, yaw=0.0):
    pad(DIRT, cx, cy, 90, 70, yaw)
    for i in range(6):
        for j in range(3): put(rng.choice(CARS), *l2w(cx, cy, yaw, -30 + i * 12, -20 + j * 16), 0.05, 1, 1, 1, yaw + rng.uniform(-0.4, 0.4))
    for i in range(8): put(TIRE_WALL, *l2w(cx, cy, yaw, -35 + i * 10, 30), 0, 1, 1, 1, yaw)
    scatter([TIRE_PILE, BARREL, PALLET, DUMPSTER, 'NewRow_93'], cx, cy, 80, 60, 30, 0, yaw); put(FORKLIFT, cx, cy, 0, 1, 1, 1, yaw + 0.5); st('junkyards')
def beach(cx, cy, yaw=0.0):
    for i in range(6): put(rng.choice([TENT, TENT_CANOPY]), *l2w(cx, cy, yaw, -25 + i * 10, 0), 0, 1, 1, 1, yaw + rng.uniform(-0.5, 0.5))
    scatter([TABLE, CHAIR, BENCH, BARREL], cx, cy, 60, 16, 14, 0, yaw); people(cx, cy, 25, 20); st('beaches')
def wood(cx, cy, yaw=0.0): forest(cx, cy, 56, 56, 80)
DISTRICTS = {                                                               # name: (centre, radius, items[(fn, dx, dy, r, args...)])
    'downtown': ((-290, 170), 140, [(tower, 0, 30, 50, NEO_LG[0], 0.2), (tower, 90, 80, 50, NEO_LG[1], 0.0), (tower, -40, -70, 50, NEO_LG[2], 0.4), (dome, 60, -20, 32),
                                    (midrise, -110, 60, 36, NEO_MD[0], 0.2), (midrise, 10, 130, 36, NEO_MD[1], 0.0), (office_block, 120, -10, 34, 0.0), (bando, -120, -40, 30, 28, 20, 0.3)]),
    'farm': ((-170, 250), 120, [(farm, 0, 0, 36, 0.3), (hamlet, 110, -20, 52, 0.2), (village, -100, 10, 42, 0.1)]),
    'industrial': ((200, 160), 130, [(crane_yard, 0, 0, 52, 0.0), (container_city, 110, -30, 46, 0.0), (train_yard, -100, 60, 52, 0.1), (dive_tower, 100, 60, 17, 6), (scaffold_tower, -40, -60, 5)]),
    'junkyard': ((-60, -210), 120, [(junkyard, 0, 0, 46, 0.3), (scaffold_tower, 70, -20, 5), (pole_line, -70, 40, 44, 0.2)]),
    'lake': ((95, -211), 120, [(beach, 0, 90, 32, 0.0), (scaffold_tower, -70, 30, 5)]),
}
DISTRICT_MODULES = {'downtown': ['m_car_park', 'm_neon_garden', 'm_picnic', 'm_scaffold_cluster', 'm_car_park', 'm_column_forest', 'm_goalpost'],
                    'farm': ['m_hay_field', 'm_tree_ring', 'm_hay_field', 'm_picnic', 'm_tree_ring', 'm_arch_row'],
                    'industrial': ['m_tank_farm', 'm_pipes', 'm_pallet_yard', 'm_container_maze', 'm_tunnel_chain', 'm_goalpost', 'm_tank_farm'],
                    'junkyard': ['m_tire_slalom', 'm_hesco_fort', 'm_ramp_pair', 'm_rock_garden', 'm_tent_camp', 'm_tunnel_chain', 'm_tire_slalom'],
                    'lake': ['m_tent_camp', 'm_picnic', 'm_tree_ring', 'm_ramp_pair']}
# =============================== RACE ===========================================
# The race is planned as straight flight lines: every leg between consecutive gates is a straight segment that
# tools/raceline.py checks against the oriented bounds of every placed mesh and the terrain (the build aborts if
# a leg is blocked). Features are flown along their open axis with a gate at each end, so the pilot is never asked
# to turn inside a corridor: hall-side gauntlet wing (first floor, 6 m wide), under the three power-loop bars and
# the overhang slab, low over the lake, round the orbit tower, under the bridge between its pillars, a 40 m climb up
# the spire's south face, over its top and a 77 m dive back down beside it, then the home straight through the arch.
# Conventions measured on 17 Workshop tracks: start and gate yaw = flight bearing - 90 deg (the gate's local +Y is
# the flight direction); Spoints[0] = start, Spoints[i] = gate i-1 with the gate's yaw, 0.5 m below its centre.
GATE_FLY = {r: v['box_t'][2] / 100 for r, v in json.load(open(os.path.join(DATA, 'gate_bounds.json'))).items()}   # opening centre above the pivot
GATE_FLY['ClassicRound'] = 1.45
START_XY = (-22.0, 0.0); START_H = 1.2; SPAWN_BACK = 12.0                 # start gate at START_XY; the drone spawns SPAWN_BACK m behind it
def zp(name, default): return ZONE_AT.get(name, (default[0], default[1], default[2] if len(default) > 2 else 0.0))
gb = zp('gauntlet_bando', (130, 85, 0.0)); pl = zp('power_loop_bars', (60, -120, 0.3)); br = zp('bridge', (-60, 160, 0.4))
lk = zp('lake', (60, -270)); sp = zp('spire', (-150, 120)); ot = zp('orbit_tower', (-200, 20))
gates = []                                                                   # (row, x, y, flight z absolute, scale)
CENTRE_HALF = {'DefaultGate': 1.0, 'DefaultOneW': 1.0, 'Invisible': 1.5, 'InflRond02': 1.73}       # centre-pivot gates: half height of the opening
GATE_SCALE = {'DefaultGate': 3.0, 'DefaultOneW': 3.0, 'GateModul01': 2.0, 'ClassicRound': 1.5, 'Invisible': 2.0, 'InflRond02': 1.0,
              'InflSimpl02': 1.5, 'InflSimpl01': 1.5, 'InflRound01': 1.5, 'InflElev01': 1.0, 'InflDive01': 1.5, 'InflDive02': 1.0}   # Workshop tracks scale the 2 m gates up to 5.5x; these are the sizes used here
def gate(row, x, y, fly_h=None, z_abs=None, sc=None):
    """fly_h: height of the opening centre above the ground there; z_abs: absolute opening-centre height; sc: gate scale."""
    sc = sc if sc is not None else GATE_SCALE.get(row, 1.0)
    if z_abs is not None: z = z_abs
    else:
        if row in CENTRE_HALF: z = ground(x, y) + max(fly_h if fly_h is not None else 0.0, CENTRE_HALF[row] * sc + 0.5)
        else: z = ground(x, y) + max(fly_h if fly_h is not None else GATE_FLY.get(row, 0.0) * sc, 2.5)   # never lower than 2.5 m: the valley floor undulates up to 1.5 m
    gates.append((row, x, y, z, sc))
wing = l2w(gb[0], gb[1], gb[2], 0, 32); wyaw = gb[2]; wing_fly = ground(*wing) + 5.9      # first-floor corridor: floors at +4.0 and +8.0, walls at v = +-3
gate('InflSimpl02', 40, 0)                                                   # 1  home straight, through the pit arch
gate('InflDive01', 66, 92)                                                   # 2  tall inflatable before the hall (opening 3.8 m up)
gate('DefaultGate', *l2w(wing[0], wing[1], wyaw, -30, 0), z_abs=wing_fly, sc=1.5)    # 3  line-up gate 16 m before the wing, at first-floor height (3 m gate)
gate('DefaultOneW', *l2w(wing[0], wing[1], wyaw, -11, 0), z_abs=wing_fly, sc=1.5)    # 4  inside the wing, first floor (6 m wide, 3.7 m tall)
gate('DefaultOneW', *l2w(wing[0], wing[1], wyaw, 11, 0), z_abs=wing_fly, sc=1.5)     # 5  wing exit
gate('InflRound01', *l2w(wing[0], wing[1], wyaw, 60, 0))                     # 6  straight out of the wing, big round gate
gate('InflElev01', 262, 50)                                                  # 7  elevated gate in the east field, turn south
gf = zp('gap_field', (290, 0))
gate('GateModul01', gf[0] + 66, gf[1] - 30)                                  # 8  low gate heading south, east of the gap field's containers and arches
gate('InflDive02', lk[0] + 72, lk[1] + 12)                                   # 9  drop to the lake's east shore
gate('Invisible', lk[0], lk[1], 2.0)                                         # 10 low pass over the water
gate('InflSimpl02', lk[0] - 80, lk[1] - 10)                                  # 11 south-west shore (the jump ramp is on the west shore), turn north
gate('InflSimpl01', *l2w(pl[0], pl[1], pl[2], -42, 0))                       # 12 under the three rising power-loop bars ...
gate('GateModul01', *l2w(pl[0], pl[1], pl[2], 52, 0))                        # 13 ... and the overhang slab
gate('GateModul01', 105, -45)                                                # 14 turn north-west, south of the container stacks
gate('InflSimpl02', -40, -95)                                                # 15 across the jump field
gate('InflSimpl02', -120, -165)                                              # 16 north of the skatepark
gate('GateModul01', ot[0] - 30, ot[1] - 60)                                  # 17 orbit the tower ...
gate('ClassicRound', ot[0] + 30, ot[1] + 40)                                 # 18 ... passing 5 m from it
gate('InflRond02', *l2w(br[0], br[1], br[2], 0, -30))                        # 19 line up on the bridge's underpass
gate('DefaultOneW', br[0], br[1], 3.5, sc=2.5)                               # 20 under the deck (8 m clear), between the middle pillars
gate('InflRond02', *l2w(br[0], br[1], br[2], 0, 30))                         # 21 out the other side
gate('DefaultGate', sp[0] + 30, sp[1] - 9, 40.0)                             # 22 climb along the spire's south face ...
gate('DefaultOneW', sp[0], sp[1] - 10, z_abs=top_spire + 4.5)                # 23 ... over the top (6 m gate, bottom 1.5 m above the roof) ...
gate('InflDive01', sp[0] - 30, sp[1] - 9)                                    # 24 ... and dive 77 m beside it
gate('GateModul01', -120, 48)                                                # 25 low gate, turn for home
gate('DefaultGate', -62, 0)                                                  # 26 home straight
if ROOKIE:
    # Rookie race: the home straight, then the road loop vertex by vertex (midpoints on long legs), big low inflatables only
    gates = []
    gate('InflSimpl02', 40, 0)
    pts = road[1:]                                                    # (150,-60) ... (-40,-40): the loop in driving order, pits last
    for (x0, y0), (x1, y1) in zip([(40, 0)] + pts, pts):
        if math.hypot(x1 - x0, y1 - y0) > 170: gate('InflSimpl02', (x0 + x1) / 2, (y0 + y1) / 2)
        gate('InflSimpl01' if len(gates) % 4 == 3 else 'InflSimpl02', x1, y1)
    gate('InflSimpl02', -62, 0)
# ---- flight corridor: spawn -> start gate -> gates -> start, reserved before modules, jumps and scatter ----
line = [START_XY] + [(x, y) for (_, x, y, _, _) in gates] + [START_XY]
def corridor_dist(x, y):
    best = 1e9
    for (x0, y0), (x1, y1) in zip(line, line[1:]):
        dx, dy = x1 - x0, y1 - y0; d2 = dx * dx + dy * dy
        if d2 < 1e-6: best = min(best, math.hypot(x - x0, y - y0)); continue
        t = max(0, min(1, ((x - x0) * dx + (y - y0) * dy) / d2))
        best = min(best, math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)))
    return best
_free = free
def free(x, y, r): return _free(x, y, r) and corridor_dist(x, y) > r + 8
for (_, x, y, _, _) in gates: occupied.append((x, y, 6))
occupied.append((START_XY[0] - SPAWN_BACK, START_XY[1], 6))
jump_pts = [(-40, -60), (20, -110), (-30, -170), (-100, -200), (-180, -170), (-220, -100), (-160, -40), (-80, -40), (-40, -60)]
jump_track([pt for pt in jump_pts if corridor_dist(*pt) > 12] or jump_pts[:2])
# ---- districts and landmarks: placed only now, so they respect the reserved race corridor ----
for name, ((dx0, dy0), R, items) in DISTRICTS.items():
    for it in items:
        fn, dx, dy, r = it[0], it[1], it[2], it[3]; args = it[4:]
        zone(fn, dx0 + dx, dy0 + dy, r, *args, max_slide=150)
    for i, r in enumerate(NEO_SM): zone(midrise, -340 + i * 60, 40 - i * 30, 36, r, 0.2 * i, max_slide=120) if name == 'downtown' else None
for (x, y) in ((250, 150), (300, 190), (350, 120)): putf(TURBINE, x, y, 7, 0, 1.6, 1.6, 1.6, rng.uniform(0, 6.28))
putf(WINDMILL_L, 300, 240, 13, 0, 1, 1, 1, 1.2)
putf(RIG, -60, 380, 21, 0, 1, 1, 1, 0.3); putf(TANK_V, -95, 360, 4); putf(TANK_V, -87, 360, 4); putf(PIPES, -80, 372, 4, 0, 2, 2, 2)
for (x, y) in ((160, 110), (-50, -150), (40, 140)): zone(scaffold_tower, x, y, 5)
for i in range(5):
    px, py = -60 + i * 7, 230
    if flat(px, py, 4) and free(px, py, 4): put(PIPE, px, py, 0, 3.0, 3.0, 3.0, math.pi / 2); occupied.append((px, py, 4))
for (x, y, z) in ((90, -220, 70), (-230, -20, 90)): put(BALLOON, x, y, z, 1, 1, 1, rng.uniform(0, 6.28)); st('balloons')   # two landmarks: over the lake and above the spire

# ---- module library (placed per district in section 5) ----
MODULES = []
def module(r):
    def deco(fn): MODULES.append((fn, r)); return fn
    return deco
@module(26)
def m_container_maze(x, y, yaw):
    for i in range(4):
        for j in range(4):
            if (i + j) % 2: continue
            put(CONTAINER_S, *l2w(x, y, yaw, -18 + i * 12, -18 + j * 12), 0, 1, 1, 1, yaw + (math.pi / 2 if j % 2 else 0))
            if rng.random() < 0.4: put(CONTAINER_S, *l2w(x, y, yaw, -18 + i * 12, -18 + j * 12), 2.6, 1, 1, 1, yaw + 0.3)
@module(24)
def m_pipes(x, y, yaw):
    for i in range(6): put(PIPE, *l2w(x, y, yaw, -20 + i * 8, 0), 0, 3.0, 3.0, 3.0, yaw + math.pi / 2)
    scatter([CONE, BARREL], x, y, 40, 10, 6, 0, yaw)
@module(28)
def m_tire_slalom(x, y, yaw):
    for i in range(7): put(TIRE_WALL, *l2w(x, y, yaw, -24 + i * 8, (i % 2) * 8 - 4), 0, 1, 1, 1, yaw + 0.5 * (i % 2))
    scatter([TIRE_PILE, CONE], x, y, 50, 20, 8, 0, yaw)
@module(18)
def m_hesco_fort(x, y, yaw):
    for i in range(8):
        a = i / 8 * 6.283; put(HESCO, x + 14 * math.cos(a), y + 14 * math.sin(a), 0, 2, 2, 2.5, a)
    put(TENT, x, y, 0, 1, 1, 1, yaw); scatter([BARREL, CRATE, PALLET], x, y, 18, 18, 6)
@module(26)
def m_car_park(x, y, yaw):
    pad(ASPHALT, x, y, 44, 30, yaw)
    for i in range(7):
        for j in range(2):
            if rng.random() < 0.3: continue
            put(rng.choice(CARS), *l2w(x, y, yaw, -18 + i * 6, -8 + j * 16), 0.05, 1, 1, 1, yaw + math.pi / 2)
    put(LAMP_TALL, x, y, 0, 1, 1, 1, yaw)
@module(22)
def m_tent_camp(x, y, yaw):
    for i in range(5): put(rng.choice([TENT, TENT_CANOPY, TENT_BIG]), *l2w(x, y, yaw, rng.uniform(-14, 14), rng.uniform(-10, 10)), 0, 1, 1, 1, rng.uniform(0, 6.28))
    people(x, y, 14, 8); scatter([TABLE, CHAIR, BARREL], x, y, 30, 24, 10)
@module(28)
def m_hay_field(x, y, yaw): scatter(HAY, x, y, 50, 40, 24, 0, yaw)
@module(28)
def m_rock_garden(x, y, yaw): scatter(ROCKS + BUSHES + [CLIFF], x, y, 50, 40, 18, 0, yaw, scale=(0.8, 2.2))
@module(22)
def m_tree_ring(x, y, yaw):
    for i in range(14):
        a = i / 14 * 6.283; s_ = rng.uniform(0.9, 1.3); put(rng.choice(TREES), x + 18 * math.cos(a), y + 18 * math.sin(a), 0, s_, s_, s_, a)
    put(rng.choice(BIG_TREES), x, y, 0, 1.2, 1.2, 1.2, rng.uniform(0, 6.28))
@module(26)
def m_tunnel_chain(x, y, yaw):
    for i in range(5): put(CUBE_HOLE[rng.choice(['blue', 'grey', 'yellow', 'red'])], *l2w(x, y, yaw, -20 + i * 10, 0), 2.5, 6, 5, 5, yaw + math.pi / 2)
    a_, b_ = l2w(x, y, yaw, -28, 0), l2w(x, y, yaw, 28, 0); tube(a_[0], a_[1], ground(x, y) + 2.5, b_[0], b_[1], ground(x, y) + 2.5, 1.5, strict=False)
@module(28)
def m_column_forest(x, y, yaw):
    for i in range(6):
        for j in range(5): post('grey', *l2w(x, y, yaw, -20 + i * 8, -16 + j * 8), 0, 0.8, 0.8, top=ground(x, y) + 8)
    box('concrete', x, y, ground(x, y) + 8, 0.3, 46, 38, yaw)
    for j in range(4):
        a_, b_ = l2w(x, y, yaw, -26, -12 + j * 8), l2w(x, y, yaw, 26, -12 + j * 8); tube(a_[0], a_[1], ground(x, y) + 3.0, b_[0], b_[1], ground(x, y) + 3.0, 1.5)
@module(24)
def m_arch_row(x, y, yaw):
    for i in range(5): put(ARCH, *l2w(x, y, yaw, -20 + i * 10, 0), 0, 1.5, 1.5, 1.5, yaw)
    a_, b_ = l2w(x, y, yaw, -28, 0), l2w(x, y, yaw, 28, 0); tube(a_[0], a_[1], ground(x, y) + 3.0, b_[0], b_[1], ground(x, y) + 3.0, 1.5, strict=False)
@module(22)
def m_tank_farm(x, y, yaw):
    for i in range(3): put(TANK_V, *l2w(x, y, yaw, -12 + i * 12, 0), 0, 1, 1, 1, yaw)
    put(PIPES, *l2w(x, y, yaw, 0, 12), 0, 2, 2, 2, yaw); scatter([BARREL, PIPES], x, y, 40, 28, 6, 0, yaw)
@module(30)
def m_train(x, y, yaw):
    for i in range(4): put(BOXCAR, *l2w(x, y, yaw, -22 + i * 14.5, 0), 0, 1, 1, 1, yaw)
    for i in range(4): put(POLE, *l2w(x, y, yaw, -22 + i * 14.5, 10), 0, 1.3, 1.3, 1.3, yaw)
@module(20)
def m_picnic(x, y, yaw):
    scatter([TABLE, BENCH, CHAIR], x, y, 30, 24, 10); people(x, y, 14, 8)
@module(16)
def m_neon_garden(x, y, yaw):
    for i in range(12):
        a = i / 12 * 6.283; px, py = x + 12 * math.cos(a), y + 12 * math.sin(a); cylinder('grey', px, py, ground(px, py), 3.0, 0.3); add(rng.choice(NEONS), px, py, ground(px, py) + 3.2, 1, 1, 1, a)
@module(20)
def m_scaffold_cluster(x, y, yaw):
    for (u, v, n) in ((-12, -10, 4), (12, -10, 6), (0, 12, 5)): scaffold_tower(*l2w(x, y, yaw, u, v), n)
@module(26)
def m_pallet_yard(x, y, yaw):
    for i in range(5):
        for j in range(4):
            for k in range(rng.randint(1, 4)): put(PALLET, *l2w(x, y, yaw, -16 + i * 8, -12 + j * 8), k * 0.17, 1, 1, 1, yaw)
    put(FORKLIFT, *l2w(x, y, yaw, 22, 0), 0, 1, 1, 1, yaw)
@module(24)
def m_ramp_pair(x, y, yaw):
    for sgn in (-1, 1):
        x0, y0 = l2w(x, y, yaw, sgn * 4, 0); x1, y1 = l2w(x, y, yaw, sgn * 20, 0)
        pitched('grey', x0, y0, ground(x0, y0) + 0.05, x1, y1, ground(x1, y1) + 5.0, 6.0)
    scatter([TIRE_PILE, CONE], x, y, 44, 12, 8, 0, yaw)
@module(20)
def m_goalpost(x, y, yaw):
    g = ground(x, y)
    for sgn in (-1, 1): post('grey', *l2w(x, y, yaw, 0, sgn * 8), 0, 0.7, 0.7, top=g + 12)
    box('yellow', x, y, g + 12, 0.7, 0.7, 16.7, yaw)
    for sgn in (-1, 1): post('grey', *l2w(x, y, yaw, 14, sgn * 5), 0, 0.6, 0.6, top=g + 7)
    box('yellow', *l2w(x, y, yaw, 14, 0), g + 7, 0.6, 0.6, 10.6, yaw)
    a_, b_ = l2w(x, y, yaw, -10, 0), l2w(x, y, yaw, 24, 0); tube(a_[0], a_[1], g + 2.0, b_[0], b_[1], g + 2.0, 2.0)
# ---- 5. District modules on flat cells near their district, facing the road; then road dressing and flow gates ----
cells = json.load(open(os.path.join(DATA, 'flat_cells04.json')))
MOD = {fn.__name__: (fn, r) for fn, r in MODULES}
for name, ((dx0, dy0), R, items) in DISTRICTS.items():
    for mname in DISTRICT_MODULES[name]:
        fn, r = MOD[mname]
        cands = sorted((c for c in cells if math.hypot(c[0] - dx0, c[1] - dy0) < R), key=lambda c: math.hypot(c[0] - dx0, c[1] - dy0))
        for (cx, cy) in cands:
            if math.hypot(cx, cy) < 80 or not flat(cx, cy, r) or not free(cx, cy, r): continue
            fn(cx, cy, road_yaw(cx, cy)); occupied.append((cx, cy, r)); st('modules'); break
        else: st('modules_skipped')
DRESS = {'downtown': (CARS + [LAMP_TALL, BENCH, DUMPSTER, 'NewRow_323', TABLE, CHAIR], 70), 'farm': (HAY + [TRACTOR, FENCE, FENCE, BARREL] + BUSHES, 90), 'industrial': ([BARREL, PALLET, CRATE, CONE, HESCO, FORKLIFT, PIPES, GENERATOR], 110),
         'junkyard': ([TIRE_PILE, TIRE_WALL, BARREL, PALLET, DUMPSTER, 'NewRow_93', CONE, HESCO], 110), 'lake': ([BENCH, TABLE, CHAIR, TENT_CANOPY, BARREL] + BUSHES, 60)}
for name, ((dx0, dy0), R, items) in DISTRICTS.items():
    rows, n = DRESS[name]; placed_n = 0
    for _ in range(n * 6):
        if placed_n >= n: break
        a = rng.uniform(0, 6.28); d = rng.uniform(0, R); x, y = dx0 + d * math.cos(a), dy0 + d * math.sin(a)
        if not flat(x, y, 2, 0.5) or not free(x, y, 1.5) or corridor_dist(x, y) < 9 or road_dist(x, y) < 8: continue
        put(rng.choice(rows), x, y, 0, 1, 1, 1, road_yaw(x, y) + rng.choice([0, math.pi / 2])); placed_n += 1; st('district_dressing')
    for _ in range(3):
        a = rng.uniform(0, 6.28); d = rng.uniform(0, R); x, y = dx0 + d * math.cos(a), dy0 + d * math.sin(a)
        if flat(x, y, 4, 0.6) and free(x, y, 4) and corridor_dist(x, y) > 12 and road_dist(x, y) > 10: people(x, y, 4, 6); occupied.append((x, y, 4))
# flow gates across the road every 60 m (posts 7 m apart from the centreline, a beam at 7 m), fences on alternate
# pieces with gaps, cones, parked cars and spectators at the corners: the road is the freestyle spine of the park
flow_gates = []
for (px, py, yaw, k) in road_pieces:
    if k % 6 == 0 and corridor_dist(px, py) > 14 and road_dist(px, py) < 1 and all(math.hypot(px - vx, py - vy) > 30 for (vx, vy) in road) and all(math.hypot(px - fx_, py - fy_) > 40 for (fx_, fy_) in flow_gates):
        g = ground(px, py); flow_gates.append((px, py))
        for sgn in (-1, 1): post(rng.choice(['red', 'blue', 'yellow']), *l2w(px, py, yaw, 0, sgn * 7), 0, 0.6, 0.6, yaw, top=g + 7)
        box('black', px, py, g + 7, 0.6, 0.6, 14.6, yaw); add(rng.choice(NEONS), *l2w(px, py, yaw, 0, 0), g + 7.3, 1, 1, 1, yaw)
        a_, b_ = l2w(px, py, yaw, -12, 0), l2w(px, py, yaw, 12, 0); tube(a_[0], a_[1], g + 3.0, b_[0], b_[1], g + 3.0, 2.5); st('flow_gates')
    if k % 2 == 0:
        for u in (-4, 0, 4):
            for sgn in (-1, 1):
                fx_, fy_ = l2w(px, py, yaw, u, sgn * 6.5)
                if corridor_dist(fx_, fy_) > 9: put(FENCE, fx_, fy_, 0, 1, 1, 1, yaw)
    if k % 4 == 1 and rng.random() < 0.6: put(rng.choice(CARS), *l2w(px, py, yaw, 0, rng.choice([-9.5, 9.5])), 0.05, 1, 1, 1, yaw)
    for sgn in (-1, 1):
        sx_, sy_ = l2w(px, py, yaw, 0, sgn * 7.5)
        if flat(sx_, sy_, 3, 0.6) and corridor_dist(sx_, sy_) > 9: plane(PAVE, sx_, sy_, ground(sx_, sy_) + 0.04, 10, 3, yaw)
        tx_, ty_ = l2w(px, py, yaw, rng.uniform(-3, 3), sgn * 12.5)
        if k % 2 == 1 and corridor_dist(tx_, ty_) > 9 and free(tx_, ty_, 2): s_ = rng.uniform(0.9, 1.3); put(rng.choice(TREES), tx_, ty_, 0, s_, s_, s_, rng.uniform(0, 6.28)); st('road_trees')
for (x0, y0), (x1, y1) in zip(road, road[1:]):
    if corridor_dist(x1, y1) > 16 and free(x1 + 14, y1 + 14, 6): people(x1 + 14, y1 + 14, 5, 6, 0, face=(x1, y1))
bb_n = 0
for (px, py, yaw, k) in road_pieces:
    if k % 6 != 3 or bb_n >= 12: continue
    for side in (1, -1):
        bx_, by_ = l2w(px, py, yaw, 0, side * 20)
        if flat(bx_, by_, 13) and free(bx_, by_, 9) and road_dist(bx_, by_) > 17 and corridor_dist(bx_, by_) > 16:
            billboard(bx_, by_, yaw + (-math.pi / 2 if side > 0 else math.pi / 2), variant=bb_n % 4); bb_n += 1; break
if corridor_dist(-40, 46) > 16: billboard(-40, 46, -math.pi / 2, w=28, h=9, post_h=6, variant=1)                   # north of the pits facing the start line
# ---- 6. Woods and belts: dense forest on the slopes ringing the bowl, four woods inside it, rocks on the scree ----
for (x, y) in ((-320, 40), (20, 180), (-20, -60), (-400, -160), (200, 220), (-120, 260), (-500, -80), (260, -120), (-60, 320), (-320, -300)): zone(wood, x, y, 30, max_slide=120)
for _ in range(3000):
    x, y = rng.uniform(-620, 420), rng.uniform(-380, 480)
    if not has_ground(x, y) or gz(x, y) > G0 + 40 or not free(x, y, 3): continue
    s_ = rng.uniform(0.8, 1.5); put(rng.choice(TREES + PINES + BIG_TREES), x, y, 0, s_, s_, s_, rng.uniform(0, 6.28)); st('bowl_trees')
for _ in range(2500):
    x, y = rng.uniform(-620, 420), rng.uniform(-380, 480)
    if not has_ground(x, y) or not free(x, y, 2): continue
    s_ = rng.uniform(0.7, 2.0); put(rng.choice(ROCKS + BUSHES), x, y, 0, s_, s_, s_, rng.uniform(0, 6.28))
for _ in range(300000):
    if stats.get('slope_trees', 0) >= 22000: break
    x, y = rng.uniform(-1000, 1000), rng.uniform(-1000, 1000)
    if not has_ground(x, y): continue
    h = gz(x, y) - G0
    if h < 3 or h > 130 or not flat(x, y, 6, tol=4.0) or not free(x, y, 3): continue
    s_ = rng.uniform(0.9, 1.6); put(rng.choice(PINES), x, y, 0, s_, s_, s_, rng.uniform(0, 6.28)); st('slope_trees')
for _ in range(6000):
    x, y = rng.uniform(-900, 900), rng.uniform(-900, 900)
    if not has_ground(x, y): continue
    h = gz(x, y) - G0
    if h < 3 or h > 160 or not free(x, y, 3): continue
    s_ = rng.uniform(0.8, 2.5); put(rng.choice(ROCKS + [CLIFF, CLIFF]), x, y, 0, s_, s_, s_, rng.uniform(0, 6.28)); st('slope_rocks')

# ---- clearance pass: only the designed structures may touch the race tube or a feature's flight tube ----
import raceline, mapcheck
CORE = {CONCRETE, BRICK, FLOOR_HOLE_R, FLOOR_HOLE_SQ, COLUMN, COLUMN_BRICK, ASPHALT, PAVE, DIRT, GRAVEL, SAND, WATER, SCAFFOLD_W, CONTAINER_S, CONTAINER_L, TANK_CONT} | set(CUBE.values()) | set(CUBE_HOLE.values()) | set(CYL.values()) | set(WALL_WIN) | {WALL_TRI}   # stacked things stay whole: never delete the bottom of a stack
legs3 = [(START_XY[0], START_XY[1], ground(*START_XY) + START_H)] + [(x, y, z) for (_, x, y, z, _) in gates] + [(START_XY[0], START_XY[1], ground(*START_XY) + START_H)]
def seg_samples(a_, b_, step=1.0):
    n = max(2, int(math.dist(a_, b_) / step)); return [tuple(a_[i] + (b_[i] - a_[i]) * k / n for i in range(3)) for k in range(n + 1)]
race_samples = [p for a_, b_ in zip(legs3, legs3[1:]) for p in seg_samples(a_, b_)]
tube_samples = [(p, r, strict) for (x0, y0, z0, x1, y1, z1, r, strict) in TUBES for p in seg_samples((x0, y0, z0), (x1, y1, z1))]
def near_any_tube(o):
    return any(math.hypot(o.cx - p[0], o.cy - p[1]) < o.rad + r + 0.5 for (p, r, _) in tube_samples)
removed = 0; strict_hits = []
for row in list(instances):
    if row.startswith('decal_') or not raceline.CAT.get(row, {}).get('bounds'): continue
    keep = []
    for t in instances[row]:
        o = raceline.OBB(row, t, raceline.CAT[row])
        on_race = corridor_dist(o.cx, o.cy) < o.rad + 2.5 and any(o.hit(p, 2.5) for p in race_samples)
        in_tube = near_any_tube(o) and any(o.hit(p, r + 0.3) for (p, r, _) in tube_samples)
        if row in CORE:
            top = o.T[2] + (o.o[2] + o.e[2]) * o.S[2]                                       # floors under a tube are the floor, not a blocker
            if in_tube and any(o.hit(p, r) for (p, r, strict) in tube_samples if strict and top > p[2] - 1.0): strict_hits.append((row, round(o.cx), round(o.cy), round(o.T[2], 1)))
            keep.append(t)
        elif on_race or in_tube: removed += 1
        else: keep.append(t)
    instances[row] = keep
instances = {r: v for r, v in instances.items() if v}
st('cleared_from_flight_tubes', removed)
if strict_hits: raise SystemExit(f'STRUCTURE INSIDE A FEATURE GAP: {strict_hits[:12]} ({len(strict_hits)} total)')
def gate_yaw(prev, cur, nxt):
    """Flight bearing through a gate = direction from the previous gate to the next; stored yaw = bearing - 90 deg."""
    return math.atan2(nxt[1] - prev[1], nxt[0] - prev[0]) - math.pi / 2
G0s = ground(*START_XY); start_bearing = math.atan2(gates[0][2] - START_XY[1], gates[0][1] - START_XY[0]); start_yaw = start_bearing - math.pi / 2
start_tf = tf(START_XY[0], START_XY[1], G0s + START_H, quat_yaw(start_yaw))
SPAWN_XY = (START_XY[0] - SPAWN_BACK * math.cos(start_bearing), START_XY[1] - SPAWN_BACK * math.sin(start_bearing))
checkpoints = []; spoints = [tf(SPAWN_XY[0], SPAWN_XY[1], ground(*SPAWN_XY) + START_H, quat_yaw(start_yaw))]           # spawn behind the start line, facing it
for i, (row, x, y, zf, sc) in enumerate(gates):
    prev = START_XY if i == 0 else gates[i - 1][1:3]; nxt = START_XY if i == len(gates) - 1 else gates[i + 1][1:3]
    yaw = gate_yaw(prev, (x, y), nxt); z = zf - GATE_FLY.get(row, 0.0) * sc
    scale = (sc, sc, sc) if row.startswith('Infl') else (sc, 1.0, sc)                                                       # Workshop: inflatables uniform, Gate2-type gates scaled in X/Z only
    checkpoints.append(dict(Transform=tf(x, y, z, quat_yaw(yaw), scale), RowName=row)); spoints.append(tf(x, y, z - 0.5, quat_yaw(yaw)))
race = dict(CheckPoints=checkpoints, StartTransform=start_tf, Laps=3, BestTime=0, Spoints=spoints)
legs3.insert(0, (SPAWN_XY[0], SPAWN_XY[1], ground(*SPAWN_XY) + START_H))
# ---- line-of-flight validation: every leg must be clear of every mesh (1.5 m tube) and above the terrain ----
_data = dict(S_AssetsTransform=[dict(Rname=r, Transform=v) for r, v in instances.items()], Race=race)
_obbs = raceline.load_obbs(_data)
print('zones:', {k: (round(v[0]), round(v[1]), round(v[2], 2)) for k, v in ZONE_AT.items()})
print('stats:', stats)
blocked = raceline.check(_data, clearance=1.5, land=LAND, verbose=True, obbs=_obbs)
if blocked: raise SystemExit(f'RACE NOT FLYABLE: {blocked} blocked legs (see above)')
print('race: all', len(gates) + 1, 'legs clear')
_fl, _bu, _off = mapcheck.run(_data, LAND, struct_rows=CORE | {LED_V, SCAFFOLD_W, BALLOON, ARCH} | set(NEONS), verbose=True)
if sum(map(len, _fl.values())) > 0: raise SystemExit('FLOATING OBJECTS (see above)')

# =============================== OUTPUT =========================================
cam = (-120.0, -90.0, G0 + 60.0)
cam_yaw = math.degrees(math.atan2(0 - cam[1], 0 - cam[0])); cam_pitch = math.degrees(math.atan2(G0 + 10 - cam[2], math.hypot(cam[0], cam[1])))
rows_all = dict(instances); rows_all.update(decal_rows)
map_json = {'S_AssetsTransform': [dict(Rname=r, Transform=t, UniqueGroupTag=['None'] * len(t)) for r, t in rows_all.items()],
            'BaseMapRow': 'BaseLandscape04', 'WeatherIndex': 0, 'Race': race,
            'CamLoc': tf(cam[0], cam[1], cam[2], quat_pitch_yaw(cam_pitch, cam_yaw)), 'CustomWeather': dict(timeOfDay=15.5, northyaw=220, Cloud=0.2)}
info = {'BaseMapRow': 'BaseLandscape04', 'Name': DISPLAY, 'CreatorSteamID': STEAM_ID, 'CreationTimeUnix': int(time.time()), 'Track': True}
out_dir = os.path.join(ROOT, 'maps', NAME)
if os.path.isdir(out_dir): shutil.rmtree(out_dir)
os.makedirs(out_dir)
json.dump(map_json, open(os.path.join(out_dir, NAME + '.json'), 'w')); open(os.path.join(out_dir, NAME + '.info'), 'w').write(json.dumps(info))
if decal_files:
    os.makedirs(os.path.join(out_dir, 'Decals'))
    for name, (variant, wide) in decal_files.items(): billboard_png(variant, os.path.join(out_dir, 'Decals', name), wide)
    lib = os.path.join(os.path.dirname(GAME_USER_MAPS), 'UserDecals'); os.makedirs(lib, exist_ok=True)      # the editor's own PNG library
    lib2 = os.path.join(os.path.dirname(GAME_USER_MAPS), 'MapDecals'); os.makedirs(lib2, exist_ok=True)
    for name in decal_files:
        shutil.copy(os.path.join(out_dir, 'Decals', name), os.path.join(lib, name)); shutil.copy(os.path.join(out_dir, 'Decals', name), os.path.join(lib2, name))
from PIL import Image, ImageDraw
W = 1024; img = Image.new('RGB', (W, W), (40, 60, 35)); d = ImageDraw.Draw(img); sc = W / 1200.0
def px(x, y): return (y * sc + W / 2, W / 2 - x * sc)
for i in range(0, W, 8):
    for j in range(0, W, 8):
        x = (W / 2 - j) / sc; y = (i - W / 2) / sc; h = gz(x, y) - G0
        if h > 2: d.rectangle((i, j, i + 8, j + 8), fill=(min(255, 60 + int(h * 1.2)),) * 3)
for r, trs in instances.items():
    for t in trs:
        x, y = t['Translation']['X'] / 100, t['Translation']['Y'] / 100
        col = (70, 110, 200) if r == WATER else (60, 60, 65) if r == ASPHALT else (150, 90, 60) if r in [BRICK] + WALL_WIN else (200, 195, 185) if r == CONCRETE else (90, 160, 255) if r == CUBE['blue'] else (180, 180, 180)
        d.rectangle((px(x + 1.5, y - 1.5), px(x - 1.5, y + 1.5)), fill=col)
for cp in checkpoints:
    x, y = cp['Transform']['Translation']['X'] / 100, cp['Transform']['Translation']['Y'] / 100; p = px(x, y); d.ellipse((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), fill=(255, 220, 40))
d.text((20, W - 40), DISPLAY, fill=(240, 240, 240)); img.save(os.path.join(out_dir, 'Thumbnail.jpg'), quality=88)
dst = os.path.join(GAME_USER_MAPS, NAME)
if os.path.isdir(dst): shutil.rmtree(dst)
shutil.copytree(out_dir, dst)
print(f'{NAME}: {sum(len(v) for v in rows_all.values())} instances, {len(checkpoints)} gates -> {dst}')
print(stats)
