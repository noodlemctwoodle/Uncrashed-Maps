#!/usr/bin/env python3
"""Query the Uncrashed asset index (data/asset_index.json, built by tools/build_index.py) from any map generator.

    from assets import find, row, size, base_offset, pick
    trees = find('tree', max_h=14)                 # rows tagged tree up to 14 m tall (hidden rows excluded)
    bench = row('bench')                            # first row whose name matches
    L, W, H = size('NewRow_168')                    # mesh bounds in metres
    z_fix = base_offset('NewRow_50')                # +0.68: the boxcar's base sits 0.68 m above its pivot (it hovers
                                                    # when placed at ground height); rest('NewRow_50') is -0.68

CLI: python3 tools/assets.py tree [max_h] | python3 tools/assets.py name=camaro | python3 tools/assets.py NewRow_303

Index fields used here (per row, see tools/build_index.py): ``name`` (readable), ``source`` (object name), ``tags``,
``category`` (editor display name, e.g. 'Small_assets', 'Foliage', 'Basic shape'), ``size_m`` [L, W, H] or None,
``pivot`` ('base' / 'centre' / 'top' / 'offset'), ``base_offset_m`` (mesh bottom relative to the pivot, m),
``collision``, ``physics``, ``mac_material`` (has an OvverideMatMacOs entry: only 14 wind-animated trees/bushes),
``hidden`` (HideInEditor), ``kind`` ('mesh' / 'blueprint'), ``bounds_estimated``.
"""

import json, os, re, sys, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rnum(r):
    """Sort key for row names: the number of ``NewRow_<n>``; other names sort after all of them (hash-spread)."""
    m = __import__('re').match(r'NewRow_(\d+)$', r)
    return int(m.group(1)) if m else 10**6 + abs(hash(r)) % 10**5


# Loaded once at import; every query reads this dict.
INDEX = json.load(open(os.path.join(ROOT, 'data', 'asset_index.json')))


def rows():
    """The whole index: ``{row name: entry dict}``."""
    return INDEX


def find(
    tag=None,
    name=None,
    category=None,
    min_h=0.0,
    max_h=1e9,
    min_w=0.0,
    max_w=1e9,
    collision=None,
    physics=None,
    mac_only=False,
    include_hidden=False,
):
    """Rows matching a semantic tag and/or a regex on the name, filtered by height/width (m) and flags.

    Parameters
        tag             one of the index tags ('tree', 'bench' is a name, not a tag, ...); None = any
        name            case-insensitive regex searched in ``"<name> <source>"``
        category        exact editor category display name
        min_h, max_h    inclusive bounds on the height (size_m[2]) in metres
        min_w, max_w    inclusive bounds on the larger horizontal size (max of L, W) in metres
        collision, physics   None = ignore, True/False = require that flag value
        mac_only        drop mesh rows tagged 'tree' that have no Mac material override (wind-animated trees
                        without one render untextured on macOS)
        include_hidden  keep rows flagged HideInEditor (excluded by default)
    Rows without bounds count as 0 x 0 x 0 m, so they pass only when the minimums are 0.
    Returns row names sorted numerically.
    """
    out = []
    for rn, e in INDEX.items():
        if e['hidden'] and not include_hidden:
            continue
        if tag and tag not in e['tags']:
            continue
        if name and not re.search(name, e['name'] + ' ' + e['source'], re.I):
            continue
        if category and e['category'] != category:
            continue
        if collision is not None and e['collision'] != collision:
            continue
        if physics is not None and e['physics'] != physics:
            continue
        if mac_only and e['kind'] == 'mesh' and not e['mac_material'] and 'tree' in e['tags']:
            continue
        s = e['size_m'] or [0, 0, 0]
        if not (min_h <= s[2] <= max_h and min_w <= max(s[0], s[1]) <= max_w):
            continue
        out.append(rn)
    return sorted(out, key=rnum)


def row(name, **kw):
    """First (lowest-numbered) row whose name matches regex ``name``; ``kw`` are passed to ``find``. None if none."""
    r = find(name=name, **kw)
    return r[0] if r else None


def size(rn):
    """(L, W, H) in metres of row ``rn``'s mesh bounds; (0, 0, 0) when the row has no bounds."""
    return tuple(INDEX[rn]['size_m'] or (0, 0, 0))


def base_offset(rn):
    """Metres from the pivot down to the mesh bottom (negative when the mesh hangs below the pivot)."""
    b = INDEX[rn]['base_offset_m']
    return b if b is not None else 0.0


def rest(rn):
    """Height to add when placing the row at ground level so its lowest point touches the ground (only lifts meshes
    whose base sits above the pivot; meshes designed to sink, like trees and rocks, are left alone)."""
    # A base more than 5 cm above the pivot would hover: return the (negative) correction that drops it to the ground.
    b = base_offset(rn)
    return -b if b > 0.05 else 0.0


def pick(tag, rng=random, **kw):
    """A random row with ``tag`` (filters in ``kw`` as for ``find``), drawn with ``rng.choice``; None if none match."""
    r = find(tag, **kw)
    return rng.choice(r) if r else None


def describe(rn):
    """One-line human summary of row ``rn``: name, category, tags, size, pivot, base offset and flags."""
    e = INDEX[rn]
    s = e['size_m']
    return (
        f"{rn}: {e['name']} [{e['category']}; {', '.join(e['tags'])}] "
        + (
            f"{s[0]:g} x {s[1]:g} x {s[2]:g} m, pivot {e['pivot']}, base {e['base_offset_m']:+.2f} m"
            if s
            else 'no bounds'
        )
        + f", collision {'yes' if e['collision'] else 'NO'}"
        + (', physics' if e['physics'] else '')
        + (', hidden' if e['hidden'] else '')
        + (', bounds estimated' if e['bounds_estimated'] else '')
    )


if __name__ == '__main__':
    # CLI: a row id describes that row, name=<regex> lists name matches, anything else is a tag with optional max_h.
    a = sys.argv[1:] if len(sys.argv) > 1 else ['tree']
    if a[0].startswith('NewRow_'):
        print(describe(a[0]))
    elif a[0].startswith('name='):
        [print(describe(r)) for r in find(name=a[0][5:])]
    else:
        [print(describe(r)) for r in find(a[0], max_h=float(a[1]) if len(a) > 1 else 1e9)]
