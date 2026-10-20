"""Decode a UE4 landscape's heightmap textures from a cooked level (.umap/.uexp/.ubulk) into a world-height sampler."""
import sys, os, struct, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uasset import Asset

class Landscape:
    def __init__(self, base):
        self.a = a = Asset(base + '.uasset')
        self.bulk = open(base + '.ubulk', 'rb').read() if os.path.exists(base + '.ubulk') else b''
        self.exp = a.exp
        root = self._props(self._export_index('RootComponent0'))
        loc = root.get('RelativeLocation', {'X': 0, 'Y': 0, 'Z': 0}); sc = root.get('RelativeScale3D', {'X': 100, 'Y': 100, 'Z': 100})
        self.loc = (loc['X'], loc['Y'], loc['Z']); self.scale = (sc['X'], sc['Y'], sc['Z'])
        self.textures = {}; self.comps = []
        for i, e in enumerate(a.exports):
            if (a.ref(e['cls']) or '').endswith('.LandscapeComponent'):
                p = self._props(i)
                rl = p.get('RelativeLocation', {'X': 0, 'Y': 0}); sb = (int(round(rl.get('X', 0))), int(round(rl.get('Y', 0))))
                hb = p.get('HeightmapScaleBias'); tex = str(p.get('HeightmapTexture', '')).replace('EXPORT:', '')
                self.comps.append(dict(base=sb, size=p.get('ComponentSizeQuads', 63), tex=tex, bias=(hb['Z'], hb['W']), scale=(hb['X'], hb['Y'])))
        self.by_base = {c['base']: c for c in self.comps}
        self.quads = self.comps[0]['size']
    def _export_index(self, name): return [i for i, e in enumerate(self.a.exports) if e['name'] == name][0]
    def _props(self, i):
        r = self.a.export_reader(i); out = {}
        while True:
            try:
                t = self.a.read_tag(r)
                if t is None: break
                s = r.p; end = s + t['size']
                try: v = self.a.read_value(r, t, end)
                except Exception: v = None
                if t['type'] != 'BoolProperty': r.p = end
                out[t['name']] = v
            except Exception: break
        out['__end'] = r.p
        return out
    def texture(self, name):
        if name in self.textures: return self.textures[name]
        i = self._export_index(name); p = self._props(i); pos = p['__end']; b = self.exp
        pos += 4 + 2 + 2 + 4 + 8 + 8                    # guid flag, 2x strip flags, bCooked, PixelFormat FName, SkipOffset
        sx, sy, packed = struct.unpack_from('<iiI', b, pos); pos += 12
        n, = struct.unpack_from('<i', b, pos); pos += 4; fmt = b[pos:pos + n].rstrip(b'\0').decode(); pos += n
        first, nmips = struct.unpack_from('<ii', b, pos); pos += 8
        pos += 4                                          # per-mip bCooked
        flags, = struct.unpack_from('<I', b, pos); pos += 4
        if flags & 0x2000: count, size = struct.unpack_from('<qq', b, pos); pos += 16
        else: count, size = struct.unpack_from('<ii', b, pos); pos += 8
        off, = struct.unpack_from('<q', b, pos); pos += 8
        if flags & 0x40: data = b[pos:pos + size]; pos += size
        else: data = self.bulk[off:off + size]
        msx, msy = struct.unpack_from('<ii', b, pos)
        assert fmt == 'PF_B8G8R8A8' and msx * msy * 4 == len(data), (fmt, msx, msy, len(data), hex(flags))
        self.textures[name] = (msx, msy, data); return self.textures[name]
    def height_cm(self, x_cm, y_cm):
        """World height (cm) of the landscape at world (x, y) cm, bilinear."""
        lx = (x_cm - self.loc[0]) / self.scale[0]; ly = (y_cm - self.loc[1]) / self.scale[1]
        q = self.quads; cx, cy = int(lx // q), int(ly // q)
        c = self.by_base.get((cx * q, cy * q))
        if not c: return None
        w, h, data = self.texture(c['tex'])
        u0 = c['bias'][0] * w; v0 = c['bias'][1] * h
        fx = lx - cx * q; fy = ly - cy * q
        def px(i, j):
            i = min(max(int(u0 + i), 0), w - 1); j = min(max(int(v0 + j), 0), h - 1); o = (j * w + i) * 4
            return (data[o + 2] << 8) | data[o + 1]
        i0, j0 = int(fx), int(fy); tx, ty = fx - i0, fy - j0
        hgt = (px(i0, j0) * (1 - tx) + px(i0 + 1, j0) * tx) * (1 - ty) + (px(i0, j0 + 1) * (1 - tx) + px(i0 + 1, j0 + 1) * tx) * ty
        return self.loc[2] + (hgt - 32768) * self.scale[2] / 128.0

if __name__ == '__main__':
    base = sys.argv[1]
    L = Landscape(base)
    print('landscape loc', L.loc, 'scale', L.scale, 'components', len(L.comps), 'quads', L.quads)
    for (x, y) in ((0, 0), (10000, 0), (0, 10000), (-20000, 0), (30000, 20000), (-40000, -30000), (50000, 0), (0, -60000)):
        print(f'  ground at ({x/100:.0f} m, {y/100:.0f} m): {L.height_cm(x, y)}')
    if len(sys.argv) > 2:
        from PIL import Image
        N = 256; img = Image.new('L', (N, N)); px_ = img.load(); half = 1300 * 100
        hs = []
        for i in range(N):
            for j in range(N):
                x = -half + (i + 0.5) * 2 * half / N; y = -half + (j + 0.5) * 2 * half / N
                hgt = L.height_cm(x, y); hs.append((i, j, hgt))
        vals = [h for _, _, h in hs if h is not None]; lo, hi = min(vals), max(vals)
        for i, j, hgt in hs: px_[j, N - 1 - i] = 0 if hgt is None else int(255 * (hgt - lo) / max(1, hi - lo))
        img = img.resize((1024, 1024)); img.save(sys.argv[2]); print('height range cm', lo, hi, '->', sys.argv[2])
