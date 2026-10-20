#!/usr/bin/env python3
"""Physical sanity checks for a generated Uncrashed map, using the mesh bounds in data/catalog.json:
  floaters  - a prop whose lowest point is more than 0.3 m above the terrain with nothing under it
  buried    - a prop whose top is below the terrain
  off_map   - an instance outside the landscape
Rotated (pitched/rolled) instances are skipped. usage: mapcheck.py <map.json> [--base L_BaseLandscape04]"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raceline
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def upright(t):
    q = t['Rotation']; return abs(q['X']) < 0.02 and abs(q['Y']) < 0.02
def run(data, land, struct_rows=(), verbose=True):
    obbs = [o for o in raceline.load_obbs(data)]
    # supports: top faces (z) of every upright box, indexed by 10 m cell
    tops = {}
    recs = []
    for a in data['S_AssetsTransform']:
        info = raceline.CAT.get(a['Rname']); 
        if not info or not info.get('bounds'): continue
        for t in a['Transform']:
            if not upright(t): continue
            o = raceline.OBB(a['Rname'], t, info)
            bot = o.T[2] + (o.o[2] - o.e[2]) * o.S[2]; top = o.T[2] + (o.o[2] + o.e[2]) * o.S[2]
            rx = max(o.e[0] * abs(o.S[0]), o.e[1] * abs(o.S[1]))
            recs.append((o.row, o.T[0], o.T[1], bot, top, rx))
            tops.setdefault((int(o.T[0] // 10), int(o.T[1] // 10)), []).append((o.T[0], o.T[1], top, rx))
    floaters = {}; buried = {}; off = 0
    for (row, x, y, bot, top, rx) in recs:
        if row in struct_rows: continue
        h = land.height_cm(x * 100, y * 100)
        if h is None: off += 1; continue
        g = h / 100
        if bot - g > 0.3:
            supported = False
            for cx in (int(x // 10) - 1, int(x // 10), int(x // 10) + 1):
                for cy in (int(y // 10) - 1, int(y // 10), int(y // 10) + 1):
                    for (sx, sy, stop, srx) in tops.get((cx, cy), []):
                        if abs(stop - bot) < 0.45 and math.hypot(sx - x, sy - y) < srx + rx * 0.5: supported = True; break
                    if supported: break
                if supported: break
            if not supported: floaters.setdefault(row, []).append((round(x), round(y), round(bot - g, 1)))
        if top < g - 0.2: buried.setdefault(row, []).append((round(x), round(y), round(g - top, 1)))
    if verbose:
        def nm(r): return (raceline.CAT[r]['mesh'] or raceline.CAT[r].get('blueprint') or '').split('/')[-1].split('.')[0]
        for r, v in sorted(floaters.items(), key=lambda kv: -len(kv[1])): print(f'FLOATING {r:<12}{len(v):>5}  {nm(r):<30} e.g. {v[:4]}')
        for r, v in sorted(buried.items(), key=lambda kv: -len(kv[1])): print(f'BURIED   {r:<12}{len(v):>5}  {nm(r):<30} e.g. {v[:4]}')
        print(f'{sum(map(len, floaters.values()))} floating, {sum(map(len, buried.values()))} buried, {off} off the landscape')
    return floaters, buried, off
if __name__ == '__main__':
    if '--flat' in sys.argv:                                         # the Empty board: flat landscape at the given height (cm)
        class Flat:
            def __init__(self, z): self.z = z
            def height_cm(self, x, y): return self.z if abs(x) < 302400 and abs(y) < 302400 else None
        land = Flat(float(sys.argv[sys.argv.index('--flat') + 1]))
    else:
        from landscape import Landscape
        base = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else 'L_BaseLandscape04'
        land = Landscape(os.path.join(ROOT, 'data/extracted/Uncrashed/Content/MapEditor/BaseLevel', base))
    run(json.load(open(sys.argv[1], encoding='utf-8-sig')), land)
