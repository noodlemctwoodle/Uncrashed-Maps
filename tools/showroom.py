#!/usr/bin/env python3
"""Showroom: every prefab from tools/prefabs.py on a grid in one small map, for a single in-game check.

    python3 tools/showroom.py            # all prefabs
    python3 tools/showroom.py vehicle    # only prefabs whose name contains the word

The map is written to maps/Showroom and copied into the game's MapEditor/User folder. The spawn is at the origin
facing -Y; the prefabs stand in rows in front of it in the order PREFABS lists them (printed with their grid
positions, which `tools/setcam.py Showroom x y z yaw pitch` can point the editor camera at).
"""

import json
import math
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapcheck
import prefabs
from landscape import Landscape
from mapkit import BRICK, CONCRETE, CUBE, MapKit, rest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEAM_ID = os.environ.get("UNCRASHED_STEAM_ID", "76561197969360950")
GAME_USER_MAPS = os.path.expanduser(f"~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User")
NAME, BASE = "Showroom", "BaseLandscape02"
LAND = Landscape(os.path.join(ROOT, "data", "extracted/Uncrashed/Content/MapEditor/BaseLevel/L_" + BASE))
PITCH, ROW_GAP, PER_ROW = 90.0, 110.0, 6  # grid pitch (m), gap between rows, prefabs per row
instances, stats = {}, {}
rng = random.Random(11)


def gz(x, y):
    """Ground-top height (m); the origin height off the landscape."""
    h = LAND.height_cm(x * 100, y * 100)
    return (LAND.height_cm(0, 0) if h is None else h) / 100.0 + 0.02


def quat_yaw(yaw):
    return dict(X=0.0, Y=0.0, Z=math.sin(yaw / 2), W=math.cos(yaw / 2))


def quat_pitch_yaw(pitch_deg, yaw_deg):
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2
    return dict(
        X=math.sin(P) * math.sin(Y),
        Y=-math.sin(P) * math.cos(Y),
        Z=math.cos(P) * math.sin(Y),
        W=math.cos(P) * math.cos(Y),
    )


def tf(x, y, z, rot, s=(1, 1, 1)):
    return dict(
        Rotation=rot,
        Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)),
        Scale3D=dict(X=round(s[0], 4), Y=round(s[1], 4), Z=round(s[2], 4)),
    )


def add(row, x, y, z, sx=1.0, sy=1.0, sz=1.0, yaw=0.0, rot=None):
    instances.setdefault(row, []).append(tf(x, y, z, rot if rot else quat_yaw(yaw), (sx, sy, sz)))


def box(kind, cx, cy, z0, h, lx, ly, yaw=0.0):
    """Same massing helper as the map builders: concrete (top pivot), brick (base pivot) or a coloured cube."""
    lx, ly, h = max(lx, 0.1), max(ly, 0.1), max(h, 0.01)
    if kind == "concrete":
        sz = h / 0.30
        add(CONCRETE, cx, cy, z0 + 0.29 * sz, lx / 4, ly / 4, sz, yaw)
    elif kind == "brick":
        add(BRICK, cx, cy, z0, lx / 0.3, ly / 4, h / 4, yaw)
    else:
        add(CUBE[kind], cx, cy, z0 + h / 2, lx, ly, h, yaw)


def plane(row, x, y, z_top, lx, ly, yaw=0.0):
    add(row, x, y, z_top - 0.05, max(lx, 0.5) / 4, max(ly, 0.5) / 4, 1.0, yaw)


kit = MapKit(add, box, plane, ground_z=gz, rng=rng, stats=stats)
want = [a for a in sys.argv[1:] if not a.startswith("-")]
names = [n for n in prefabs.PREFABS if not want or any(w in n for w in want)]
print(f"{len(names)} prefabs:")
for i, name in enumerate(names):
    fn, radius = prefabs.PREFABS[name]
    col, row = i % PER_ROW, i // PER_ROW
    x = (col - (PER_ROW - 1) / 2) * PITCH
    y = -80.0 - row * ROW_GAP
    before = sum(len(v) for v in instances.values())
    fn(kit, x, y, 0.0)
    n = sum(len(v) for v in instances.values()) - before
    print(
        f"  {name:26s} at ({x:6.0f}, {y:6.0f})  {n:5d} objects   camera: tools/setcam.py Showroom {x:.0f} {y + 45:.0f} 25 -90 -25"
    )

cam = (0.0, 60.0, gz(0, 0) + 55.0)
map_json = {
    "S_AssetsTransform": [dict(Rname=r, Transform=t, UniqueGroupTag=["None"] * len(t)) for r, t in instances.items()],
    "BaseMapRow": BASE,
    "WeatherIndex": 0,
    "Race": dict(CheckPoints=[], StartTransform=tf(0, 0, 0, dict(X=0, Y=0, Z=0, W=1)), Laps=1, BestTime=-1, Spoints=[]),
    "CamLoc": tf(*cam, quat_pitch_yaw(-28.0, -90.0)),
    "CustomWeather": dict(timeOfDay=12.5, northyaw=0.0, Cloud=0.2),
}
info = {
    "BaseMapRow": BASE,
    "Name": "Prefab Showroom",
    "CreatorSteamID": STEAM_ID,
    "CreationTimeUnix": int(time.time()),
    "Track": False,
}
out = os.path.join(ROOT, "maps", NAME)
if os.path.isdir(out):
    shutil.rmtree(out)
os.makedirs(out)
json.dump(map_json, open(os.path.join(out, NAME + ".json"), "w"))
open(os.path.join(out, NAME + ".info"), "w").write(json.dumps(info))
dst = os.path.join(GAME_USER_MAPS, NAME)
if os.path.isdir(dst):
    shutil.rmtree(dst)
shutil.copytree(out, dst)
fl, bu, off = mapcheck.run(map_json, LAND, verbose=False)
sp = mapcheck.spawn_clear(map_json, LAND, clearance=1.0)
n = sum(len(v) for v in instances.values())
print(f"{NAME}: {n} objects, {len(instances)} rows -> {dst}")
print(
    f"checks: {sum(map(len, fl.values()))} floating, {sum(map(len, bu.values()))} buried, spawn {'CLEAR' if not sp else 'BLOCKED'}"
)
print(stats)
