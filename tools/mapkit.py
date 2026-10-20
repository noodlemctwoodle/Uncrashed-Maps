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
STAIR_A = "NewRow_787"  # SM_Stair_A 3.6 x 8.6 x 5.7 m: a real flight of stairs
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
        """A real flight of stairs (SM_Stair_A, 8.6 m run, 5.7 m rise) scaled to `rise`, climbing along `yaw`
        from its foot at (x, y). The mesh's run is its local Y, so it is placed with its foot at the pivot."""
        L, W, H = size(STAIR_A)
        s = rise / H
        sw = (width / L) if width else max(0.6, s)
        self.add(STAIR_A, *l2w(x, y, yaw, (W * s) / 2, 0), self.g(x, y), sw, s, s, yaw - math.pi / 2)
        self.st("stairs")

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
        self.add(DECK_ON_POSTS, cx, cy, z0 - 0.2, sx, sy, sz, yaw + math.pi / 2)
        top = z0 - 0.2 + H * sz
        for sgn in (-1, 1):
            foot = l2w(cx, cy, yaw, sgn * (length / 2 + 8.6 * top / 5.67 * 0.5), 0)
            self.stairs(foot[0], foot[1], yaw + (math.pi if sgn > 0 else 0.0), top - z0, width)
        self.st("wooden_bridges")

    def bridge(self, cx, cy, length, width, yaw, clear_h=3.2, deck="flagstone", stairs=None, name=""):
        """A stone footbridge you can fly under, from real pieces: brick piers at each end with a rectangular
        passage between them (the only arch mesh in the game is a futuristic one, so the opening is square),
        a concrete deck surfaced with `deck`, stone parapets, and at each end either a real flight of stairs
        (short footbridges, the default under 24 m) or a textured flagstone ramp between brick embankment walls.
        `length` runs along `yaw`; the passage runs across it. Heights in metres above the ground at the centre."""
        z0 = self.g(cx, cy)
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
                foot = l2w(cx, cy, yaw, sgn * (length / 2 + 8.6 * H / 5.67), 0)
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
        n = max(1, int(round(L / 3.76)))
        yaw = math.atan2(y1 - y0, x1 - x0)
        for q in range(n):
            t = (q + 0.5) / n
            self.add(PARAPET, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, z, L / (n * 0.94), 1.0, 1.0, yaw)

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
