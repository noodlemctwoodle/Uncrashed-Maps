#!/usr/bin/env python3
"""Scene: the one object every map, the prefab showroom and the prefab tests build into.

A part (tools/prefabs.py) that was checked in the showroom renders identically in a real map because both go
through this class: the same ground sampler, the same add()/box()/plane() primitives, the same occupancy grid,
the same keep-clear rule, the same writer and the same checks. Map builders only decide WHERE parts go.

    sc = Scene("CentralPark", "New York City - Central Park", base="BaseLandscape02")
    prefabs.road(sc, [(0, 0), (200, 40)], width=12)
    sc.write(cam=(0, 420, 95, -90, -12))      # maps/<Name>/ and the game's MapEditor/User/<Name>/
    sc.check()                                # floaters, buried, off-landscape, take-off clearance

Lengths in metres, angles in radians (camera yaw/pitch in degrees, as the editor stores them).
"""

import json
import math
import os
import random
import shutil
import time

import mapcheck
from landscape import Landscape
from mapkit import BRICK, CONCRETE, CUBE, CYL, MapKit, rest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
STEAM_ID = os.environ.get("UNCRASHED_STEAM_ID", "76561197969360950")
GAME_USER_MAPS = os.path.expanduser(f"~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User")

# occupancy codes (what already stands on a 4 m cell): parts refuse to put things where they do not belong
FREE, PATH, WATER, HARD, BUILDING, ROAD, SIDEWALK, BRIDGE = 0, 1, 2, 3, 4, 6, 7, 8
GROUND_LIFT = 0.02  # every ground height is lifted this much so surfaces never sink into the landscape


class Flat:
    """A flat landscape (the Empty board, or the tests): constant height inside a 3024 m half-size board."""

    def __init__(self, z_cm=0.0):
        self.z = z_cm

    def height_cm(self, x, y):
        return self.z if abs(x) < 302400 and abs(y) < 302400 else None


def quat_yaw(yaw):
    """Quaternion for a yaw (radians) about +Z."""
    return dict(X=0.0, Y=0.0, Z=math.sin(yaw / 2), W=math.cos(yaw / 2))


def quat_pitch_yaw(pitch_deg, yaw_deg):
    """Quaternion for pitch then yaw in degrees (roll 0), as UE's FRotator::Quaternion."""
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2
    SP, CP, SY, CY = math.sin(P), math.cos(P), math.sin(Y), math.cos(Y)
    return dict(X=SP * SY, Y=-SP * CY, Z=CP * SY, W=CP * CY)


def tf(x, y, z, rot, s=(1, 1, 1)):
    """Map-JSON transform: metres -> Unreal centimetres."""
    return dict(
        Rotation=rot,
        Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)),
        Scale3D=dict(X=round(s[0], 4), Y=round(s[1], 4), Z=round(s[2], 4)),
    )


class Scene:
    def __init__(
        self, name, display=None, base="BaseLandscape02", flat_z=None, seed=7, grid=(-1300, -1500, 2600, 3000)
    ):
        """`base` is the level row (BaseLandscape02 = the grassy landscape); `flat_z` (m) uses a flat ground instead
        (tests, the Empty board). `grid` is the occupancy grid origin and size in metres (4 m cells)."""
        self.name, self.display, self.base = name, display or name, base
        if flat_z is not None:
            self.land = Flat(flat_z * 100)
            self.board = 3000.0
        else:
            self.land = Landscape(os.path.join(DATA, "extracted/Uncrashed/Content/MapEditor/BaseLevel/L_" + base))
            self.board = 1205.0  # BaseLandscape02's far edges; the near edges are enforced by the sampler
        self.rng = random.Random(seed)
        self.instances, self.stats = {}, {}
        self.keep_clear = [(0.0, 0.0, 5.0)]  # (x, y, r): the spawn; parts add fountains, stages, ...
        self.roads = []  # (pts, width) of every carriageway laid, for the geometry tests
        self.cell = 4.0
        self.gx0, self.gy0 = grid[0], grid[1]
        self.gnx, self.gny = int(grid[2] / self.cell), int(grid[3] / self.cell)
        self.occ = bytearray(self.gnx * self.gny)
        self.g0 = self.ground(0.0, 0.0) or GROUND_LIFT
        self.kit = MapKit(self.add, self.box, self.plane, ground_z=self.g, rng=self.rng, stats=self.stats)

    def __getattr__(self, k):  # the kit's recipes read as scene methods: sc.bench(), sc.wall(), sc.bridge() ...
        return getattr(self.kit, k)

    # ---- ground ---------------------------------------------------------------------------------------------
    def ground(self, x, y):
        """Ground-top height (m) at (x, y), or None off the landscape."""
        h = self.land.height_cm(x * 100, y * 100)
        return None if h is None else h / 100.0 + GROUND_LIFT

    def g(self, x, y):
        """Ground height for placement; off-landscape points fall back to the origin height (add() drops them)."""
        h = self.ground(x, y)
        return self.g0 if h is None else h

    # ---- bookkeeping ----------------------------------------------------------------------------------------
    def st(self, k, n=1):
        self.stats[k] = self.stats.get(k, 0) + n

    def count(self):
        return sum(len(v) for v in self.instances.values())

    # ---- primitives -----------------------------------------------------------------------------------------
    def add(self, row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0, rot=None):
        """Place a row at pivot (x, y, z); anything off the landscape is dropped and counted."""
        if abs(x) > self.board or abs(y) > self.board or self.ground(x, y) is None:
            self.st("dropped_off_landscape")
            return False
        self.instances.setdefault(row, []).append(tf(x, y, z, rot if rot else quat_yaw(yaw), (sx, sy, sz)))
        return True

    def box(self, kind, cx, cy, z0, h, lx, ly, yaw=0.0):
        """Axis box from z0 up by h: 'concrete' (SM_ConcreteFloor01, top pivot), 'brick' (base pivot) or a cube colour."""
        lx, ly, h = max(lx, 0.1), max(ly, 0.1), max(h, 0.01)
        if kind == "concrete":
            sz = h / 0.30
            self.add(CONCRETE, cx, cy, z0 + 0.29 * sz, lx / 4, ly / 4, sz, yaw)
        elif kind == "brick":
            self.add(BRICK, cx, cy, z0, lx / 0.3, ly / 4, h / 4, yaw)
        else:
            self.add(CUBE[kind], cx, cy, z0 + h / 2, lx, ly, h, yaw)

    def cylinder(self, kind, cx, cy, z0, h, d):
        """Cylinder of diameter d from z0 up by h (centre pivot)."""
        self.add(CYL[kind], cx, cy, z0 + h / 2, d, d, h)

    def plane(self, row, x, y, z_top, lx, ly, yaw=0.0):
        """A 4 x 4 x 0.1 m ground plane scaled to lx x ly with its top at z_top."""
        self.add(row, x, y, z_top - 0.05, max(lx, 0.5) / 4, max(ly, 0.5) / 4, 1.0, yaw)
        self.st("planes")

    def put(self, row, x, y, dz=0.0, s=1.0, yaw=0.0):
        """A prop on the ground at its own (x, y), lifted by dz and the catalogue rest correction; refused inside a
        keep-clear circle (the spawn, fountain basins, stages)."""
        h = self.ground(x, y)
        if h is None or not self.clear_at(x, y):
            self.st("props_refused")
            return False
        return self.add(row, x, y, h + dz + rest(row) * s, s, s, s, yaw)

    # ---- occupancy ------------------------------------------------------------------------------------------
    def cell_of(self, x, y):
        return (int((x - self.gx0) // self.cell), int((y - self.gy0) // self.cell))

    def mark(self, x, y, v):
        i, j = self.cell_of(x, y)
        if 0 <= i < self.gnx and 0 <= j < self.gny:
            self.occ[j * self.gnx + i] = v

    def occ_at(self, x, y):
        """Occupancy of the cell under (x, y); off-grid counts as HARD."""
        i, j = self.cell_of(x, y)
        return self.occ[j * self.gnx + i] if 0 <= i < self.gnx and 0 <= j < self.gny else HARD

    def mark_line(self, pts, w, v):
        """Mark the cells along a polyline of width w."""
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(L / 2))
            yaw = math.atan2(y1 - y0, x1 - x0)
            for k in range(n + 1):
                t = k / n
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                for off in (-w / 2, -w / 4, 0, w / 4, w / 2):
                    self.mark(x - off * math.sin(yaw), y + off * math.cos(yaw), v)

    def mark_rect(self, cx, cy, lx, ly, yaw, v):
        """Mark the cells inside a rotated rectangle."""
        c, s = math.cos(yaw), math.sin(yaw)
        for u in range(-int(lx / 2) - 1, int(lx / 2) + 2, 2):
            for w in range(-int(ly / 2) - 1, int(ly / 2) + 2, 2):
                self.mark(cx + u * c - w * s, cy + u * s + w * c, v)

    def mark_poly(self, pts, v):
        """Mark every cell whose centre is inside a polygon."""
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        for j in range(int((min(ys) - self.gy0) // self.cell), int((max(ys) - self.gy0) // self.cell) + 1):
            for i in range(int((min(xs) - self.gx0) // self.cell), int((max(xs) - self.gx0) // self.cell) + 1):
                if 0 <= i < self.gnx and 0 <= j < self.gny:
                    x, y = self.gx0 + (i + 0.5) * self.cell, self.gy0 + (j + 0.5) * self.cell
                    if point_in_poly(x, y, pts):
                        self.occ[j * self.gnx + i] = v

    def on_road(self, x, y):
        return self.occ_at(x, y) == ROAD

    def clear_at(self, x, y):
        return not any(math.hypot(x - kx, y - ky) < kr for (kx, ky, kr) in self.keep_clear)

    # ---- output ---------------------------------------------------------------------------------------------
    def map_json(
        self, cam=(0.0, 60.0, 55.0, -90.0, -28.0), time_of_day=12.5, north_yaw=0.0, race=None, extra_rows=None
    ):
        rows = dict(self.instances)
        rows.update(extra_rows or {})
        return {
            "S_AssetsTransform": [
                dict(Rname=r, Transform=t, UniqueGroupTag=["None"] * len(t)) for r, t in rows.items()
            ],
            "BaseMapRow": self.base,
            "WeatherIndex": 0,
            "Race": race
            or dict(
                CheckPoints=[], StartTransform=tf(0, 0, 0, dict(X=0, Y=0, Z=0, W=1)), Laps=1, BestTime=-1, Spoints=[]
            ),
            "CamLoc": tf(cam[0], cam[1], cam[2], quat_pitch_yaw(cam[4], cam[3])),
            "CustomWeather": dict(timeOfDay=time_of_day, northyaw=round(north_yaw, 2), Cloud=0.2),
        }

    def write(
        self,
        cam=(0.0, 60.0, 55.0, -90.0, -28.0),
        time_of_day=12.5,
        north_yaw=0.0,
        race=None,
        extra_rows=None,
        thumbnail=None,
        decals=None,
        install=True,
    ):
        """Write maps/<Name>/ (json, info, thumbnail, decals) and copy it into the game's user maps.
        `thumbnail(path)` draws the Thumbnail.jpg; `decals` maps file name -> PNG writer(path)."""
        data = self.map_json(cam, time_of_day, north_yaw, race, extra_rows)
        info = {
            "BaseMapRow": self.base,
            "Name": self.display,
            "CreatorSteamID": STEAM_ID,
            "CreationTimeUnix": int(time.time()),
            "Track": bool(race and race.get("CheckPoints")),
        }
        out = os.path.join(ROOT, "maps", self.name)
        if os.path.isdir(out):
            shutil.rmtree(out)
        os.makedirs(out)
        json.dump(data, open(os.path.join(out, self.name + ".json"), "w"))
        open(os.path.join(out, self.name + ".info"), "w").write(json.dumps(info))
        if thumbnail:
            thumbnail(os.path.join(out, "Thumbnail.jpg"))
        if decals:
            ddir = os.path.join(out, "Decals")
            os.makedirs(ddir)
            for fname, writer in decals.items():
                writer(os.path.join(ddir, fname))
            if install:
                for lib in ("UserDecals", "MapDecals"):
                    ld = os.path.join(os.path.dirname(GAME_USER_MAPS), lib)
                    os.makedirs(ld, exist_ok=True)
                    for fname in decals:
                        shutil.copy(os.path.join(ddir, fname), os.path.join(ld, fname))
        self.data = data
        if install:
            dst = os.path.join(GAME_USER_MAPS, self.name)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(out, dst)
            return dst
        return out

    def check(self, verbose=False, abort_on_spawn=True, spawn=True):
        """Floating / buried / off-landscape objects and take-off clearance, on the last written data."""
        data = getattr(self, "data", None) or self.map_json()
        fl, bu, off = mapcheck.run(data, self.land, verbose=verbose)
        sp = mapcheck.spawn_clear(data, self.land, clearance=1.0, verbose=verbose) if spawn else {}
        nf, nb = sum(map(len, fl.values())), sum(map(len, bu.values()))
        if spawn:
            print(
                f"checks: {nf} floating, {nb} buried, {off} off the landscape, spawn {'CLEAR' if not sp else 'BLOCKED'}"
            )
        if sp and abort_on_spawn:
            raise SystemExit("SPAWN BLOCKED: the take-off point must have 1 m of open air in every direction")
        return fl, bu, off, sp


def point_in_poly(x, y, pts):
    """Even-odd point in polygon."""
    inside = False
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside
