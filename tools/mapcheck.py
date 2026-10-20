#!/usr/bin/env python3
"""Physical sanity checks for a generated Uncrashed map, using the mesh bounds in data/catalog.json:
  floaters  - a prop whose lowest point is more than 0.3 m above the terrain with nothing under it
  buried    - a prop whose top is below the terrain
  off_map   - an instance outside the landscape
Rotated (pitched/rolled) instances are skipped. usage: mapcheck.py <map.json> [--base L_BaseLandscape04]

Flags
    --base NAME    cooked base level under data/extracted/Uncrashed/Content/MapEditor/BaseLevel/ whose heightmap is
                   decoded by tools/landscape.py (default L_BaseLandscape04, the "Mountain" level). Needs the
                   extracted game files.
    --flat Z_CM    instead of a real landscape, use a flat ground at Z_CM centimetres bounded by the 6048 m Empty
                   board (BaseBoard, ground at Z 0, so `--flat 0`). Takes precedence over --base.

Output: one `FLOATING`/`BURIED` line per offending row (count, mesh name, up to four example (x, y, gap) tuples in
metres) sorted by count, then a `N floating, N buried, N off the landscape` summary; run() returns the same data so
the build scripts can fail on it.

Units: the map JSON and `height_cm` are Unreal centimetres; everything inside run() is metres.

Conventions relied on
  - "Upright" = |q.X| < 0.02 and |q.Y| < 0.02 (no pitch/roll beyond about 2.3 deg). Only upright instances are
    checked and only upright instances count as supports: the bottom and top of a box are taken from its local Z
    bounds (`origin.z +/- extent.z`, scaled), which is only its world bottom/top when local Z is world Z. A pitched
    or rolled mesh would need all eight rotated corners, so it is skipped rather than mis-measured.
  - Support heuristic: a prop that hovers more than 0.3 m over the terrain is still fine if it rests on something.
    "Rests on" means some upright box's top face is within 0.45 m of the prop's bottom and the two are horizontally
    within (support half-extent + half the prop's half-extent) of each other, searched over the 3x3 block of 10 m
    cells around the prop. That accepts props on floors, tables, roofs and container stacks and tolerates the
    catalog's rest-height corrections (trees and houses sink a little, boxcars hover 0.68 m).
  - Buried = top more than 0.2 m under the terrain sample at the pivot; the 0.3 m / 0.2 m / 0.45 m margins are
    empirical and absorb the valley floor's undulation (the sampler is accurate to about 0.1 m).
  - `height_cm` returns None off the landscape: such instances are counted as off_map and never checked further.
"""

import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raceline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def upright(t):
    """True when a Transform's rotation is yaw-only: |q.X| and |q.Y| below 0.02 (about 2.3 deg of pitch/roll)."""
    q = t['Rotation']
    return abs(q['X']) < 0.02 and abs(q['Y']) < 0.02


def run(data, land, struct_rows=(), verbose=True):
    """Find floating, buried and off-landscape instances.

    data         parsed map JSON (`S_AssetsTransform`).
    land         terrain sampler with `height_cm(x_cm, y_cm)` -> cm or None (Landscape, or the Flat stub below).
    struct_rows  rows that are structure, not props (cubes, floors, walls...): they are never reported as floating or
                 buried (their placement is the builder's design) but they still act as supports for everything else.
    verbose      print the report lines.
    Returns (floaters, buried, off): two dicts row -> [(x, y, gap_m), ...] with x, y rounded to whole metres and the
    gap rounded to 0.1 m, and the count of instances with no terrain under them.

    Gotchas: everything is measured at the pivot's (x, y), so a wide slab over a slope is judged by its centre only;
    supports are indexed by their centre cell, so a support wider than about 10 m half-extent can be missed by a prop
    near its edge; rotated instances are skipped entirely (see the module docstring).
    """
    obbs = [o for o in raceline.load_obbs(data)]
    # supports: top faces (z) of every upright box, indexed by 10 m cell
    # supports: every upright box, indexed into every 10 m cell its footprint covers (so a long deck or a wide
    # building supports props anywhere on it); stored as a rotated rectangle for an exact containment test
    tops = {}
    recs = []
    for a in data['S_AssetsTransform']:
        info = raceline.CAT.get(a['Rname'])
        if not info or not info.get('bounds'):
            continue
        for t in a['Transform']:
            if not upright(t):
                continue
            o = raceline.OBB(a['Rname'], t, info)
            bot = o.T[2] + (o.o[2] - o.e[2]) * o.S[2]
            top = o.T[2] + (o.o[2] + o.e[2]) * o.S[2]
            hx, hy = o.e[0] * abs(o.S[0]), o.e[1] * abs(o.S[1])
            ox, oy = o.o[0] * o.S[0], o.o[1] * o.S[1]
            yaw = raceline.yaw_of(t['Rotation']) * math.pi / 180
            cxr = o.T[0] + ox * math.cos(yaw) - oy * math.sin(yaw)
            cyr = o.T[1] + ox * math.sin(yaw) + oy * math.cos(yaw)
            rx = max(hx, hy)
            recs.append((o.row, o.T[0], o.T[1], bot, top, rx))
            sup = (cxr, cyr, hx, hy, yaw, top, bot)
            for gx in range(int((cxr - rx) // 10), int((cxr + rx) // 10) + 1):
                for gy in range(int((cyr - rx) // 10), int((cyr + rx) // 10) + 1):
                    tops.setdefault((gx, gy), []).append(sup)

    def supported(x, y, bot, rx):
        """True when some support's top is within 0.45 m under the prop's bottom (or the prop is embedded in it) and
        the prop's centre lies inside that support's rotated footprint grown by half the prop's size."""
        for sx, sy, hx, hy, yaw, stop, sbot in tops.get((int(x // 10), int(y // 10)), []):
            if not (abs(stop - bot) < 0.45 or (sbot - 0.05 < bot < stop)):
                continue
            c, s_ = math.cos(yaw), math.sin(yaw)
            u = (x - sx) * c + (y - sy) * s_
            v = -(x - sx) * s_ + (y - sy) * c
            if abs(u) <= hx + rx * 0.6 and abs(v) <= hy + rx * 0.6:
                return True
        return False

    floaters = {}
    buried = {}
    off = 0
    for row, x, y, bot, top, rx in recs:
        if row in struct_rows:
            continue
        h = land.height_cm(x * 100, y * 100)
        if h is None:
            off += 1
            continue
        g = h / 100
        if bot - g > 0.3:
            if not supported(x, y, bot, rx):
                floaters.setdefault(row, []).append((round(x), round(y), round(bot - g, 1)))
        if top < g - 0.2:
            buried.setdefault(row, []).append((round(x), round(y), round(g - top, 1)))
    if verbose:

        def nm(r):
            """Mesh or blueprint basename of a row, for the report."""
            return (raceline.CAT[r]['mesh'] or raceline.CAT[r].get('blueprint') or '').split('/')[-1].split('.')[0]

        for r, v in sorted(floaters.items(), key=lambda kv: -len(kv[1])):
            print(f'FLOATING {r:<12}{len(v):>5}  {nm(r):<30} e.g. {v[:4]}')
        for r, v in sorted(buried.items(), key=lambda kv: -len(kv[1])):
            print(f'BURIED   {r:<12}{len(v):>5}  {nm(r):<30} e.g. {v[:4]}')
        print(
            f'{sum(map(len, floaters.values()))} floating, {sum(map(len, buried.values()))} buried, {off} off the landscape'
        )
    return floaters, buried, off


def spawn_clear(data, land, clearance=1.0, x=0.0, y=0.0, verbose=True):
    """The drone needs open air to take off: nothing but the ground surface may lie within `clearance` metres of
    the spawn capsule in any direction. The capsule is sampled from 0.2 m to 2.2 m above the ground at (x, y)
    (freestyle maps spawn at the world origin; a race map's start comes from its StartTransform). Ground planes and
    water are exempt (the drone sits on them). Returns the offending rows."""
    sx, sy = x, y
    if data.get('Race', {}).get('CheckPoints'):
        st = data['Race']['StartTransform']['Translation']
        sx, sy = st['X'] / 100, st['Y'] / 100
    h = land.height_cm(sx * 100, sy * 100)
    g = (h or 0) / 100
    hits = {}
    for o in raceline.load_obbs(data):
        if math.hypot(o.cx - sx, o.cy - sy) > o.rad + clearance + 0.5:
            continue
        for k in range(11):
            p = (sx, sy, g + 0.2 + 0.2 * k)
            if o.hit(p, clearance):
                hits.setdefault(o.row, []).append((round(o.cx - sx, 1), round(o.cy - sy, 1), round(o.T[2] - g, 1)))
                break
    if verbose:
        for r, v in hits.items():
            nm = (raceline.CAT[r]['mesh'] or raceline.CAT[r].get('blueprint') or '').split('/')[-1].split('.')[0]
            print(f'SPAWN BLOCKED by {r} {nm}: {len(v)} within {clearance} m, e.g. {v[:3]} (dx, dy, dz from the spawn)')
        if not hits:
            print(f'spawn clear: nothing within {clearance} m of the take-off point ({sx:.1f}, {sy:.1f})')
    return hits


if __name__ == '__main__':
    if '--flat' in sys.argv:  # the Empty board: flat landscape at the given height (cm)

        class Flat:
            """Stand-in for Landscape: constant height inside the 6048 m BaseBoard (|x|, |y| < 302400 cm), else None."""

            def __init__(self, z):
                """z: ground height in cm."""
                self.z = z

            def height_cm(self, x, y):
                """Ground height (cm) at world (x, y) cm, or None beyond the board's 3024 m half-size."""
                return self.z if abs(x) < 302400 and abs(y) < 302400 else None

        land = Flat(float(sys.argv[sys.argv.index('--flat') + 1]))
    else:
        from landscape import Landscape

        base = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else 'L_BaseLandscape04'
        land = Landscape(os.path.join(ROOT, 'data/extracted/Uncrashed/Content/MapEditor/BaseLevel', base))
    _d = json.load(open(sys.argv[1], encoding='utf-8-sig'))
    run(_d, land)
    spawn_clear(_d, land)
