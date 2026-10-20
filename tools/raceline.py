#!/usr/bin/env python3
"""Line-of-flight check for an Uncrashed race: every leg (start -> gate 1 -> ... -> gate N -> start) is sampled as a
straight line at interpolated height and tested against the oriented bounding box of every placed mesh (bounds from
data/catalog.json, scaled, rotated by the instance quaternion) and against the terrain. Reports every blocking object.

usage: raceline.py <map.json> [--clearance 1.5] [--base L_BaseLandscape04]

Inputs
    <map.json>      a map file as the game stores it (`S_AssetsTransform`, `Race.CheckPoints`, `Race.StartTransform`,
                    `Race.Spoints`); a UTF-8 BOM is tolerated.
    --clearance m   radius of the flight tube around each leg, in metres (default 1.5). The build uses 1.5; pass 2.0
                    to see how much margin a track has.
    --base NAME     cooked base level under data/extracted/Uncrashed/Content/MapEditor/BaseLevel/ used for the terrain
                    check (default L_BaseLandscape04, the "Mountain" level). If the extracted level is missing the
                    terrain check is skipped with a notice and only mesh collisions are reported.
    data/catalog.json       bounds (`origin`, `extent`, both cm, mesh-local) for every asset row.
    data/gate_bounds.json   per gate row: `pivot` and `box_t` (the detection box offset from the pivot, cm).

Output: one line per leg ("clear" or "BLOCKED" with the offending rows and where along the leg they are hit, plus how
many samples are below ground + 0.8 m), then a summary line; the exit value of check() is the number of blocked legs.
Also importable: racemap.py and mapcheck.py reuse CAT, GATES, fly_point(), OBB and load_obbs().

Units: the JSON is Unreal centimetres (Z up); everything in this module is converted to metres on load and all
thresholds, clearances and distances below are metres.

Conventions relied on (measured on Workshop tracks, see .claude/skills/uncrashed-maps/SKILL.md):
  - Quaternion yaw = 2 * atan2(Z, W) (stored as Z = sin(yaw/2), W = cos(yaw/2)).
  - A gate's stored yaw is the flight bearing minus 90 deg, so the gate's local +Y is the flight direction. This
    module never needs the bearing itself: it only flies pivot-to-pivot (well, opening-to-opening) in a straight line.
  - A gate's opening centre = pivot translation + the row's BoxDetect offset (`box_t`), scaled by the checkpoint's
    Scale3D and rotated by the gate yaw. Rows with no entry in gate_bounds.json fly through the pivot.
  - The in-game start actor's detection box sits at the StartTransform pivot, so the START point is the pivot.
  - `Spoints[0]` (respawn 0) may sit behind the start line; when it is more than 1 m away it becomes a SPAWN leg.
  - A floor whose top is more than 1 m under the line is the floor the drone flies over, not a blocker.
  - "Upright" means |q.X| < 0.02 and |q.Y| < 0.02, i.e. no pitch or roll beyond about 2.3 deg.
"""

import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = json.load(open(os.path.join(ROOT, 'data/catalog.json')))
GATES = json.load(
    open(os.path.join(ROOT, 'data/gate_bounds.json'))
)  # pivot, detection-box offset (opening centre) per gate row


def fly_point(cp):
    """Centre of a checkpoint's detection box in world space: pivot + the row's BoxDetect offset rotated by the yaw.

    cp: one entry of `Race.CheckPoints` ({Transform, RowName}); Transform in cm, Scale3D optional (defaults to 1).
    Returns (x, y, z) in metres. The `box_t` offset from gate_bounds.json is multiplied per axis by Scale3D (the game
    scales the detection box with the gate), rotated about Z by the gate yaw only (pitch and roll are ignored, gates
    are placed upright) and added to the pivot. Unknown rows use a zero offset, i.e. the pivot itself.
    """
    t, q, sc = (
        cp['Transform']['Translation'],
        cp['Transform']['Rotation'],
        cp['Transform'].get('Scale3D', {'X': 1, 'Y': 1, 'Z': 1}),
    )
    bt = GATES.get(cp['RowName'], {}).get('box_t', [0, 0, 0])
    bt = [bt[0] * sc['X'], bt[1] * sc['Y'], bt[2] * sc['Z']]
    yaw = 2 * math.atan2(q['Z'], q['W'])
    c, s = math.cos(yaw), math.sin(yaw)
    # 2-D rotation of the (scaled) offset by the yaw, then cm -> m; Z is unaffected by yaw.
    return (
        t['X'] / 100 + (bt[0] * c - bt[1] * s) / 100,
        t['Y'] / 100 + (bt[0] * s + bt[1] * c) / 100,
        t['Z'] / 100 + bt[2] / 100,
    )


# Rows whose mesh or blueprint path contains one of these are never obstacles: ground planes are flown over, water is
# flown through (the invisible lake gate sits 2 m over it) and decals are flat images on other surfaces.
IGNORE_SUBSTR = ('BaseGround', 'meWater', 'Decal')


def q_to_m(q):
    """Rotation matrix (3 row tuples, row-major) of a unit quaternion given as a {X, Y, Z, W} dict.

    R maps mesh-local vectors to world vectors; R^T (used in OBB.hit) maps world back to local. The quaternion is
    assumed normalised, as the game stores it.
    """
    x, y, z, w = q['X'], q['Y'], q['Z'], q['W']
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def yaw_of(q):
    """Yaw in degrees of a {X, Y, Z, W} quaternion (2 * atan2(Z, W)); exact for yaw-only rotations."""
    return math.degrees(2 * math.atan2(q['Z'], q['W']))


class OBB:
    """Oriented bounding box of one placed instance (metres), from the catalog bounds and the instance transform.

    Attributes:
        row   asset row name (`Rname`).
        T     world translation (pivot) in m.
        R     rotation matrix from q_to_m().
        S     per-axis Scale3D (may be non-uniform or negative for mirrored instances).
        o, e  catalog bounds origin and half-extent in mesh-local metres, unscaled (the scale is applied at test time).
        rad   bounding-sphere radius about the pivot: the scaled half-diagonal plus the scaled distance from the pivot
              to the box centre, so it covers the box whatever the rotation. Used only as a cheap reject in hit().
        cx, cy  the pivot's X/Y, for the radius pre-check.
        top   world height of the highest point: exact `T.z + (o.z + e.z) * S.z` for upright instances, otherwise the
              conservative `T.z + rad`.
    """

    __slots__ = ('row', 'T', 'R', 'S', 'o', 'e', 'rad', 'cx', 'cy', 'top')

    def __init__(self, row, t, info):
        """row: asset row name; t: one Transform dict (cm, quaternion, Scale3D); info: the row's catalog entry."""
        self.row = row
        tr, sc = t['Translation'], t['Scale3D']
        self.T = (tr['X'] / 100, tr['Y'] / 100, tr['Z'] / 100)
        self.S = (sc['X'], sc['Y'], sc['Z'])
        self.R = q_to_m(t['Rotation'])
        b = info['bounds']
        self.o = [v / 100 for v in b['origin']]
        self.e = [v / 100 for v in b['extent']]
        # Sphere radius = |scaled extent| + |scaled origin offset|: an upper bound on how far any corner can be from
        # the pivot, independent of rotation.
        self.rad = math.sqrt(sum((self.e[i] * self.S[i]) ** 2 for i in range(3))) + math.sqrt(
            sum((self.o[i] * self.S[i]) ** 2 for i in range(3))
        )
        self.cx, self.cy = self.T[0], self.T[1]
        self.top = self.T[2] + self.rad  # conservative; refined below for upright boxes
        q = t['Rotation']
        # Upright (no pitch/roll beyond ~2.3 deg): the local Z axis is world Z, so the top face height is exact.
        if abs(q['X']) < 0.02 and abs(q['Y']) < 0.02:
            self.top = self.T[2] + (self.o[2] + self.e[2]) * self.S[2]

    def hit(self, p, clearance):
        """True when world point p (m) is inside the box inflated by `clearance` metres.

        Fast path: if the horizontal distance from the pivot exceeds rad + clearance the point cannot touch the box.
        Otherwise p is moved into mesh-local space (R^T applied to p - T, then divided per axis by the scale) and
        compared with the axis-aligned local box [o - e, o + e]. The clearance is expressed in local units by dividing
        it by |S_i| for each axis, so a non-uniform scale gives the right world distance on every face; the test is a
        box inflation, not a rounded tube, so it is slightly conservative at corners and edges. `or 1e-9` guards a zero
        scale; a negative scale (mirrored instance) just flips that local axis, which the signed division handles.
        """
        if math.hypot(p[0] - self.cx, p[1] - self.cy) > self.rad + clearance:
            return False
        d = [p[i] - self.T[i] for i in range(3)]
        for i in range(3):
            li = sum(self.R[k][i] * d[k] for k in range(3)) / (self.S[i] or 1e-9)  # R^T d, into mesh local
            if abs(li - self.o[i]) > self.e[i] + clearance / abs(self.S[i] or 1e-9):
                return False
        return True


def load_obbs(data):
    """One OBB per placed instance of every row that has catalog bounds and is not in IGNORE_SUBSTR.

    data: the parsed map JSON. Rows missing from the catalog or without bounds (decals) are skipped silently.
    Returns a flat list; for FPVPark that is tens of thousands of boxes, so callers keep and reuse it.
    """
    obbs = []
    for a in data['S_AssetsTransform']:
        row = a['Rname']
        info = CAT.get(row)
        if (
            not info
            or not info.get('bounds')
            or any(s in (info.get('mesh') or '') + (info.get('blueprint') or '') for s in IGNORE_SUBSTR)
        ):
            continue
        for t in a['Transform']:
            obbs.append(OBB(row, t, info))
    return obbs


def check(data, clearance=1.5, land=None, step=0.5, verbose=True, obbs=None):
    """Test every race leg as a straight segment against all OBBs and (optionally) the terrain.

    data       parsed map JSON with a `Race` block.
    clearance  flight tube radius in m around the line.
    land       a terrain sampler with `height_cm(x_cm, y_cm)` (tools/landscape.py's Landscape) or None to skip the
               terrain check. Gotcha: `height_cm` returns None off the landscape, which raises here, so every leg must
               stay over the landscape (mapcheck's off_map count catches that first).
    step       sample spacing along each leg in m (at least two segments per leg).
    verbose    print one line per leg plus the blocking rows.
    obbs       a precomputed load_obbs() list to avoid rebuilding it for repeated calls.
    Returns the number of blocked legs (0 = all clear).

    Leg list: [SPAWN,] START, G1..GN, START. SPAWN is only added when respawn point 0 (`Spoints[0]`) is more than
    1 m from the start, because the drone then has to fly from there to the start gate first. The closing leg goes
    back to START (not SPAWN), so laps are start -> gates -> start.
    """
    obbs = obbs if obbs is not None else load_obbs(data)
    race = data['Race']
    st = race['StartTransform']['Translation']
    pts = [('START', (st['X'] / 100, st['Y'] / 100, st['Z'] / 100))]
    sp0 = race.get('Spoints', [{}])[0].get('Translation')
    # 100 cm: respawn 0 that merely sits on the start line is not a separate leg.
    if sp0 and math.hypot(sp0['X'] - st['X'], sp0['Y'] - st['Y']) > 100:
        pts.insert(0, ('SPAWN', (sp0['X'] / 100, sp0['Y'] / 100, sp0['Z'] / 100)))
    for i, cp in enumerate(race['CheckPoints']):
        pts.append((f'G{i + 1}:{cp["RowName"]}', fly_point(cp)))
    pts.append(pts[1] if pts[0][0] == 'SPAWN' else pts[0])
    bad = 0
    for (na, a), (nb, b) in zip(pts, pts[1:]):
        L = math.dist(a, b)
        n = max(2, int(L / step))
        hits = {}
        low = 0
        for k in range(n + 1):
            u = k / n
            p = tuple(a[i] + (b[i] - a[i]) * u for i in range(3))
            # The first and last 5 % of a leg lie inside the gate frames themselves (and the pilot stand at the
            # start), which would otherwise count as obstacles.
            if 0.05 < u < 0.95:  # the gate's own neighbourhood is exempt
                for o in obbs:
                    if o.top < p[2] - 1.0:
                        continue  # a floor more than 1 m under the line is the floor, not a blocker
                    if o.hit(p, clearance):
                        hits.setdefault(o.row, []).append(round(u * L, 1))
            # Terrain: the line must stay 0.8 m above the ground sample (empirical margin for the undulating floor).
            if land is not None and p[2] < land.height_cm(p[0] * 100, p[1] * 100) / 100 + 0.8:
                low += 1
        if hits or low:
            bad += 1
            if verbose:
                print(f'LEG {na} -> {nb}  ({L:.0f} m)  BLOCKED')
                # Rows ordered by where along the leg they are first hit; the name is the mesh/blueprint basename.
                for row, ds in sorted(hits.items(), key=lambda kv: kv[1][0]):
                    print(
                        f'    {row:<12} {(CAT[row]["mesh"] or CAT[row].get("blueprint") or "").split("/")[-1].split(".")[0]:<32} at {ds[0]:.0f}..{ds[-1]:.0f} m along the leg'
                    )
                if low:
                    print(f'    terrain: {low} samples below ground + 0.8 m')
        elif verbose:
            print(f'leg {na} -> {nb}  ({L:.0f} m)  clear')
    return bad


if __name__ == '__main__':
    # Positional arguments are everything not starting with '--'; only the first (the map path) is used, so the value
    # after --clearance/--base harmlessly lands in args[1].
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    clearance = float(sys.argv[sys.argv.index('--clearance') + 1]) if '--clearance' in sys.argv else 1.5
    base = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else 'L_BaseLandscape04'
    data = json.load(open(args[0], encoding='utf-8-sig'))
    land = None
    # The terrain sampler needs the extracted base level (not in the repo); without it only meshes are checked.
    try:
        from landscape import Landscape

        land = Landscape(os.path.join(ROOT, 'data/extracted/Uncrashed/Content/MapEditor/BaseLevel', base))
    except Exception as e:
        print('no terrain check:', e)
    bad = check(data, clearance, land)
    print(f'\n{bad} blocked legs' if bad else '\nall legs clear')
