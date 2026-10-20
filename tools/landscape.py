"""Decode a UE4 landscape's heightmap textures from a cooked level (.umap/.uexp/.ubulk) into a world-height sampler.

Purpose
    Give map generators the real ground height of a base level (BaseLandscape04 "Mountain" and friends) without the
    game: ``Landscape(base).height_cm(x, y)`` returns the terrain height in cm at world (x, y) cm, or None off the
    landscape. Validated: the sampler returns exactly -15.00 m at BaseLandscape04's PlayerStart (world origin) and
    ground-standing objects of six player-built Workshop maps sit at 0.00-0.08 m above it (see README / SKILL.md).

Usage
    python3 tools/landscape.py <level path without extension> [heightmap.png]
        prints the landscape transform, component count and sample heights; with a PNG path (needs Pillow) it also
        renders a 1024 px greyscale heightmap of the +-1300 m square around the origin (+X up, +Y right, black =
        off-landscape).
    from landscape import Landscape; L = Landscape('data/extracted/.../BaseLandscape04'); L.height_cm(x_cm, y_cm)

Inputs
    ``base + '.uasset'`` and ``base + '.uexp'`` (the cooked level, read with tools/uasset.py) and ``base + '.ubulk'``
    (streamed texture payloads; optional when the heightmaps are stored inline).

File-format facts the code relies on (UE 4.27 ALandscape / ULandscapeComponent / UTexture2D)
    Landscape placement: the actor's ``RootComponent0`` RelativeLocation (cm) and RelativeScale3D (cm per quad in
      X/Y, Z scale factor; defaults 100).
    Components: every export whose class is ``LandscapeComponent`` has RelativeLocation = (SectionBaseX,
      SectionBaseY) in quad units, ComponentSizeQuads (quads per side; 63 default, same for every component),
      HeightmapTexture (an export reference) and HeightmapScaleBias = (1/texW, 1/texH, U offset, V offset): Z/W give
      where this component's (quads+1)^2 vertex heights start inside the shared texture.
    Heightmap texels: PF_B8G8R8A8, 4 bytes per texel in B, G, R, A order. The 16-bit height is R << 8 | G (B and A
      hold the normal); 32768 is zero height. World height = loc.z + (h - 32768) * scale.z / 128 (LANDSCAPE_ZSCALE =
      1/128 in LandscapeDataAccess.h).
    Texture payload (after the UTexture2D tagged properties): i32 UObject GUID flag, 2 + 2 bytes of strip flags
      (UTexture and UTexture2D), i32 bCooked, FName PixelFormat (8), i64 SkipOffset = 28 bytes; then SizeX i32,
      SizeY i32, PackedData u32, PixelFormatString FString, FirstMipToSerialize i32, NumMips i32; then the first mip:
      i32 bCooked, FByteBulkData header (u32 flags; element count + size on disk as i64 pair when flag 0x2000
      BULKDATA_Size64Bit else i32 pair; i64 offset in file), the payload inline when flag 0x40
      BULKDATA_ForceInlinePayload is set, otherwise at that offset in the .ubulk; then the mip's SizeX, SizeY i32.
      Only the top mip is decoded.

Gotchas
    ``height_cm`` returns None outside the landscape: callers must skip those points, never substitute -15 m.
    Component lookup is by exact base key, so a landscape with components of differing sizes is not supported.
"""

import sys, os, struct, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uasset import Asset


class Landscape:
    """Heightmap sampler for one cooked level.

    Attributes
        a           the ``Asset`` (uasset/uexp) of the level
        bulk        bytes of the .ubulk (b'' when absent)
        loc, scale  landscape actor location (cm) and scale (cm per quad in X/Y, Z factor) as 3-tuples
        comps       one dict per LandscapeComponent: ``base`` (quad coords), ``size`` (quads), ``tex`` (export
                    name), ``bias`` (U, V offset into the texture), ``scale`` (1/texW, 1/texH)
        by_base     ``{(baseX, baseY): comp}`` for lookup
        quads       quads per component side (taken from the first component)
        textures    cache ``{export name: (width, height, BGRA bytes)}`` filled by ``texture``
    """

    def __init__(self, base):
        """Load the level at ``base`` (path without extension) and collect its landscape components.

        Raises IndexError if the level has no ``RootComponent0`` export or no landscape components.
        """
        self.a = a = Asset(base + '.uasset')
        self.bulk = open(base + '.ubulk', 'rb').read() if os.path.exists(base + '.ubulk') else b''
        self.exp = a.exp
        root = self._props(self._export_index('RootComponent0'))
        loc = root.get('RelativeLocation', {'X': 0, 'Y': 0, 'Z': 0})
        sc = root.get('RelativeScale3D', {'X': 100, 'Y': 100, 'Z': 100})
        self.loc = (loc['X'], loc['Y'], loc['Z'])
        self.scale = (sc['X'], sc['Y'], sc['Z'])
        self.textures = {}
        self.comps = []
        for i, e in enumerate(a.exports):
            if (a.ref(e['cls']) or '').endswith('.LandscapeComponent'):
                p = self._props(i)
                # RelativeLocation of a component is its section base in quads (integers stored as floats).
                rl = p.get('RelativeLocation', {'X': 0, 'Y': 0})
                sb = (int(round(rl.get('X', 0))), int(round(rl.get('Y', 0))))
                hb = p.get('HeightmapScaleBias')
                tex = str(p.get('HeightmapTexture', '')).replace('EXPORT:', '')
                self.comps.append(
                    dict(
                        base=sb,
                        size=p.get('ComponentSizeQuads', 63),
                        tex=tex,
                        bias=(hb['Z'], hb['W']),
                        scale=(hb['X'], hb['Y']),
                    )
                )
        self.by_base = {c['base']: c for c in self.comps}
        self.quads = self.comps[0]['size']

    def _export_index(self, name):
        """Index of the first export named ``name`` (IndexError when absent)."""
        return [i for i, e in enumerate(self.a.exports) if e['name'] == name][0]

    def _props(self, i):
        """Tolerant tagged-property read of export ``i``.

        Like ``Asset.read_props`` but a value that fails to decode becomes None (the cursor still resyncs by tag
        size) and a broken tag ends the list. Static-array indices are ignored (last one wins). The dict also carries
        ``'__end'``: the uexp offset just after the terminating ``None`` tag, where the class's native payload (the
        texture data) begins.
        """
        r = self.a.export_reader(i)
        out = {}
        while True:
            try:
                t = self.a.read_tag(r)
                if t is None:
                    break
                s = r.p
                end = s + t['size']
                try:
                    v = self.a.read_value(r, t, end)
                except Exception:
                    v = None
                if t['type'] != 'BoolProperty':
                    r.p = end
                out[t['name']] = v
            except Exception:
                break
        out['__end'] = r.p
        return out

    def texture(self, name):
        """Decode (and cache) the top mip of the UTexture2D export ``name``.

        Returns ``(width, height, bytes)`` with 4 BGRA bytes per texel. Asserts the format is PF_B8G8R8A8 and the
        payload size matches width * height * 4 (layout in the module docstring).
        """
        if name in self.textures:
            return self.textures[name]
        i = self._export_index(name)
        p = self._props(i)
        pos = p['__end']
        b = self.exp
        pos += 4 + 2 + 2 + 4 + 8 + 8  # guid flag, 2x strip flags, bCooked, PixelFormat FName, SkipOffset
        # FTexturePlatformData::SerializeCooked: SizeX, SizeY, PackedData (slices + flags), format string, mip range.
        sx, sy, packed = struct.unpack_from('<iiI', b, pos)
        pos += 12
        (n,) = struct.unpack_from('<i', b, pos)
        pos += 4
        fmt = b[pos : pos + n].rstrip(b'\0').decode()
        pos += n
        first, nmips = struct.unpack_from('<ii', b, pos)
        pos += 8
        pos += 4  # per-mip bCooked
        # FByteBulkData of the first mip: flags, count/size (64-bit when 0x2000), offset, inline payload when 0x40.
        (flags,) = struct.unpack_from('<I', b, pos)
        pos += 4
        if flags & 0x2000:
            count, size = struct.unpack_from('<qq', b, pos)
            pos += 16
        else:
            count, size = struct.unpack_from('<ii', b, pos)
            pos += 8
        (off,) = struct.unpack_from('<q', b, pos)
        pos += 8
        if flags & 0x40:
            data = b[pos : pos + size]
            pos += size
        else:
            data = self.bulk[off : off + size]
        msx, msy = struct.unpack_from('<ii', b, pos)
        assert fmt == 'PF_B8G8R8A8' and msx * msy * 4 == len(data), (fmt, msx, msy, len(data), hex(flags))
        self.textures[name] = (msx, msy, data)
        return self.textures[name]

    def height_cm(self, x_cm, y_cm):
        """World height (cm) of the landscape at world (x, y) cm, bilinear.

        Converts world cm to landscape quad units via ``loc``/``scale``, finds the component whose base contains the
        point, reads the four surrounding vertex heights from its heightmap (texel offset from HeightmapScaleBias)
        and blends them bilinearly. Returns None when no component covers (x, y); texel indices are clamped to the
        texture so the last row/column of a component reuses its edge instead of reading past it.
        """
        lx = (x_cm - self.loc[0]) / self.scale[0]
        ly = (y_cm - self.loc[1]) / self.scale[1]
        q = self.quads
        cx, cy = int(lx // q), int(ly // q)
        c = self.by_base.get((cx * q, cy * q))
        if not c:
            return None
        w, h, data = self.texture(c['tex'])
        u0 = c['bias'][0] * w
        v0 = c['bias'][1] * h
        fx = lx - cx * q
        fy = ly - cy * q

        def px(i, j):
            """16-bit height of vertex (i, j) of the component: R (high byte) and G (low byte) of the BGRA texel."""
            i = min(max(int(u0 + i), 0), w - 1)
            j = min(max(int(v0 + j), 0), h - 1)
            o = (j * w + i) * 4
            return (data[o + 2] << 8) | data[o + 1]

        i0, j0 = int(fx), int(fy)
        tx, ty = fx - i0, fy - j0
        hgt = (px(i0, j0) * (1 - tx) + px(i0 + 1, j0) * tx) * (1 - ty) + (
            px(i0, j0 + 1) * (1 - tx) + px(i0 + 1, j0 + 1) * tx
        ) * ty
        # LANDSCAPE_ZSCALE = 1/128: 16-bit heights are centred on 32768 and scaled by the actor's Z scale.
        return self.loc[2] + (hgt - 32768) * self.scale[2] / 128.0


if __name__ == '__main__':
    base = sys.argv[1]
    L = Landscape(base)
    print('landscape loc', L.loc, 'scale', L.scale, 'components', len(L.comps), 'quads', L.quads)
    for x, y in (
        (0, 0),
        (10000, 0),
        (0, 10000),
        (-20000, 0),
        (30000, 20000),
        (-40000, -30000),
        (50000, 0),
        (0, -60000),
    ):
        print(f'  ground at ({x / 100:.0f} m, {y / 100:.0f} m): {L.height_cm(x, y)}')
    if len(sys.argv) > 2:
        from PIL import Image

        # 256 x 256 samples over +-1300 m, normalised to the height range; None (off-landscape) renders black.
        N = 256
        img = Image.new('L', (N, N))
        px_ = img.load()
        half = 1300 * 100
        hs = []
        for i in range(N):
            for j in range(N):
                x = -half + (i + 0.5) * 2 * half / N
                y = -half + (j + 0.5) * 2 * half / N
                hgt = L.height_cm(x, y)
                hs.append((i, j, hgt))
        vals = [h for _, _, h in hs if h is not None]
        lo, hi = min(vals), max(vals)
        for i, j, hgt in hs:
            px_[j, N - 1 - i] = 0 if hgt is None else int(255 * (hgt - lo) / max(1, hi - lo))
        img = img.resize((1024, 1024))
        img.save(sys.argv[2])
        print('height range cm', lo, hi, '->', sys.argv[2])
