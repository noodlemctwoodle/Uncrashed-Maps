#!/usr/bin/env python3
"""Showroom: every part demo from tools/prefabs.py on a grid in one small map, for a single in-game check.

    python3 tools/showroom.py            # all demos
    python3 tools/showroom.py road       # only demos whose name contains the word

The map goes to maps/Showroom and into the game's MapEditor/User folder through the same Scene class the real
maps use, so what you see here is what a map gets. The spawn is at the origin facing -Y; the demos stand in rows
in front of it in DEMOS order, each printed with a `tools/setcam.py Showroom ...` line to point the editor camera.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefabs
from scene import Scene

PITCH, ROW_GAP, PER_ROW = 110.0, 120.0, 5  # grid pitch (m), gap between rows, demos per row


def build(names, flat_z=None):
    """Lay the named demos on the grid; returns the scene and [(name, x, y)]."""
    sc = Scene("Showroom", "Prefab Showroom", flat_z=flat_z, seed=11)
    spots = []
    for i, name in enumerate(names):
        fn, radius = prefabs.DEMOS[name]
        col, row = i % PER_ROW, i // PER_ROW
        x = (col - (PER_ROW - 1) / 2) * PITCH
        y = -90.0 - row * ROW_GAP
        before = sc.count()
        fn(sc, x, y, 0.0)
        spots.append((name, x, y, sc.count() - before))
    return sc, spots


if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    names = [n for n in prefabs.DEMOS if not want or any(w in n for w in want)]
    sc, spots = build(names)
    print(f"{len(spots)} demos:")
    for name, x, y, n in spots:
        print(
            f"  {name:18s} at ({x:6.0f}, {y:6.0f})  {n:5d} objects   camera: tools/setcam.py Showroom {x:.0f} {y + 48:.0f} 26 -90 -26"
        )
    dst = sc.write(cam=(0.0, 60.0, sc.g0 + 55.0, -90.0, -28.0))
    print(f"Showroom: {sc.count()} objects, {len(sc.instances)} rows -> {dst}")
    sc.check()
    print(sc.stats)
