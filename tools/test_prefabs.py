#!/usr/bin/env python3
"""Geometry tests for every part demo, plus a golden hash so any change to a part's output is noticed.

    python3 tools/test_prefabs.py            # run all checks
    python3 tools/test_prefabs.py --update   # accept the current output as the new golden hashes

Each demo is built alone on a flat scene (no landscape needed, so this runs anywhere) and checked by geometry:
nothing floats or is buried, vehicles stand inside asphalt, walkers never stand on a carriageway, lamps and
benches stay off the carriageway, stair landings meet bridge decks, water stays inside fountain basins, and
every object stays inside the demo's declared footprint. The checks are the written form of the bugs that were
seen in the game; a part that passes them and the showroom is ready for a map.
"""

import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefabs
import showroom
from mapkit import CAT, GROUND, PARAPET, STAIR_A
from scene import Scene

GOLDEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "prefab_golden.json")
GROUND_ROWS = set(GROUND.values()) | {prefabs.WATER_ROW}


def yaw_of(t):
    q = t["Rotation"]
    return math.atan2(2 * (q["W"] * q["Z"] + q["X"] * q["Y"]), 1 - 2 * (q["Y"] ** 2 + q["Z"] ** 2))


def footprint(row, t):
    """(cx, cy, ex, ey, yaw, z_bottom, z_top) of an instance's bounding box in metres."""
    b = CAT.get(row, {}).get("bounds")
    tr, s = t["Translation"], t["Scale3D"]
    ya = yaw_of(t)
    if not b:
        return tr["X"] / 100, tr["Y"] / 100, 0.5, 0.5, ya, tr["Z"] / 100, tr["Z"] / 100 + 1
    ox, oy, oz = b["origin"][0] / 100 * s["X"], b["origin"][1] / 100 * s["Y"], b["origin"][2] / 100 * s["Z"]
    ex, ey, ez = b["extent"][0] / 100 * s["X"], b["extent"][1] / 100 * s["Y"], b["extent"][2] / 100 * s["Z"]
    c, sn = math.cos(ya), math.sin(ya)
    cx, cy = tr["X"] / 100 + ox * c - oy * sn, tr["Y"] / 100 + ox * sn + oy * c
    return cx, cy, ex, ey, ya, tr["Z"] / 100 + oz - ez, tr["Z"] / 100 + oz + ez


def corners(fp):
    cx, cy, ex, ey, ya = fp[:5]
    c, s = math.cos(ya), math.sin(ya)
    return [(cx + u * c - v * s, cy + u * s + v * c) for u in (-ex, ex) for v in (-ey, ey)]


def build(name):
    sc = Scene("Test", flat_z=0.0, seed=11)
    fn, radius = prefabs.DEMOS[name]
    fn(sc, 0.0, 0.0, 0.3)  # a slight yaw so axis-aligned mistakes show
    return sc, radius


def check(name):
    """Return a list of failure strings for one demo."""
    sc, radius = build(name)
    fails = []
    inst = sc.instances

    def road_dist(x, y):
        """Signed distance inside the nearest carriageway edge (positive = on the asphalt)."""
        best = -1e9
        for pts, w in sc.roads:
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                dx, dy = x1 - x0, y1 - y0
                d2 = dx * dx + dy * dy or 1e-9
                t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / d2))
                best = max(best, w / 2 - math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)))
        return best

    road_cells = lambda x, y: road_dist(x, y) > -0.05  # noqa: E731
    # footprint
    for row, ts in inst.items():
        for t in ts:
            fp = footprint(row, t)
            if math.hypot(fp[0], fp[1]) > radius + max(fp[2], fp[3]):
                fails.append(f"{row} at ({fp[0]:.1f},{fp[1]:.1f}) outside the {radius} m footprint")
                break
    # vehicles: every corner on a road cell
    for row in prefabs.CARS:
        for t in inst.get(row, []):
            fp = footprint(row, t)
            if not all(road_cells(x, y) for x, y in corners(fp)):
                fails.append(f"vehicle {row} at ({fp[0]:.1f},{fp[1]:.1f}) not entirely on the carriageway")
            if fp[5] < -0.15 or fp[5] > 0.35:
                fails.append(f"vehicle {row} bottom at {fp[5]:.2f} m (not on the ground)")
    # walkers, lamps, benches, bins: never on a carriageway
    for row in prefabs.PEOPLE + [prefabs.LAMP_TALL, prefabs.LAMP_SHORT, prefabs.TRASH, "NewRow_204"]:
        for t in inst.get(row, []):
            x, y = t["Translation"]["X"] / 100, t["Translation"]["Y"] / 100
            if road_dist(x, y) > 0.3:
                fails.append(f"{row} standing on the carriageway at ({x:.1f},{y:.1f})")
                break
    # stairs: the top landing must meet a deck or terrace edge (something solid within 0.6 m at that height)
    tops = []
    for row, ts in inst.items():
        if row in (STAIR_A, PARAPET) or row in GROUND_ROWS or row in prefabs.PEOPLE:
            continue
        for t in ts:
            fp = footprint(row, t)
            if fp[6] > 2.0:
                tops.append(fp)
    for t in inst.get(STAIR_A, []) if name != "probe" else []:
        fp = footprint(STAIR_A, t)
        ya = yaw_of(t)
        top = (fp[0] - math.sin(ya) * fp[3], fp[1] + math.cos(ya) * fp[3])  # local +Y end (the landing)
        if not any(
            abs(o[6] - fp[6]) < 0.9
            and min(math.hypot(top[0] - cx, top[1] - cy) for cx, cy in corners(o)) < max(o[2], o[3]) + 0.8
            for o in tops
        ):
            fails.append(f"stair landing at ({top[0]:.1f},{top[1]:.1f}, {fp[6]:.1f} m) meets nothing")
    # fountain: water tiles inside the ring
    if name == "fountain":
        for t in inst.get(prefabs.WATER_ROW, []):
            x, y, s = t["Translation"]["X"] / 100, t["Translation"]["Y"] / 100, t["Scale3D"]["X"] * 4
            if math.hypot(x, y) + s * 0.71 > 8.0 - 0.4:
                fails.append(f"water tile at ({x:.1f},{y:.1f}) pokes through the basin ring")
                break
    # road: sidewalks exist on both sides and cars on both headings
    if name == "road":
        heads = {round(math.degrees(yaw_of(t)) % 360) for row in prefabs.CARS for t in inst.get(row, [])}
        if not any(abs(((h - 17) + 180) % 360 - 180) < 95 for h in heads) or not any(
            abs(((h - 197) + 180) % 360 - 180) < 95 for h in heads
        ):
            fails.append(f"cars only head one way: {sorted(heads)}")
        if len(inst.get("NewRow_197", [])) < 2:
            fails.append("fewer than two sidewalk pieces")
    # the generic floater / buried check on the flat ground
    sc.data = sc.map_json()
    fl, bu, off, sp = sc.check(abort_on_spawn=False, spawn=False)
    for r, v in fl.items():
        fails.append(f"floating {r} x{len(v)}")
    for r, v in bu.items():
        fails.append(f"buried {r} x{len(v)}")
    return fails, hashlib.sha1(json.dumps(inst, sort_keys=True).encode()).hexdigest()[:12]


if __name__ == "__main__":
    update = "--update" in sys.argv
    golden = json.load(open(GOLDEN)) if os.path.exists(GOLDEN) else {}
    bad = 0
    for name in prefabs.DEMOS:
        fails, h = check(name)
        changed = golden.get(name) not in (None, h)
        status = "FAIL" if fails else ("CHANGED" if changed and not update else "ok")
        bad += bool(fails) or (changed and not update)
        print(f"{status:8s} {name:18s} {h}")
        for f in fails[:6]:
            print(f"           - {f}")
        golden[name] = h if (update or name not in golden) else golden[name]
    if update:
        json.dump(golden, open(GOLDEN, "w"), indent=1, sort_keys=True)
        print("golden hashes updated")
    sys.exit(1 if bad else 0)
