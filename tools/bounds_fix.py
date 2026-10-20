#!/usr/bin/env python3
"""Complete data/catalog.json bounds for every row: basic shapes whose ExtendedBounds omit Origin, and blueprint rows
(union of their StaticMeshComponent meshes' bounds, offset by RelativeLocation and scaled by RelativeScale3D)."""
import sys, os, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pakread import Pak
from uasset import Asset
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKS = os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Uncrashed FPV Drone Sim/Uncrashed-Mac-Shipping.app/Contents/UE4/Uncrashed/Content/Paks")
index = {}
for p in sorted(glob.glob(os.path.join(PAKS, '*.pak'))):
    pk = Pak(p)
    for f in pk.files: index[f] = pk
def extract(game_path):
    rel = game_path.split('.')[0].replace('/Game/', '../../../Uncrashed/Content/'); outs = []
    for ext in ('.uasset', '.uexp'):
        f = rel + ext
        if f not in index: return None
        dst = os.path.join(ROOT, 'data/extracted', f.replace('../../../', ''))
        if not os.path.exists(dst): os.makedirs(os.path.dirname(dst), exist_ok=True); open(dst, 'wb').write(index[f].read(f))
        outs.append(dst)
    return outs[0]
def mesh_bounds(game_path):
    """(origin, extent) in cm for a StaticMesh asset, or None."""
    ua = extract(game_path)
    if not ua: return None
    a = Asset(ua)
    for i, e in enumerate(a.exports):
        if a.ref(e['cls']) and a.ref(e['cls']).endswith('StaticMesh'):
            b = a.read_props(a.export_reader(i)).get('ExtendedBounds')
            if not b or 'BoxExtent' not in b: return None
            o = b.get('Origin') or {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
            return [o.get('X', 0.0), o.get('Y', 0.0), o.get('Z', 0.0)], [b['BoxExtent']['X'], b['BoxExtent']['Y'], b['BoxExtent']['Z']]
    return None
def bp_bounds(game_path):
    ua = extract(game_path)
    if not ua: return None, 'bp not in pak'
    a = Asset(ua); lo = [1e9] * 3; hi = [-1e9] * 3; parts = 0; notes = []
    for i, e in enumerate(a.exports):
        cls = a.ref(e['cls']) or ''
        if not cls.endswith('StaticMeshComponent'): continue
        try: props = a.read_props(a.export_reader(i))
        except Exception as ex: notes.append(f'component unreadable: {ex}'[:60]); continue
        sm = props.get('StaticMesh')
        if not sm: continue
        try: mb = mesh_bounds(sm)
        except Exception as ex: mb = None; notes.append(f'{sm.split("/")[-1]}: {ex}'[:70])
        if not mb: continue
        o, ex_ = mb; loc = props.get('RelativeLocation') or {}; sc = props.get('RelativeScale3D') or {}; rot = props.get('RelativeRotation')
        s = [sc.get('X', 1.0), sc.get('Y', 1.0), sc.get('Z', 1.0)]; l = [loc.get('X', 0.0), loc.get('Y', 0.0), loc.get('Z', 0.0)]
        if rot and any(abs(rot.get(k, 0.0)) > 1 for k in ('Pitch', 'Yaw', 'Roll')):   # rotated part: inflate to its largest horizontal extent
            r = max(ex_[0] * abs(s[0]), ex_[1] * abs(s[1])); ex_ = [r / abs(s[0] or 1), r / abs(s[1] or 1), ex_[2]]
        for k in range(3):
            c = l[k] + o[k] * s[k]; h = ex_[k] * abs(s[k]); lo[k] = min(lo[k], c - h); hi[k] = max(hi[k], c + h)
        parts += 1
    if not parts: return None, 'no mesh components (' + '; '.join(notes[:3]) + ')'
    return ([(lo[k] + hi[k]) / 2 for k in range(3)], [(hi[k] - lo[k]) / 2 for k in range(3)]), f'{parts} components' + ('; ' + '; '.join(notes[:2]) if notes else '')
if __name__ == '__main__':
    cat = json.load(open(os.path.join(ROOT, 'data/catalog.json'))); fixed = 0; still = []
    for rn, e in cat.items():
        if e.get('bounds'): continue
        try:
            if e.get('mesh'):
                mb = mesh_bounds(e['mesh'])
                if mb: e['bounds'] = dict(origin=mb[0], extent=mb[1]); e.pop('err', None); fixed += 1; continue
            if e.get('blueprint'):
                mb, note = bp_bounds(e['blueprint']); e['bounds_note'] = note
                if mb: e['bounds'] = dict(origin=mb[0], extent=mb[1]); e['bounds_from'] = 'blueprint components'; fixed += 1; continue
        except Exception as ex: e['err'] = str(ex)[:80]
        still.append((rn, (e.get('mesh') or e.get('blueprint') or '').split('/')[-1].split('.')[0], e.get('err') or e.get('bounds_note')))
    json.dump(cat, open(os.path.join(ROOT, 'data/catalog.json'), 'w'), indent=1)
    print('fixed', fixed, 'still missing', len(still))
    for s in still: print('  ', *s)
