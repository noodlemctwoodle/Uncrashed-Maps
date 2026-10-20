"""Decode DT_MapEditorAssets thumbnails (256x256 DXT5 top mip in .ubulk) into labelled contact sheets."""

import os, glob, json, struct, sys
from PIL import Image, ImageDraw

SRC = 'data/extracted/Uncrashed/Content/MapEditor/DataTables/Thumbnails'


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
            off += 8  # alpha block
            c0, c1, bits = struct.unpack_from('<HHI', data, off)
            off += 8
            cols = bc1_colors(c0, c1)
            for i in range(16):
                px[bx * 4 + i % 4, by * 4 + i // 4] = cols[(bits >> (2 * i)) & 3]
    return img


cat = json.load(open('data/catalog.json'))
rows = sorted(cat.keys(), key=lambda r: int(r.split('_')[1]) if '_' in r else -1)
thumbs = []
for rn in rows:
    f = os.path.join(SRC, rn + '.ubulk')
    if not os.path.exists(f) or cat[rn]['hidden']:
        continue
    data = open(f, 'rb').read()
    if len(data) < 65536:
        continue
    img = decode_bc3(data[:65536], 256, 256).resize((160, 160))
    e = cat[rn]
    name = (e['mesh'] or e['blueprint'] or '?').split('.')[-1][:22]
    b = e.get('bounds')
    size = 'x'.join(str(round(2 * x / 100, 1)) for x in b['extent']) if b else ''
    thumbs.append((rn, name, size, img))
os.makedirs('data/thumbs', exist_ok=True)
PER = 56
COLS = 8
CW, CH = 160, 196
for s in range(0, len(thumbs), PER):
    chunk = thumbs[s : s + PER]
    rows_n = (len(chunk) + COLS - 1) // COLS
    sheet = Image.new('RGB', (COLS * CW, rows_n * CH), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for i, (rn, name, size, img) in enumerate(chunk):
        x, y = (i % COLS) * CW, (i // COLS) * CH
        sheet.paste(img, (x, y))
        d.text((x + 3, y + 162), f'{rn.replace("NewRow_", "R")} {name}', fill=(255, 255, 255))
        d.text((x + 3, y + 178), size, fill=(180, 220, 255))
    sheet.save(f'data/thumbs/sheet_{s // PER:02d}.png')
print(len(thumbs), 'thumbnails,', (len(thumbs) + PER - 1) // PER, 'sheets')
