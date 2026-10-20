#!/usr/bin/env python3
"""Asset-first building blocks shared by every Uncrashed map generator.

The rule this module enforces: use a real editor asset wherever one exists (textured building meshes, stairs,
parapets, fences, arches, benches, kiosks), and fall back to cubes and concrete slabs only for shapes the catalogue
does not have. It also owns the two placement rules that caused visible bugs: surface layering (every ground
material gets its own height band so planes never z-fight) and bench orientation (long axis along the path, seat
facing it).

All lengths are metres; rows are DT_MapEditorAssets ids ("NewRow_N"). A generator supplies its own `add()` and the
kit returns the instances through it, so this file stays free of map state.

    kit = MapKit(add, box, plane, ground_z=0.06)
    kit.building(footprint_pts, height_m, tags)       # textured mesh tiles when a mesh fits, box massing otherwise
    kit.bridge(cx, cy, length, width, yaw, clear_h)   # real stone arch portals + deck + stone parapets + stairs
    kit.stairs(x, y, yaw, rise)                       # SM_Stair_A scaled to the rise
    kit.wall(pts, kind)                               # concrete fence / brick wall / parapet / park fence meshes
    kit.bench(x, y, path_yaw, side)                   # correctly oriented bench
    kit.surface(row, x, y, lx, ly, yaw, piece_index)  # plane on the right height band, staggered against overlap
"""

import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = json.load(open(os.path.join(ROOT, "data", "catalog.json")))

# ---- rows ----------------------------------------------------------------------------------------------------
CUBE = dict(
    default="NewRow_13",
    yellow="NewRow_46",
    blue="NewRow_79",
    red="NewRow_84",
    green="NewRow_268",
    grey="NewRow_256",
    violet="NewRow_378",
    black="NewRow_109",
)
CONCRETE, BRICK = "NewRow_303", "NewRow_318"
ARCH = "NewRow_45"  # SM_NeoArch_ME 7.0 x 1.5 x 9.9 m, base pivot: a real stone arch
STAIR_A = "NewRow_787"  # SM_Stair_A 3.6 x 8.6 x 5.7 m: a real flight of stairs (pivot at one side of the foot)
STAIR_RISE = 5.3  # m from the stair's base to its top landing (its bounds dip 0.37 m below the pivot)
STAIR_CLIMB = 1  # +1: the mesh climbs toward its local +Y; -1: toward -Y (set from the showroom probe)
STAIRS_SMALL = "NewRow_106"  # sm_Stairs_01_01 2.4 x 3.9 x 3.7 m
PARAPET = "NewRow_275"  # SM_parapet_fence_small 0.94 x 0.12 x 0.98 m: stone parapet section
HANDRAIL = "NewRow_276"  # sm_Handrail_01_01 2.08 m
CONCRETE_FENCE = "NewRow_2"  # SM_concrete_fence_01 4.88 x 0.25 x 3.64 m: retaining-wall panel
PARK_FENCE = "NewRow_777"  # SM_RaceTrack_Fence_02 4 x 0.13 x 2.6 m
TALL_FENCE = "NewRow_780"  # SM_Fence04 0.1 x 4 x 2.74 m (long axis Y)
WOOD_FENCE_DOOR = "NewRow_88"
BENCH = "NewRow_204"  # SM_Bench03 0.9 x 2.19 x 1.04 m: long axis is local Y, seat front is local +X
KIOSKS = ["NewRow_230", "NewRow_231", "NewRow_233"]  # Christmas booths: market stalls / kiosks
BUS_STOPS = ["NewRow_29", "NewRow_43"]
WOOD_DECK = "NewRow_184"  # SM_BaseGround with wood planks: boardwalks and bridge decks
DECK_ON_POSTS = "NewRow_221"  # SM_Deck_Floor_04 10.3 x 13.2 x 4.1 m: a wooden deck on posts = a rustic footbridge
BOWER = "NewRow_205"  # SM_Bower02 7.8 x 6.4 x 7.6 m: a park gazebo / pergola
CAFE = ["NewRow_228", "NewRow_229"]  # SM_CafeBuilding01/04: park cafes
PLAYGROUND = ["NewRow_287", "NewRow_288", "NewRow_289", "NewRow_293", "NewRow_295", "NewRow_296", "NewRow_643"]
WILLOW = "NewRow_171"
GROUND = dict(
    asphalt="NewRow_182",
    pavement="NewRow_185",
    pavement2="NewRow_197",
    pavement3="NewRow_186",
    flagstone="NewRow_376",
    dirt="NewRow_180",
    gravel="NewRow_181",
    sand="NewRow_662",
    wood="NewRow_184",
)
# textured building meshes the massing prefers over boxes (name -> (row, max vertical stack, flat roof))
BUILDING_MESHES = {
    "NewRow_794": 3,
    "NewRow_795": 3,
    "NewRow_796": 3,
    "NewRow_797": 3,
    "NewRow_9": 1,
    "NewRow_95": 1,
    "NewRow_96": 1,
    "NewRow_97": 1,
}
HOUSES = ["NewRow_788", "NewRow_789", "NewRow_790", "NewRow_791", "NewRow_793"]

# ---- surface height bands (metres above the ground top): distinct per material, so no two planes share a height
LAYER = dict(
    lawn=0.00,
    dirt=0.05,
    gravel=0.07,
    sand=0.07,
    asphalt=0.10,
    pavement=0.14,
    pavement2=0.14,
    pavement3=0.14,
    flagstone=0.16,
    wood=0.18,
    plaza=0.20,
    sidewalk=0.22,
)
STAGGER = 0.004  # consecutive overlapping pieces of one path alternate by this much


def size(row):
    """(L, W, H) of a row's mesh bounds in metres, or (1, 1, 1) if unknown."""
    b = CAT.get(row, {}).get("bounds")
    return (2 * b["extent"][0] / 100, 2 * b["extent"][1] / 100, 2 * b["extent"][2] / 100) if b else (1.0, 1.0, 1.0)


def base_offset(row):
    """Mesh bottom relative to the pivot (m); negative means the mesh hangs below the pivot."""
    b = CAT.get(row, {}).get("bounds")
    return (b["origin"][2] - b["extent"][2]) / 100 if b else 0.0


def rest(row):
    """Correction so a row placed at ground height touches the ground (only lifts bases that sit above the pivot)."""
    bo = base_offset(row)
    return -bo if bo > 0.05 else 0.0


def l2w(cx, cy, yaw, u, v):
    """Local (u along yaw, v to its left) -> world."""
    c, s = math.cos(yaw), math.sin(yaw)
    return cx + u * c - v * s, cy + u * s + v * c


class MapKit:
    """Asset-first placement helpers bound to a generator's add()/box()/plane() functions.

    add(row, x, y, z, sx, sy, sz, yaw)       places a row at pivot (x, y, z) m
    box(kind, cx, cy, z0, h, lx, ly, yaw)    the generator's cube/concrete/brick massing helper
    plane(row, x, y, z_top, lx, ly, yaw)     the generator's ground-plane helper (top face at z_top)
    """

    def __init__(self, add, box, plane, ground_z=0.06, rng=None, stats=None):
        """`ground_z` is the ground-top height (m) on a flat board, or a callable ground_z(x, y) -> height for a
        landscape (used wherever the kit puts something on the ground)."""
        self.add, self.box, self.plane = add, box, plane
        self._ground = ground_z if callable(ground_z) else (lambda x, y: ground_z)
        self.z0 = ground_z if not callable(ground_z) else 0.0
        self.rng = rng or random.Random(3)
        self.stats = stats if stats is not None else {}

    def g(self, x, y):
        """Ground-top height at (x, y)."""
        return self._ground(x, y)

    def place(self, row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0):
        """Place a mesh so that the CENTRE OF ITS BOUNDING BOX stands at (x, y) with its BOTTOM at height z,
        whatever the mesh's pivot is. Several editor meshes have the pivot at a corner or an end (SM_Stair_A at
        one side of the foot, SM_Deck_Floor_04 at a corner), so placing their pivot at the centre of a bridge
        put them metres off it (seen in the game); this helper compensates from the catalogue bounds."""
        b = CAT.get(row, {}).get("bounds")
        if not b:
            self.add(row, x, y, z, sx, sy, sz, yaw)
            return
        ox, oy = b["origin"][0] / 100 * sx, b["origin"][1] / 100 * sy  # bbox centre relative to the pivot
        oz = (b["origin"][2] - b["extent"][2]) / 100 * sz  # bbox bottom relative to the pivot
        c, s_ = math.cos(yaw), math.sin(yaw)
        self.add(row, x - (ox * c - oy * s_), y - (ox * s_ + oy * c), z - oz, sx, sy, sz, yaw)

    def st(self, k, n=1):
        self.stats[k] = self.stats.get(k, 0) + n

    # ---- surfaces -------------------------------------------------------------------------------------------
    def surface(self, material, x, y, lx, ly, yaw=0.0, piece=0, z_base=None):
        """A ground plane on its material's height band. `piece` staggers consecutive overlapping pieces of the
        same path so their overlap wedges never share a depth."""
        z = (self.g(x, y) if z_base is None else z_base) + LAYER.get(material, 0.1) + STAGGER * (piece % 2)
        self.plane(GROUND.get(material, material), x, y, z, lx, ly, yaw)

    def ribbon(self, pts, width, material, max_piece=20.0):
        """Pave a polyline: one plane per piece, pieces at most `max_piece` m, each on its own stagger step."""
        piece = 0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            if L < 0.5:
                continue
            n = max(1, int(math.ceil(L / max_piece)))
            yaw = math.atan2(y1 - y0, x1 - x0)
            for q in range(n):
                t = (q + 0.5) / n
                self.surface(material, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, L / n + 0.4, width, yaw, piece)
                piece += 1
        return piece

    # ---- furniture ------------------------------------------------------------------------------------------
    def bench(self, x, y, path_yaw, side=1):
        """Bench beside a path: long axis (mesh local Y) parallel to the path, seat (local +X) facing the path.
        `side` +1 puts the bench on the path's left (local +v) side, -1 on the right."""
        yaw = path_yaw - side * math.pi / 2
        self.add(BENCH, x, y, self.g(x, y), 1.0, 1.0, 1.0, yaw)
        self.st("benches")

    def kiosk(self, x, y, yaw):
        """A market stall / kiosk mesh (the editor's Christmas booths are the only kiosk assets)."""
        row = self.rng.choice(KIOSKS)
        self.add(row, x, y, self.g(x, y) + rest(row), 1.0, 1.0, 1.0, yaw)
        self.st("kiosks")

    # ---- vehicles ---------------------------------------------------------------------------------------------
    def vehicle(self, row, x, y, heading, on_road=None, lane=0.0):
        """A vehicle on a road: its long axis (from the mesh bounds) is turned to `heading` (radians, the road
        direction), it is offset `lane` metres to the right, and it is refused unless `on_road(x, y)` says the
        ground there is carriageway (counted in stats as vehicles_dropped_off_road)."""
        L, W, H = size(row)
        px, py = l2w(x, y, heading, 0, -lane)
        if on_road is not None and not on_road(px, py):
            self.st("vehicles_dropped_off_road")
            return False
        yaw = heading + (math.pi / 2 if W > L else 0.0)  # meshes whose long axis is local Y get a quarter turn
        self.add(row, px, py, self.g(px, py) + rest(row), 1.0, 1.0, 1.0, yaw)
        self.st("vehicles")
        return True

    # ---- walls, fences, stairs ---------------------------------------------------------------------------------
    def wall(self, pts, kind="brick", height=None):
        """A wall or fence along a polyline from real sections. kinds: 'retaining' (concrete fence panels),
        'brick' (SM_ConcreteWall01 panels), 'parapet' (stone parapet sections stretched to 3.76 m), 'fence'
        (park fence), 'tall_fence'. `height` scales the section height (m)."""
        spec = {
            "retaining": (CONCRETE_FENCE, 4.88, 4.88, "x"),
            "parapet": (PARAPET, 3.76, 0.94, "x"),  # (row, length covered per section, mesh length, long axis)
            "fence": (PARK_FENCE, 4.0, 4.0, "x"),
            "tall_fence": (TALL_FENCE, 4.0, 4.0, "y"),
            "brick": (BRICK, 4.0, 4.0, "y"),
        }
        row, seg, mesh_len, axis = spec.get(kind, spec["brick"])
        h = (height / size(row)[2]) if height else 1.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            if L < 0.3:
                continue
            n = max(1, int(round(L / seg)))
            yaw = math.atan2(y1 - y0, x1 - x0)
            sfit = L / (n * mesh_len)
            for q in range(n):
                t = (q + 0.5) / n
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                gz_ = self.g(x, y) + rest(row) - 0.15  # 15 cm sunk so slopes never show a gap
                if axis == "x":
                    self.add(row, x, y, gz_, sfit, 1.0, h, yaw)
                else:
                    self.add(row, x, y, gz_, 1.0, sfit, h, yaw - math.pi / 2)
                self.st("wall_sections")

    def stairs(self, x, y, yaw, rise, width=None):
        """A real flight of stairs (SM_Stair_A: 3.6 m wide, 8.6 m run, 5.3 m rise above its base) scaled to `rise`,
        climbing along `yaw` from its foot at (x, y). The run is the mesh's local Y and the mesh climbs toward
        local STAIR_CLIMB*Y (measured in the showroom); the pivot sits at one side of the foot, so the stair is
        placed by its bounding box, never by its pivot."""
        L, W, H = size(STAIR_A)
        s = rise / STAIR_RISE
        sw = (width / L) if width else max(0.6, s)
        cx, cy = l2w(x, y, yaw, W * s / 2, 0)  # bbox centre is half a run up the slope from the foot
        self.place(STAIR_A, cx, cy, self.g(x, y), sw, s, s, yaw - STAIR_CLIMB * math.pi / 2)
        self.st("stairs")

    # ---- water features ---------------------------------------------------------------------------------------
    def basin(self, cx, cy, radius, rim_h=0.75, rim_w=0.8, z_base=None, water_row="NewRow_183"):
        """A round fountain basin: a solid masonry ring (concrete segments `rim_w` wide, `rim_h` tall) with water
        tiles entirely inside it, 0.25 m below the rim. A thin brick wall reads as a rail from the air and 3 m
        tiles poked through the ring (seen in the game), so the ring is thick and the tiles stop 1.6 m short."""
        z0 = self.g(cx, cy) if z_base is None else z_base
        n = max(12, int(2 * math.pi * radius / 2.5))
        for q in range(n):
            a = (q + 0.5) / n * 2 * math.pi
            px, py = cx + radius * math.cos(a), cy + radius * math.sin(a)
            self.box("concrete", px, py, z0, rim_h, 2 * math.pi * radius / n + 0.15, rim_w, a + math.pi / 2)
        step = 2.0
        k = int(radius // step) + 1
        for j in range(-k, k + 1):
            for i in range(-k, k + 1):
                if math.hypot(i * step, j * step) < radius - rim_w / 2 - 1.45:
                    self.add(water_row, cx + i * step, cy + j * step, z0 + rim_h - 0.25, step / 4, step / 4, 1.0)
        self.st("basins")

    # ---- bridges and arches ----------------------------------------------------------------------------------
    def wooden_bridge(self, cx, cy, length, width, yaw, clear_h=3.2):
        """A rustic footbridge from the lake-house deck-on-posts mesh (13.2 m long, 10.3 m wide, 4.1 m tall),
        scaled to the span, with a real flight of stairs at each end. Spans up to about 16 m."""
        L, W, H = size(DECK_ON_POSTS)
        sy, sx, sz = (
            max(0.5, min(1.3, length / L)),
            max(0.35, min(1.0, width / W)),
            max(0.8, min(1.2, (clear_h + 0.5) / H)),
        )
        z0 = self.g(cx, cy)
        self.place(DECK_ON_POSTS, cx, cy, z0 - 0.2, sx, sy, sz, yaw + math.pi / 2)  # corner pivot: place by bbox
        top = z0 - 0.2 + H * sz
        _, run, _ = size(STAIR_A)
        for sgn in (-1, 1):  # a stair at each end, its top landing meeting the deck edge
            foot = l2w(cx, cy, yaw, sgn * (length / 2 + run * (top - z0) / STAIR_RISE), 0)
            self.stairs(foot[0], foot[1], yaw + (math.pi if sgn > 0 else 0.0), top - z0, width)
        self.st("wooden_bridges")

    def bridge(self, cx, cy, length, width, yaw, clear_h=3.2, deck="flagstone", stairs=None, name="", span=None):
        """A stone footbridge you can fly under, from real pieces: brick piers at each end with a rectangular
        passage between them (the only arch mesh in the game is a futuristic one, so the opening is square),
        a concrete deck surfaced with `deck`, stone parapets, and at each end either a real flight of stairs
        (short footbridges, the default under 24 m) or a textured flagstone ramp between brick embankment walls.
        `length` runs along `yaw`; the passage runs across it. Heights in metres above the ground at the centre."""
        z0 = self.g(cx, cy)
        if span is not None:  # over a road cut the deck spans just the cut, never the whole mapped approach
            length = min(length, span)
        H = clear_h + 0.6  # deck top
        if stairs is None:
            stairs = length < 24
        pier_t = 1.6
        for sgn in (-1, 1):  # the two faces: piers either side of the passage
            u = sgn * (length / 2 - pier_t / 2)
            for side in (-1, 1):
                self.box(
                    "brick", *l2w(cx, cy, yaw, u, side * (width / 2 + 1.0)), z0 - 0.3, H - 0.6 + 0.3, pier_t, 2.0, yaw
                )
            self.box(
                "concrete", *l2w(cx, cy, yaw, u, 0), z0 + H - 0.6, 0.6, pier_t, width + 4.0, yaw
            )  # lintel over the passage
        self.box("concrete", cx, cy, z0 + H - 0.6, 0.6, length, width, yaw)
        self.surface(deck, cx, cy, length, width, yaw, z_base=z0 + H - 0.6)
        for sgn in (-1, 1):
            edge = [
                l2w(cx, cy, yaw, -length / 2, sgn * (width / 2 - 0.15)),
                l2w(cx, cy, yaw, length / 2, sgn * (width / 2 - 0.15)),
            ]
            self._raised_parapet(edge, z0 + H)
        for sgn in (-1, 1):  # approaches
            if stairs:
                foot = l2w(cx, cy, yaw, sgn * (length / 2 + size(STAIR_A)[1] * H / STAIR_RISE), 0)
                self.stairs(foot[0], foot[1], yaw + (math.pi if sgn > 0 else 0.0), H, width)
            else:
                run = max(12.0, H * 4.0)
                far = l2w(cx, cy, yaw, sgn * (length / 2 + run), 0)
                near = l2w(cx, cy, yaw, sgn * length / 2, 0)
                self._ramp(far, near, self.g(*far), z0 + H, width, material=deck)
                for side in (-1, 1):  # embankment walls along the ramp
                    a_ = l2w(cx, cy, yaw, sgn * (length / 2 + run), side * (width / 2 + 0.3))
                    b_ = l2w(cx, cy, yaw, sgn * length / 2, side * (width / 2 + 0.3))
                    self.wall([a_, b_], "brick", H * 0.5)
        self.st("bridges")

    def _raised_parapet(self, pts, z):
        (x0, y0), (x1, y1) = pts
        L = math.hypot(x1 - x0, y1 - y0)
        pl = size(PARAPET)[0]  # 0.94 m sections at natural size: stretched 4x the railing dissolves into posts
        n = max(1, int(round(L / pl)))
        yaw = math.atan2(y1 - y0, x1 - x0)
        for q in range(n):
            t = (q + 0.5) / n
            self.add(PARAPET, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, z, L / (n * pl), 1.0, 1.0, yaw)

    def _ramp(self, a, b, z0, z1, width, thick=0.4, material="flagstone"):
        """Pitched slab from a (height z0) to b (height z1): a textured ground plane tilted to the slope, over a grey
        cube body so it reads as solid from the side."""
        (x0, y0), (x1, y1) = a, b
        L = math.hypot(x1 - x0, y1 - y0)
        yaw = math.atan2(y1 - y0, x1 - x0)
        pitch = math.atan2(z1 - z0, L)
        P, Y = pitch / 2, yaw / 2
        rot = dict(
            X=math.sin(P) * math.sin(Y),
            Y=-math.sin(P) * math.cos(Y),
            Z=math.cos(P) * math.sin(Y),
            W=math.cos(P) * math.cos(Y),
        )
        slant = math.hypot(L, z1 - z0)
        self.add(CUBE["grey"], (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2 - thick / 2, slant, width, thick, 0.0, rot)
        self.add(
            GROUND.get(material, material),
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            (z0 + z1) / 2 + 0.03,
            slant / 4,
            width / 4,
            1.0,
            0.0,
            rot,
        )

    # ---- buildings --------------------------------------------------------------------------------------------
    def try_mesh(self, lx, ly, h):
        """Best textured building mesh tiling for a lx x ly x h box, or None (scales kept within 0.7..1.45)."""
        best = None
        for row, max_stack in BUILDING_MESHES.items():
            mx, my, mh = size(row)
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

    def place_mesh(self, fit, cx, cy, lx, ly, th):
        """Tile the fitted mesh over the rectangle; returns the roof height."""
        row, nx, ny, nz, sx, sy, sz, swap = fit
        mx, my, mh = size(row)
        yaw = th + (math.pi / 2 if swap else 0)
        for i in range(nx):
            for j in range(ny):
                x, y = l2w(cx, cy, th, -lx / 2 + (i + 0.5) * lx / nx, -ly / 2 + (j + 0.5) * ly / ny)
                for k in range(nz):
                    self.add(row, x, y, self.g(cx, cy) - 0.2 + k * mh * sz, sx, sy, sz, yaw)
                    self.st("mesh_tiles")
        return self.g(cx, cy) - 0.2 + nz * mh * sz

    def house(self, cx, cy, lx, ly, th):
        """A textured house mesh fitted to a small footprint (<= ~18 m); returns True when one fitted."""
        for row in sorted(HOUSES, key=lambda r: abs(size(r)[0] * size(r)[1] - lx * ly)):
            mx, my, mh = size(row)
            for swap in (False, True):
                ax, ay = (my, mx) if swap else (mx, my)
                sx, sy = lx / ax, ly / ay
                if 0.75 <= sx <= 1.4 and 0.75 <= sy <= 1.4:
                    s = min(sx, sy)
                    self.add(row, cx, cy, self.g(cx, cy) + 0.25, sx, sy, s, th + (math.pi / 2 if swap else 0))
                    self.st("houses")
                    return True
        return False

    def building(self, rects, h, kind="concrete", named=False, roof=None):
        """Massing for a footprint already split into rectangles [(cx, cy, lx, ly, th)]: a textured mesh
        tiling when one fits (unnamed buildings up to 60 m, houses for small footprints), box tiers otherwise.
        Returns a list of (cx, cy, lx, ly, th, roof_z, used_mesh)."""
        out = []
        for cx, cy, lx, ly, th in rects:
            if not named and h <= 12 and max(lx, ly) <= 20 and self.house(cx, cy, lx, ly, th):
                out.append((cx, cy, lx, ly, th, self.g(cx, cy) + h, True))
                continue
            fit = self.try_mesh(lx, ly, h) if (h <= 60 and not named) else None
            if fit:
                top = self.place_mesh(fit, cx, cy, lx, ly, th)
                out.append((cx, cy, lx, ly, th, top, True))
                continue
            gz_ = self.g(cx, cy)
            self.box(kind, cx, cy, gz_ - 0.5, h + 0.5, lx, ly, th)  # half a metre of foundation hides any slope
            out.append((cx, cy, lx, ly, th, gz_ + h, False))
        return out
