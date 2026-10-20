import sys, os, json, glob, collections

sys.path.insert(0, 'tools')
from pakread import Pak
from uasset import Asset

PAKS = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Uncrashed FPV Drone Sim/Uncrashed-Mac-Shipping.app/Contents/UE4/Uncrashed/Content/Paks"
)
rows = json.load(open('data/dt_assets.json'))


def field(r, prefix):
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
            fails['err'] += 1
            entry['err'] = str(ex)[:80]
    cat[rn] = entry
json.dump(cat, open('data/catalog.json', 'w'), indent=1)
print('rows', len(cat), 'with bounds', sum(1 for e in cat.values() if 'bounds' in e), 'fails', fails)
print(collections.Counter(e['category'] for e in cat.values()))
print(collections.Counter((e['mesh'] or '').split('/')[2] if e['mesh'] else 'BP' for e in cat.values()).most_common(40))
