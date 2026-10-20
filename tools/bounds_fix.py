#!/usr/bin/env python3
"""Complete data/catalog.json bounds for every row: basic shapes whose ExtendedBounds omit Origin, and blueprint rows
(union of their StaticMeshComponent meshes' bounds, offset by RelativeLocation and scaled by RelativeScale3D).

Purpose
    tools/build_catalog.py only records bounds for mesh rows whose ``ExtendedBounds`` has both Origin and BoxExtent.
    This pass fills the rest: basic shapes (SM_Cube, SM_Cylinder, SM_CubeHole, SM_Pente: 1 m, centre pivot) whose
    cooked bounds leave ``Origin`` out because it is zero, and blueprint rows (BP_meWater, Bp_Grass, lamps, gates
    ...) whose size is the union of the StaticMeshComponents in the Blueprint's generated class.

Usage
    python3 tools/bounds_fix.py      (rewrites data/catalog.json in place; prints the fixed count and what is still
                                      missing with the reason)

Inputs
    The game's paks (``PAKS``), ``data/catalog.json`` (rows lacking ``bounds``); assets are extracted on demand
    into ``data/extracted/`` (cached).
Outputs
    Each repaired row gets ``bounds = {origin: [x, y, z], extent: [hx, hy, hz]}`` in cm (centre and half-sizes in the
    row's own frame, i.e. relative to the pivot the game places). Blueprint rows also get ``bounds_from =
    'blueprint components'`` and ``bounds_note`` (component count, unreadable parts). Rows that still fail keep or
    gain ``err``/``bounds_note``. Four rows (electric poles, Megascans pipe, Maple08) were later estimated by hand
    and carry ``bounds_est``; this script does not set that flag.

Format facts
    A Blueprint asset's exports include one object per component of its SimpleConstructionScript; the ones whose
    class ends in ``StaticMeshComponent`` have ``StaticMesh`` (a ``/Game/...`` object path), ``RelativeLocation``
    (cm), ``RelativeRotation`` (degrees, Pitch/Yaw/Roll) and ``RelativeScale3D``; absent properties mean the UE
    defaults (0 / 1). Component bounds are composed as ``centre = RelativeLocation + Origin * scale`` and
    ``half = BoxExtent * |scale|``.

Gotchas
    Rotation is not applied exactly: a part rotated by more than 1 degree on any axis has its horizontal extents
    inflated to the larger of the two (a square footprint that always contains the rotated box); vertical extent is
    kept as is. Child components are treated as if attached to the root (no parent transform chaining).
"""

import sys, os, json, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pakread import Pak
from uasset import Asset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKS = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Uncrashed FPV Drone Sim/Uncrashed-Mac-Shipping.app/Contents/UE4/Uncrashed/Content/Paks"
)
# One {in-pak path: Pak} index over every pak so extract() can find any asset (later paks override earlier ones).
index = {}
for p in sorted(glob.glob(os.path.join(PAKS, '*.pak'))):
    pk = Pak(p)
    for f in pk.files:
        index[f] = pk


def extract(game_path):
    """Extract the ``.uasset`` and ``.uexp`` of a ``/Game/Dir/Name.Name`` object path into data/extracted (cached).

    Returns the local ``.uasset`` path, or None when either file is missing from the paks.
    """
    rel = game_path.split('.')[0].replace('/Game/', '../../../Uncrashed/Content/')
    outs = []
    for ext in ('.uasset', '.uexp'):
        f = rel + ext
        if f not in index:
            return None
        dst = os.path.join(ROOT, 'data/extracted', f.replace('../../../', ''))
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(index[f].read(f))
        outs.append(dst)
    return outs[0]


def mesh_bounds(game_path):
    """(origin, extent) in cm for a StaticMesh asset, or None.

    Reads ``ExtendedBounds`` of the first export whose class ends in ``StaticMesh``; a missing ``Origin`` (basic
    shapes) is taken as zero, a missing ``BoxExtent`` returns None. Both values are ``[x, y, z]`` lists.
    """
    ua = extract(game_path)
    if not ua:
        return None
    a = Asset(ua)
    for i, e in enumerate(a.exports):
        if a.ref(e['cls']) and a.ref(e['cls']).endswith('StaticMesh'):
            b = a.read_props(a.export_reader(i)).get('ExtendedBounds')
            if not b or 'BoxExtent' not in b:
                return None
            o = b.get('Origin') or {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
            return [o.get('X', 0.0), o.get('Y', 0.0), o.get('Z', 0.0)], [
                b['BoxExtent']['X'],
                b['BoxExtent']['Y'],
                b['BoxExtent']['Z'],
            ]
    return None


def bp_bounds(game_path):
    """Union of the StaticMeshComponent bounds of a Blueprint asset.

    ``game_path`` is the ``/Game/...`` path of the Blueprint (``_C`` class suffix or not; only the package matters).
    Returns ``((centre, half_extents), note)`` in cm, or ``(None, reason)`` when the asset is not in the paks or has
    no readable mesh component. ``note`` lists the component count and up to two problems (unreadable component,
    mesh whose bounds failed). Rotated parts are inflated as described in the module docstring.
    """
    ua = extract(game_path)
    if not ua:
        return None, 'bp not in pak'
    a = Asset(ua)
    lo = [1e9] * 3
    hi = [-1e9] * 3
    parts = 0
    notes = []
    for i, e in enumerate(a.exports):
        cls = a.ref(e['cls']) or ''
        if not cls.endswith('StaticMeshComponent'):
            continue
        try:
            props = a.read_props(a.export_reader(i))
        except Exception as ex:
            notes.append(f'component unreadable: {ex}'[:60])
            continue
        sm = props.get('StaticMesh')
        if not sm:
            continue
        try:
            mb = mesh_bounds(sm)
        except Exception as ex:
            mb = None
            notes.append(f'{sm.split("/")[-1]}: {ex}'[:70])
        if not mb:
            continue
        o, ex_ = mb
        # Component transform; UE defaults apply when a property is absent (location 0, scale 1, no rotation).
        loc = props.get('RelativeLocation') or {}
        sc = props.get('RelativeScale3D') or {}
        rot = props.get('RelativeRotation')
        s = [sc.get('X', 1.0), sc.get('Y', 1.0), sc.get('Z', 1.0)]
        l = [loc.get('X', 0.0), loc.get('Y', 0.0), loc.get('Z', 0.0)]
        if rot and any(
            abs(rot.get(k, 0.0)) > 1 for k in ('Pitch', 'Yaw', 'Roll')
        ):  # rotated part: inflate to its largest horizontal extent
            r = max(ex_[0] * abs(s[0]), ex_[1] * abs(s[1]))
            ex_ = [r / abs(s[0] or 1), r / abs(s[1] or 1), ex_[2]]
        # Axis-aligned union in the blueprint's frame: centre = location + origin * scale, half = extent * |scale|.
        for k in range(3):
            c = l[k] + o[k] * s[k]
            h = ex_[k] * abs(s[k])
            lo[k] = min(lo[k], c - h)
            hi[k] = max(hi[k], c + h)
        parts += 1
    if not parts:
        return None, 'no mesh components (' + '; '.join(notes[:3]) + ')'
    return ([(lo[k] + hi[k]) / 2 for k in range(3)], [(hi[k] - lo[k]) / 2 for k in range(3)]), f'{parts} components' + (
        '; ' + '; '.join(notes[:2]) if notes else ''
    )


if __name__ == '__main__':
    # Repair pass: mesh rows first (basic shapes), then blueprint rows; rows with bounds already are untouched.
    cat = json.load(open(os.path.join(ROOT, 'data/catalog.json')))
    fixed = 0
    still = []
    for rn, e in cat.items():
        if e.get('bounds'):
            continue
        try:
            if e.get('mesh'):
                mb = mesh_bounds(e['mesh'])
                if mb:
                    e['bounds'] = dict(origin=mb[0], extent=mb[1])
                    e.pop('err', None)
                    fixed += 1
                    continue
            if e.get('blueprint'):
                mb, note = bp_bounds(e['blueprint'])
                e['bounds_note'] = note
                if mb:
                    e['bounds'] = dict(origin=mb[0], extent=mb[1])
                    e['bounds_from'] = 'blueprint components'
                    fixed += 1
                    continue
        except Exception as ex:
            e['err'] = str(ex)[:80]
        still.append(
            (
                rn,
                (e.get('mesh') or e.get('blueprint') or '').split('/')[-1].split('.')[0],
                e.get('err') or e.get('bounds_note'),
            )
        )
    json.dump(cat, open(os.path.join(ROOT, 'data/catalog.json'), 'w'), indent=1)
    print('fixed', fixed, 'still missing', len(still))
    for s in still:
        print('  ', *s)
