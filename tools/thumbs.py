"""Decode DT_MapEditorAssets thumbnails (256x256 DXT5 top mip in .ubulk) into labelled contact sheets.

Purpose
    A quick visual catalogue of every visible editor row: each row's thumbnail texture (``Thumbnails_`` column of
    DT_MapEditorAssets, extracted to ``data/extracted/.../Thumbnails/<row>.ubulk``) is decoded and pasted on sheets
    of 56 with the row id, mesh name and size.

Usage
    python3 tools/thumbs.py        (run from the repo root; needs Pillow; writes data/thumbs/sheet_NN.png)

Inputs
    ``data/catalog.json`` (row order, hidden flag, mesh/blueprint name, bounds) and the thumbnail ``.ubulk`` files.
    Rows without a ``.ubulk``, hidden rows and files shorter than 65536 bytes are skipped.
Outputs
    ``data/thumbs/sheet_NN.png``: 8 columns of 160 x 196 px cells (160 px thumbnail, two text lines: ``R<n> <name>``
    and ``L x W x H`` in metres from the catalog extents). Git-ignored: thumbnails are game assets.

Format facts (BC3 / DXT5)
    The thumbnails are 256 x 256 PF_DXT5 textures whose top mip is 64 x 64 blocks x 16 bytes = 65536 bytes; the
    first 65536 bytes of each ``.ubulk`` are taken as that mip (empirical: no bulk header is parsed). Each 16-byte
    block covers 4 x 4 texels, blocks in row-major order: 8 bytes of alpha (two u8 endpoints + 48 bits of 3-bit
    indices, ignored here) then an 8-byte BC1 colour block: two RGB565 endpoints c0, c1 (u16 LE) and a u32 of
    sixteen 2-bit palette indices, texel i (row i // 4, column i % 4) at bits 2i..2i+1. In BC3 the colour block is
    always in 4-colour mode (c0, c1, 2/3 c0 + 1/3 c1, 1/3 c0 + 2/3 c1) regardless of endpoint order, which is why
    no c0 <= c1 check is needed.
"""

import os, glob, json, struct, sys
from PIL import Image, ImageDraw

SRC = 'data/extracted/Uncrashed/Content/MapEditor/DataTables/Thumbnails'


def bc1_colors(c0, c1):
    """Four-entry RGB palette of a BC1 colour block from its RGB565 endpoints ``c0``, ``c1``.

    5/6-bit channels are expanded to 8 bits by ``* 255 // 31`` and ``* 255 // 63``; entries 2 and 3 are the 2:1
    and 1:2 blends. Returns a list of four (r, g, b) tuples.
    """

    def rgb(c):
        """Split a 16-bit RGB565 value into an 8-bit (r, g, b) tuple."""
        return ((c >> 11) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)

    a, b = rgb(c0), rgb(c1)
    return [a, b, tuple((2 * x + y) // 3 for x, y in zip(a, b)), tuple((x + 2 * y) // 3 for x, y in zip(a, b))]


def decode_bc3(data, w, h):
    """Decode ``w`` x ``h`` texels of BC3 block data (``w``, ``h`` multiples of 4) into an RGB ``Image``.

    Alpha blocks are skipped (8 bytes each); colour comes from the BC1 half of every block.
    """
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
# Numeric row order (NewRow_13 before NewRow_204); rows without an underscore sort first.
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
    # Full size in metres = 2 * half extent (cm) / 100.
    size = 'x'.join(str(round(2 * x / 100, 1)) for x in b['extent']) if b else ''
    thumbs.append((rn, name, size, img))
os.makedirs('data/thumbs', exist_ok=True)
# Sheet layout: PER thumbnails per sheet, COLS per row, cells CW x CH px (thumbnail plus two caption lines).
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
