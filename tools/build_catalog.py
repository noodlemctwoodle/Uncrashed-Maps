"""Dump DT_MapEditorAssets into data/catalog.json with each static mesh's bounds read from the game files.

Purpose
    Turn the editor's asset table (``data/dt_assets.json``, the rows of DT_MapEditorAssets as dumped by
    ``tools/uasset.py ... dt``) into the catalog that every map generator uses for mesh sizes and pivots, by extracting
    each row's StaticMesh from the paks and reading its ``ExtendedBounds``.

Usage
    python3 tools/build_catalog.py        (run from the repo root: paths are relative; rewrites data/catalog.json)
    Blueprint rows and basic shapes get no bounds here; tools/bounds_fix.py completes them afterwards.

Inputs
    The game's paks (``PAKS``), ``data/dt_assets.json``. Extracted assets are cached under ``data/extracted/``
    (git-ignored) so reruns do not touch the paks again.
Outputs
    ``data/catalog.json``: ``{row: {row, category, mesh, blueprint, hidden, bbmul, pivot, collision, bounds?,
    lightmap?, err?}}``. ``bounds`` is ``{origin: [x, y, z], extent: [hx, hy, hz]}`` in cm (half-sizes), taken
    from the mesh's ``ExtendedBounds``; ``pivot`` is the table's PivotPointOffset column, which the game does NOT
    apply to stored transforms (trust the mesh bounds instead; see SKILL.md). Prints counts of rows, bounds,
    failures, categories and the most common content folders.

Format facts
    Table columns are Blueprint user-struct members, so their names carry a ``_<index>_<GUID>`` suffix
    (``Mesh_2_9AE7353A...``); ``field`` matches on the prefix. Mesh references are ``/Game/Dir/Name.Name`` and map
    to ``../../../Uncrashed/Content/Dir/Name.uasset`` + ``.uexp`` inside the paks. A StaticMesh's bounds live in the
    tagged property ``ExtendedBounds`` (FBoxSphereBounds: Origin, BoxExtent, SphereRadius) of the export whose class
    ends in ``StaticMesh``; basic shapes omit ``Origin`` (it is zero), which makes this script record no bounds for
    them.
"""

import sys, os, json, glob, collections

sys.path.insert(0, 'tools')
from pakread import Pak
from uasset import Asset

PAKS = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Uncrashed FPV Drone Sim/Uncrashed-Mac-Shipping.app/Contents/UE4/Uncrashed/Content/Paks"
)
rows = json.load(open('data/dt_assets.json'))


def field(r, prefix):
    """Value of the first column of row ``r`` whose name starts with ``prefix`` (None if no column matches).

    Needed because cooked Blueprint struct members are named ``<Name>_<index>_<GUID>``.
    """
    for k, v in r.items():
        if k.startswith(prefix):
            return v


# index all pak files once
index = {}
paks = {}
for p in sorted(glob.glob(os.path.join(PAKS, '*.pak'))):
    pk = Pak(p)
    paks[p] = pk
    for f in pk.files:
        index[f] = pk


def extract(game_path):
    """Extract the ``.uasset`` and ``.uexp`` of a ``/Game/...`` object path into data/extracted (cached).

    Returns the local ``.uasset`` path, or None when either file is missing from every pak.
    """
    # /Game/X/Y.Y -> ../../../Uncrashed/Content/X/Y.uasset
    rel = game_path.split('.')[0].replace('/Game/', '../../../Uncrashed/Content/')
    outs = []
    for ext in ('.uasset', '.uexp'):
        f = rel + ext
        if f not in index:
            return None
        dst = os.path.join('data/extracted', f.replace('../../../', ''))
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(index[f].read(f))
        outs.append(dst)
    return outs[0]


cat = {}
fails = collections.Counter()
for rn, r in rows.items():
    mesh = field(r, 'Mesh_')
    bp = field(r, 'Blueprint_')
    entry = dict(
        row=rn,
        category=field(r, 'Category_'),
        mesh=mesh,
        blueprint=bp,
        hidden=field(r, 'HideInEditor'),
        bbmul=field(r, 'BoundingBox_Multiplicator'),
        pivot=field(r, 'PivotPointOffset'),
        collision=field(r, 'Collision?'),
    )
    if mesh:
        try:
            ua = extract(mesh)
            if ua:
                a = Asset(ua)
                # The first export of class ...StaticMesh carries ExtendedBounds; blueprint rows are skipped.
                for i, e in enumerate(a.exports):
                    if a.ref(e['cls']) and a.ref(e['cls']).endswith('StaticMesh'):
                        props = a.read_props(a.export_reader(i))
                        b = props.get('ExtendedBounds')
                        if b:
                            entry['bounds'] = dict(
                                origin=[b['Origin']['X'], b['Origin']['Y'], b['Origin']['Z']],
                                extent=[b['BoxExtent']['X'], b['BoxExtent']['Y'], b['BoxExtent']['Z']],
                            )
                        entry['lightmap'] = props.get('LightMapResolution')
                        break
                if 'bounds' not in entry:
                    fails['nobounds'] += 1
            else:
                fails['notinpak'] += 1
        except Exception as ex:
            # A missing Origin (basic shapes) raises KeyError here and is recorded as err; bounds_fix.py repairs it.
            fails['err'] += 1
            entry['err'] = str(ex)[:80]
    cat[rn] = entry
json.dump(cat, open('data/catalog.json', 'w'), indent=1)
print('rows', len(cat), 'with bounds', sum(1 for e in cat.values() if 'bounds' in e), 'fails', fails)
print(collections.Counter(e['category'] for e in cat.values()))
print(collections.Counter((e['mesh'] or '').split('/')[2] if e['mesh'] else 'BP' for e in cat.values()).most_common(40))
