#!/usr/bin/env python3
"""Query the Uncrashed asset index (data/asset_index.json, built by tools/build_index.py) from any map generator.

    from assets import find, row, size, base_offset, pick
    trees = find('tree', max_h=14)                 # rows tagged tree up to 14 m tall, visible in the editor, with collision
    bench = row('bench')                            # first row whose name matches
    L, W, H = size('NewRow_168')                    # mesh bounds in metres
    z_fix = base_offset('NewRow_50')                # -0.68: lift the boxcar by 0.68 m so its wheels touch the ground

CLI: python3 tools/assets.py tree [max_h] | python3 tools/assets.py name=camaro | python3 tools/assets.py NewRow_303"""
import json, os, re, sys, random
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def rnum(r):
    m = __import__('re').match(r'NewRow_(\d+)$', r); return int(m.group(1)) if m else 10 ** 6 + abs(hash(r)) % 10 ** 5

INDEX = json.load(open(os.path.join(ROOT, 'data', 'asset_index.json')))
def rows(): return INDEX
def find(tag=None, name=None, category=None, min_h=0.0, max_h=1e9, min_w=0.0, max_w=1e9, collision=None, physics=None, mac_only=False, include_hidden=False):
    """Rows matching a semantic tag and/or a regex on the name, filtered by height/width (m) and flags."""
    out = []
    for rn, e in INDEX.items():
        if e['hidden'] and not include_hidden: continue
        if tag and tag not in e['tags']: continue
        if name and not re.search(name, e['name'] + ' ' + e['source'], re.I): continue
        if category and e['category'] != category: continue
        if collision is not None and e['collision'] != collision: continue
        if physics is not None and e['physics'] != physics: continue
        if mac_only and e['kind'] == 'mesh' and not e['mac_material'] and 'tree' in e['tags']: continue
        s = e['size_m'] or [0, 0, 0]
        if not (min_h <= s[2] <= max_h and min_w <= max(s[0], s[1]) <= max_w): continue
        out.append(rn)
    return sorted(out, key=rnum)
def row(name, **kw):
    r = find(name=name, **kw); return r[0] if r else None
def size(rn): return tuple(INDEX[rn]['size_m'] or (0, 0, 0))
def base_offset(rn):
    """Metres from the pivot down to the mesh bottom (negative when the mesh hangs below the pivot)."""
    b = INDEX[rn]['base_offset_m']; return b if b is not None else 0.0
def rest(rn):
    """Height to add when placing the row at ground level so its lowest point touches the ground (only lifts meshes
    whose base sits above the pivot; meshes designed to sink, like trees and rocks, are left alone)."""
    b = base_offset(rn); return -b if b > 0.05 else 0.0
def pick(tag, rng=random, **kw):
    r = find(tag, **kw); return rng.choice(r) if r else None
def describe(rn):
    e = INDEX[rn]; s = e['size_m']
    return f"{rn}: {e['name']} [{e['category']}; {', '.join(e['tags'])}] " + (f"{s[0]:g} x {s[1]:g} x {s[2]:g} m, pivot {e['pivot']}, base {e['base_offset_m']:+.2f} m" if s else 'no bounds') + f", collision {'yes' if e['collision'] else 'NO'}" + (', physics' if e['physics'] else '') + (', hidden' if e['hidden'] else '') + (', bounds estimated' if e['bounds_estimated'] else '')
if __name__ == '__main__':
    a = sys.argv[1:] if len(sys.argv) > 1 else ['tree']
    if a[0].startswith('NewRow_'): print(describe(a[0]))
    elif a[0].startswith('name='): [print(describe(r)) for r in find(name=a[0][5:])]
    else: [print(describe(r)) for r in find(a[0], max_h=float(a[1]) if len(a) > 1 else 1e9)]
