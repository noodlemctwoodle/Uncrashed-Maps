#!/usr/bin/env python3
"""Line-of-flight check for an Uncrashed race: every leg (start -> gate 1 -> ... -> gate N -> start) is sampled as a
straight line at interpolated height and tested against the oriented bounding box of every placed mesh (bounds from
data/catalog.json, scaled, rotated by the instance quaternion) and against the terrain. Reports every blocking object.

usage: raceline.py <map.json> [--clearance 1.5] [--base L_BaseLandscape04]
"""

import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = json.load(open(os.path.join(ROOT, 'data/catalog.json')))
GATES = json.load(
    open(os.path.join(ROOT, 'data/gate_bounds.json'))
)  # pivot, detection-box offset (opening centre) per gate row


def fly_point(cp):
    """Centre of a checkpoint's detection box in world space: translation + the row's BoxDetect offset rotated by the gate yaw."""
    t, q, sc = (
        cp['Transform']['Translation'],
        cp['Transform']['Rotation'],
        cp['Transform'].get('Scale3D', {'X': 1, 'Y': 1, 'Z': 1}),
    )
    bt = GATES.get(cp['RowName'], {}).get('box_t', [0, 0, 0])
    bt = [bt[0] * sc['X'], bt[1] * sc['Y'], bt[2] * sc['Z']]
    yaw = 2 * math.atan2(q['Z'], q['W'])
    c, s = math.cos(yaw), math.sin(yaw)
    return (
        t['X'] / 100 + (bt[0] * c - bt[1] * s) / 100,
        t['Y'] / 100 + (bt[0] * s + bt[1] * c) / 100,
        t['Z'] / 100 + bt[2] / 100,
    )


IGNORE_SUBSTR = ('BaseGround', 'meWater', 'Decal')


def q_to_m(q):
    x, y, z, w = q['X'], q['Y'], q['Z'], q['W']
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def yaw_of(q):
    return math.degrees(2 * math.atan2(q['Z'], q['W']))


class OBB:
    __slots__ = ('row', 'T', 'R', 'S', 'o', 'e', 'rad', 'cx', 'cy', 'top')

    def __init__(self, row, t, info):
        self.row = row
        tr, sc = t['Translation'], t['Scale3D']
        self.T = (tr['X'] / 100, tr['Y'] / 100, tr['Z'] / 100)
        self.S = (sc['X'], sc['Y'], sc['Z'])
        self.R = q_to_m(t['Rotation'])
        b = info['bounds']
        self.o = [v / 100 for v in b['origin']]
        self.e = [v / 100 for v in b['extent']]
        self.rad = math.sqrt(sum((self.e[i] * self.S[i]) ** 2 for i in range(3))) + math.sqrt(
            sum((self.o[i] * self.S[i]) ** 2 for i in range(3))
        )
        self.cx, self.cy = self.T[0], self.T[1]
        self.top = self.T[2] + self.rad  # conservative; refined below for upright boxes
        q = t['Rotation']
        if abs(q['X']) < 0.02 and abs(q['Y']) < 0.02:
            self.top = self.T[2] + (self.o[2] + self.e[2]) * self.S[2]

    def hit(self, p, clearance):
        if math.hypot(p[0] - self.cx, p[1] - self.cy) > self.rad + clearance:
            return False
        d = [p[i] - self.T[i] for i in range(3)]
        for i in range(3):
            li = sum(self.R[k][i] * d[k] for k in range(3)) / (self.S[i] or 1e-9)  # R^T d, into mesh local
            if abs(li - self.o[i]) > self.e[i] + clearance / abs(self.S[i] or 1e-9):
                return False
        return True


def load_obbs(data):
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
    obbs = obbs if obbs is not None else load_obbs(data)
    race = data['Race']
    st = race['StartTransform']['Translation']
    pts = [('START', (st['X'] / 100, st['Y'] / 100, st['Z'] / 100))]
    sp0 = race.get('Spoints', [{}])[0].get('Translation')
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
            if 0.05 < u < 0.95:  # the gate's own neighbourhood is exempt
                for o in obbs:
                    if o.top < p[2] - 1.0:
                        continue  # a floor more than 1 m under the line is the floor, not a blocker
                    if o.hit(p, clearance):
                        hits.setdefault(o.row, []).append(round(u * L, 1))
            if land is not None and p[2] < land.height_cm(p[0] * 100, p[1] * 100) / 100 + 0.8:
                low += 1
        if hits or low:
            bad += 1
            if verbose:
                print(f'LEG {na} -> {nb}  ({L:.0f} m)  BLOCKED')
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
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    clearance = float(sys.argv[sys.argv.index('--clearance') + 1]) if '--clearance' in sys.argv else 1.5
    base = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else 'L_BaseLandscape04'
    data = json.load(open(args[0], encoding='utf-8-sig'))
    land = None
    try:
        from landscape import Landscape

        land = Landscape(os.path.join(ROOT, 'data/extracted/Uncrashed/Content/MapEditor/BaseLevel', base))
    except Exception as e:
        print('no terrain check:', e)
    bad = check(data, clearance, land)
    print(f'\n{bad} blocked legs' if bad else '\nall legs clear')
