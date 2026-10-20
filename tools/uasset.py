"""Small UE4.27 cooked .uasset/.uexp reader: names, imports, exports, tagged properties, DataTable rows."""
import struct, json, sys, os

NATIVE = {
    'Vector': ('fff', ['X','Y','Z']), 'Rotator': ('fff', ['Pitch','Yaw','Roll']), 'Quat': ('ffff', ['X','Y','Z','W']),
    'Vector2D': ('ff', ['X','Y']), 'Vector4': ('ffff', ['X','Y','Z','W']), 'LinearColor': ('ffff', ['R','G','B','A']),
    'Color': ('BBBB', ['B','G','R','A']), 'IntPoint': ('ii', ['X','Y']), 'Guid': ('IIII', ['A','B','C','D']),
    'DateTime': ('q', ['Ticks']), 'Timespan': ('q', ['Ticks']), 'FrameNumber': ('i', ['V']),
}

class R:
    def __init__(self, b, p=0): self.b = b; self.p = p
    def u(self, fmt):
        v = struct.unpack_from('<' + fmt, self.b, self.p); self.p += struct.calcsize('<' + fmt); return v if len(v) > 1 else v[0]
    def fstr(self):
        n = self.u('i')
        if n == 0: return ''
        if n < 0: s = self.b[self.p:self.p + (-n) * 2].decode('utf-16-le')[:-1]; self.p += (-n) * 2
        else: s = self.b[self.p:self.p + n].decode('latin-1')[:-1]; self.p += n
        return s

class Asset:
    def __init__(self, path):
        base = path[:-7] if path.endswith('.uasset') else path
        self.hdr = open(base + '.uasset', 'rb').read()
        self.exp = open(base + '.uexp', 'rb').read() if os.path.exists(base + '.uexp') else b''
        r = R(self.hdr)
        assert r.u('I') == 0x9E2A83C1
        legacy = r.u('i'); assert legacy < 0
        if legacy != -4: r.u('i')
        self.ver = r.u('i'); r.u('i')
        if legacy <= -2:
            n = r.u('i'); r.p += 20 * n
        self.total_header = r.u('i'); r.fstr(); self.flags = r.u('I')
        name_count, name_off = r.u('ii')
        if not (self.flags & 0x80000000) and (self.ver == 0 or self.ver >= 516): r.fstr()
        r.u('ii')  # gatherable text
        exp_count, exp_off = r.u('ii'); imp_count, imp_off = r.u('ii')
        # names
        r2 = R(self.hdr, name_off); self.names = []
        for _ in range(name_count): self.names.append(r2.fstr()); r2.p += 4
        r2 = R(self.hdr, imp_off); self.imports = []
        for _ in range(imp_count):
            cp = self.fname(r2); cn = self.fname(r2); outer = r2.u('i'); on = self.fname(r2)
            self.imports.append(dict(class_package=cp, class_name=cn, outer=outer, name=on))
        r2 = R(self.hdr, exp_off); self.exports = []
        for _ in range(exp_count):
            cls, sup, tmpl, outer = r2.u('iiii'); on = self.fname(r2); r2.u('I'); ssize, soff = r2.u('qq'); r2.p += 104 - 44
            self.exports.append(dict(cls=cls, outer=outer, name=on, size=ssize, off=soff))
    def fname(self, r):
        i, n = r.u('ii'); s = self.names[i] if 0 <= i < len(self.names) else f'<bad {i}>'
        return s if n == 0 else f'{s}_{n-1}'
    def ref(self, idx):
        if idx == 0: return None
        if idx < 0:
            im = self.imports[-idx - 1]; out = self.ref(im['outer'])
            return (out + '.' if out else '') + im['name']
        return 'EXPORT:' + self.exports[idx - 1]['name']
    def export_reader(self, i=0):
        e = self.exports[i]; return R(self.exp, e['off'] - self.total_header)

    def read_tag(self, r):
        name = self.fname(r)
        if name == 'None': return None
        t = dict(name=name, type=self.fname(r)); t['size'], t['index'] = r.u('ii')
        ty = t['type']
        if ty == 'StructProperty': t['struct'] = self.fname(r); r.p += 16
        elif ty == 'BoolProperty': t['bool'] = r.u('B')
        elif ty in ('ByteProperty', 'EnumProperty'): t['enum'] = self.fname(r)
        elif ty in ('ArrayProperty', 'SetProperty'): t['inner'] = self.fname(r)
        elif ty == 'MapProperty': t['inner'] = self.fname(r); t['value'] = self.fname(r)
        if r.u('B'): r.p += 16
        return t

    def read_value(self, r, t, end):
        ty = t['type']
        if ty == 'BoolProperty': return bool(t['bool'])
        if ty == 'FloatProperty': return r.u('f')
        if ty == 'IntProperty': return r.u('i')
        if ty == 'UInt32Property': return r.u('I')
        if ty == 'Int64Property': return r.u('q')
        if ty == 'ByteProperty': return self.fname(r) if t.get('enum', 'None') != 'None' else r.u('B')
        if ty in ('EnumProperty', 'NameProperty'): return self.fname(r)
        if ty == 'StrProperty': return r.fstr()
        if ty in ('ObjectProperty', 'ClassProperty', 'InterfaceProperty'): return self.ref(r.u('i'))
        if ty in ('SoftObjectProperty', 'SoftClassProperty', 'AssetObjectProperty'):
            p = self.fname(r); sub = r.fstr(); return p + (':' + sub if sub else '')
        if ty == 'TextProperty':
            flags = r.u('I'); hist = r.u('b')
            if hist == -1:
                if r.u('i'): return r.fstr()
                return ''
            if hist == 0: r.fstr(); r.fstr(); return r.fstr()
            r.p = end; return '<text>'
        if ty == 'StructProperty': return self.read_struct(r, t['struct'], end)
        if ty == 'ArrayProperty':
            n = r.u('i'); inner = t['inner']; out = []
            if inner == 'StructProperty':
                it = self.read_tag(r)
                for _ in range(n): out.append(self.read_struct(r, it['struct'], None))
            else:
                for _ in range(n): out.append(self.read_value(r, dict(type=inner, enum='x'), None))
            return out
        r.p = end; return f'<{ty}>'

    def read_struct(self, r, sname, end):
        if sname in NATIVE:
            fmt, keys = NATIVE[sname]; vals = r.u(fmt); return dict(zip(keys, vals if isinstance(vals, tuple) else (vals,)))
        if sname == 'SoftObjectPath': p = self.fname(r); sub = r.fstr(); return p + (':' + sub if sub else '')
        return self.read_props(r)

    def read_props(self, r):
        out = {}
        while True:
            t = self.read_tag(r)
            if t is None: return out
            start = r.p; end = start + t['size']
            v = self.read_value(r, t, end)
            if t['type'] != 'BoolProperty': r.p = end
            key = t['name'] if t['index'] == 0 else f"{t['name']}[{t['index']}]"
            out[key] = v

    def datatable(self):
        r = self.export_reader(0); props = self.read_props(r)
        r.u('i')  # extra int (object GUID marker / none)
        n = r.u('i'); rows = {}
        for _ in range(n):
            rn = self.fname(r); rows[rn] = self.read_props(r)
        return props, rows

if __name__ == '__main__':
    a = Asset(sys.argv[1])
    print('ver', a.ver, 'names', len(a.names), 'imports', len(a.imports), 'exports', [(e['name'], a.ref(e['cls'])) for e in a.exports])
    if len(sys.argv) > 2 and sys.argv[2] == 'dt':
        props, rows = a.datatable(); print(json.dumps(props, indent=1)[:600]); print(len(rows), 'rows')
        json.dump(rows, open(sys.argv[3], 'w'), indent=1); print(json.dumps(list(rows.items())[:3], indent=1))
    else:
        r = a.export_reader(0); print(json.dumps(a.read_props(r), indent=1)[:3000])
