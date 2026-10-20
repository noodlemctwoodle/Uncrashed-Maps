#!/usr/bin/env python3
"""Index every placeable Uncrashed editor object (all rows of DT_MapEditorAssets) into data/asset_index.json and
docs/ASSETS.md, plus local thumbnail sheets (data/asset_thumbs/, game-derived, git-ignored).

Per row: id, editor category (E_AssetsCategory display names read from the enum asset), mesh or blueprint, a readable
name, size L x W x H (m), where the pivot sits (base / centre / top / offset), base offset (m), collision, physics,
triplanar material, whether a macOS material override exists (meshes without one may render grey on Mac: Bp_Grass),
hidden-in-editor, blueprint component count, and semantic tags (tree, bush, rock, vehicle, person, building, house,
industrial, container, furniture, lamp, sign, fence, barrier, sport, water, ground, shape, decal, neon, crane, ...)
so a generator can ask tools/assets.py for e.g. `find('tree', max_h=12)`."""

import json, os, re, sys, collections, struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')


def rnum(r):
    m = re.match(r'NewRow_(\d+)$', r)
    return int(m.group(1)) if m else 10**6 + abs(hash(r)) % 10**5


from uasset import Asset

rows = json.load(open(os.path.join(DATA, 'dt_assets.json')))
cat = json.load(open(os.path.join(DATA, 'catalog.json')))


def field(r, prefix):
    return next((v for k, v in r.items() if k.startswith(prefix)), None)


# category names: the enum's DisplayNameMap values appear in the uexp in enumerator order
def enum_names(path):
    try:
        a = Asset(path)
    except Exception:
        return {}
    raw = open(path.replace('.uasset', '.uexp'), 'rb').read()
    strs = [s.decode('utf-8', 'ignore') for s in re.findall(rb'[\x20-\x7e]{3,40}', raw)]
    names = [
        s
        for s in strs
        if s not in ('None',)
        and not s.startswith('NewEnumerator')
        and not s.startswith('E_')
        and s[0].isupper()
        and ' ' in s
        or s
        in (
            'Wall',
            'Foliage',
            'Interractive',
            'Custom',
            'Decals',
            'Tools',
            'Institutional',
            'Gates',
            'Small_assets',
            'Big_assets',
        )
    ]
    return {f'E_AssetsCategory::NewEnumerator{i}': n for i, n in enumerate(names)}


CATN = enum_names(os.path.join(DATA, 'extracted/Uncrashed/Content/MapEditor/DataTables/Logics/E_AssetsCategory.uasset'))
TAG_RULES = [  # (tag, regex on the lower-cased mesh/blueprint name)
    ('tree', r'elm|maple|oak|pine|alder|tree(?! ?pot)|birch|spruce|fir|palm|willow|poplar|cork'),
    ('bush', r'bush|shrub|hedge|grass|fern|plant|flower'),
    ('rock', r'rock|cliff|boulder|stone(?!wall)'),
    (
        'vehicle',
        r'camaro|kangoo|van|car(?!ousel|go|d|t)|truck|bus|tractor|forklift|boxcar|train|wagon|bike|moto|boat|plane|helic',
    ),
    ('person', r'pilot|people|woman|man_|human|spectat'),
    ('building', r'bldg|building|tower|skyscr|workshop|house|barn|silo|warehouse|hangar|church|castle|dome'),
    ('house', r'house|cottage|cabin'),
    (
        'industrial',
        r'tank|pipe|generator|scaffold|crane|container|pallet|barrel|crate|hesco|rig|turbine|windmill|fusebox|machine',
    ),
    ('container', r'container'),
    ('furniture', r'bench|table|chair|planter|tree ?pot|trash|dumpster|tent|umbrella|cart|stall|sign|stand'),
    ('lamp', r'lamp|light|projector|lantern'),
    ('sign', r'sign|billboard|screen|led|panel|neon'),
    ('fence', r'fence|handrail|rail|barrier|gate|wall'),
    ('barrier', r'barrier|cone|hesco|tire|tyre|bollard'),
    ('sport', r'rink|goal|ball|ramp|pente|skate|tribune|stadium|track'),
    ('water', r'water|pool|fountain'),
    ('ground', r'baseground|ground|floor|road|asphalt|pavement|dirt|gravel|sand'),
    ('shape', r'^sm_cube|^sm_cylinder|^sm_pyramide|^sm_pente|^sm_corner|cubehole|^sm_block'),
    ('decal', r'decal'),
    ('neon', r'neon'),
    ('crane', r'crane'),
    ('structure', r'concrete|brick|column|beam|stairs|catwalk|wall|floor|arch'),
    ('coin', r'coin'),
    ('balloon', r'balloon'),
    ('race', r'gate|flag|checkpoint'),
]


def tags_for(name, category):
    n = name.lower()
    t = [tag for tag, rx in TAG_RULES if re.search(rx, n)]
    if category == 'Foliage' and not t:
        t.append('tree')
    if category == 'Decals':
        t = ['decal']
    if category == 'Basic shape' and 'shape' not in t:
        t.append('shape')
    return t or ['prop']


def human(name):
    n = re.sub(r'^(sm_|s_|bp_|kb3d_ndb_)', '', name, flags=re.I)
    n = re.sub(r'_me$|_c$', '', n, flags=re.I)
    n = re.sub(r'([a-z])([A-Z])', r'\1 \2', n).replace('_', ' ')
    return re.sub(r'\s+', ' ', n).strip()


index = {}
for rn, r in rows.items():
    e = cat.get(rn, {})
    mesh = field(r, 'Mesh_')
    bp = field(r, 'Blueprint_')
    src = (mesh or bp or '').split('.')[-1]
    b = e.get('bounds')
    size = base = pivot = None
    if b:
        ex = b['extent']
        o = b['origin']
        size = [round(2 * ex[0] / 100, 2), round(2 * ex[1] / 100, 2), round(2 * ex[2] / 100, 2)]
        bot = (o[2] - ex[2]) / 100
        top = (o[2] + ex[2]) / 100
        base = round(bot, 2)
        pivot = (
            'base'
            if abs(bot) < 0.12
            else ('top' if abs(top) < 0.12 else ('centre' if abs(bot + top) < 0.15 * max(size[2], 0.1) else 'offset'))
        )
    category = CATN.get(field(r, 'Category_'), field(r, 'Category_'))
    index[rn] = dict(
        id=rn,
        name=human(src),
        source=src,
        path=mesh or bp,
        kind='blueprint' if bp and not mesh else 'mesh',
        category=category,
        size_m=size,
        pivot=pivot,
        base_offset_m=base,
        collision=bool(field(r, 'Collision?')),
        physics=bool(field(r, 'PhysicsEnabled?')),
        triplanar=bool(field(r, 'Triplanar?')),
        mac_material=bool(field(r, 'OvverideMatMacOs')),
        hidden=bool(field(r, 'HideInEditor')),
        bounds_estimated=bool(e.get('bounds_est')),
        components=e.get('bounds_note'),
        tags=tags_for(src, category),
        thumbnail=field(r, 'Thumbnails_'),
    )
json.dump(index, open(os.path.join(DATA, 'asset_index.json'), 'w'), indent=1)
# ---- thumbnails (local only) and the markdown catalogue ----
from PIL import Image, ImageDraw

SRC = os.path.join(DATA, 'extracted/Uncrashed/Content/MapEditor/DataTables/Thumbnails')
TH = os.path.join(DATA, 'asset_thumbs')
os.makedirs(TH, exist_ok=True)


def bc1_colors(c0, c1):
    def rgb(c):
        return ((c >> 11) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)

    a, b = rgb(c0), rgb(c1)
    return [a, b, tuple((2 * x + y) // 3 for x, y in zip(a, b)), tuple((x + 2 * y) // 3 for x, y in zip(a, b))]


def decode_bc3(data, w, h):
    img = Image.new('RGB', (w, h))
    px = img.load()
    off = 0
    for by in range(h // 4):
        for bx in range(w // 4):
            off += 8
            c0, c1, bits = struct.unpack_from('<HHI', data, off)
            off += 8
            cols = bc1_colors(c0, c1)
            for i in range(16):
                px[bx * 4 + i % 4, by * 4 + i // 4] = cols[(bits >> (2 * i)) & 3]
    return img


thumbs = {}
for rn in index:
    f = os.path.join(SRC, rn + '.ubulk')
    if os.path.exists(f) and os.path.getsize(f) >= 65536:
        p = os.path.join(TH, rn + '.png')
        if not os.path.exists(p):
            decode_bc3(open(f, 'rb').read()[:65536], 256, 256).resize((128, 128)).save(p)
        thumbs[rn] = p
by_tag = collections.defaultdict(list)
for rn, e in index.items():
    for t in e['tags']:
        by_tag[t].append(rn)
for t, lst in by_tag.items():  # one contact sheet per tag
    lst = sorted(lst, key=rnum)
    COLS = 8
    CW, CH = 136, 170
    n = len(lst)
    rows_n = (n + COLS - 1) // COLS
    sheet = Image.new('RGB', (COLS * CW, max(1, rows_n) * CH), (28, 28, 30))
    d = ImageDraw.Draw(sheet)
    for i, rn in enumerate(lst):
        x, y = (i % COLS) * CW, (i // COLS) * CH
        if rn in thumbs:
            sheet.paste(Image.open(thumbs[rn]), (x + 4, y + 4))
        e = index[rn]
        d.text((x + 4, y + 134), f"{rn.replace('NewRow_', 'R')} {e['name'][:18]}", fill=(255, 255, 255))
        d.text((x + 4, y + 150), 'x'.join(str(v) for v in e['size_m']) if e['size_m'] else '?', fill=(170, 210, 255))
    sheet.save(os.path.join(TH, f'sheet_{t}.png'))
# markdown catalogue (no images: thumbnails are game assets and stay local)
lines = [
    '# Uncrashed editor asset index',
    '',
    f'{len(index)} rows of DT_MapEditorAssets. Sizes in metres (L x W x H of the mesh bounds); pivot says where the',
    'row\'s origin sits on the mesh; base offset is the mesh bottom relative to the pivot (negative = sinks when placed at ground height).',
    'Generated by `tools/build_index.py`; query with `tools/assets.py` (`python3 tools/assets.py tree`). Thumbnail sheets per tag are in',
    '`data/asset_thumbs/` after running the indexer (game-derived, not committed).',
    '',
    '`macOS override` marks rows whose table entry lists Mac-specific materials (OvverideMatMacOs). Only 14 rows have one, all wind-animated',
    'trees and bushes whose Windows material has no Mac version; every other mesh uses a material that already works on Mac, so an empty cell',
    'is normal. The exception is Bp_Grass (R663), which has no override and renders grey on Mac: use green cubes for lawns.',
    '',
]
for t in sorted(by_tag, key=lambda k: -len(by_tag[k])):
    lines += [
        f'## {t} ({len(by_tag[t])})',
        '',
        '| row | name | category | size L x W x H m | pivot | base | coll | phys | macOS override | notes |',
        '|---|---|---|---|---|---|---|---|---|---|',
    ]
    for rn in sorted(by_tag[t], key=rnum):
        e = index[rn]
        sz = ' x '.join(f'{v:g}' for v in e['size_m']) if e['size_m'] else '?'
        notes = (
            ('hidden ' if e['hidden'] else '')
            + ('est. bounds ' if e['bounds_estimated'] else '')
            + (f"{e['components']} " if e['kind'] == 'blueprint' and e['components'] else '')
            + ('triplanar' if e['triplanar'] else '')
        )
        lines.append(
            f"| {rn.replace('NewRow_', 'R')} | {e['name']} | {e['category']} | {sz} | {e['pivot'] or '?'} | {e['base_offset_m'] if e['base_offset_m'] is not None else '?'} | {'y' if e['collision'] else 'n'} | {'y' if e['physics'] else ''} | {'y' if e['mac_material'] else ''} | {notes.strip()} |"
        )
    lines.append('')
os.makedirs(os.path.join(ROOT, 'docs'), exist_ok=True)
open(os.path.join(ROOT, 'docs', 'ASSETS.md'), 'w').write('\n'.join(lines))
print(
    len(index),
    'rows indexed;',
    len(thumbs),
    'thumbnails;',
    {t: len(v) for t, v in sorted(by_tag.items(), key=lambda kv: -len(kv[1]))},
)
print('categories:', collections.Counter(e['category'] for e in index.values()))
