"""Minimal UE4 (pak v11, unencrypted, Zlib) reader: list and extract files."""

import struct, zlib, os, sys, glob

MAGIC = 0x5A6F12E1


def read_fstring(buf, pos):
    (n,) = struct.unpack_from('<i', buf, pos)
    pos += 4
    if n < 0:
        s = buf[pos : pos + (-n) * 2].decode('utf-16-le').rstrip('\0')
        pos += (-n) * 2
    else:
        s = buf[pos : pos + n].decode('latin-1').rstrip('\0')
        pos += n
    return s, pos


class Pak:
    def __init__(self, path):
        self.path = path
        self.fh = open(path, 'rb')
        sz = os.path.getsize(path)
        self.fh.seek(sz - 221)
        foot = self.fh.read(221)
        magic, ver = struct.unpack_from('<II', foot, 17)
        assert magic == MAGIC, path
        self.version = ver
        off, isz = struct.unpack_from('<qq', foot, 25)
        self.methods = [''] + [foot[61 + i * 32 : 61 + (i + 1) * 32].split(b'\0')[0].decode() for i in range(5)]
        self.fh.seek(off)
        idx = self.fh.read(isz)
        p = 0
        self.mount, p = read_fstring(idx, p)
        (self.count,) = struct.unpack_from('<i', idx, p)
        p += 4
        p += 8  # path hash seed
        (has_ph,) = struct.unpack_from('<i', idx, p)
        p += 4
        if has_ph:
            p += 8 + 8 + 20
        (has_fdi,) = struct.unpack_from('<i', idx, p)
        p += 4
        fdi_off = fdi_size = 0
        if has_fdi:
            fdi_off, fdi_size = struct.unpack_from('<qq', idx, p)
            p += 16 + 20
        (n_enc,) = struct.unpack_from('<i', idx, p)
        p += 4
        self.encoded = idx[p : p + n_enc]
        p += n_enc
        self.files = {}
        if has_fdi:
            self.fh.seek(fdi_off)
            fdi = self.fh.read(fdi_size)
            q = 0
            (ndirs,) = struct.unpack_from('<i', fdi, q)
            q += 4
            for _ in range(ndirs):
                d, q = read_fstring(fdi, q)
                (nf,) = struct.unpack_from('<i', fdi, q)
                q += 4
                for _ in range(nf):
                    f, q = read_fstring(fdi, q)
                    (eo,) = struct.unpack_from('<i', fdi, q)
                    q += 4
                    self.files[(self.mount + d + f).replace('//', '/')] = eo

    def entry(self, eo):
        b = self.encoded
        p = eo
        (flags,) = struct.unpack_from('<I', b, p)
        p += 4
        comp_idx = (flags >> 23) & 0x3F
        encrypted = bool(flags & (1 << 22))
        nblocks = (flags >> 6) & 0xFFFF
        bsize = flags & 0x3F
        if bsize == 0x3F:
            (bsize,) = struct.unpack_from('<I', b, p)
            p += 4
        else:
            bsize <<= 11
        if flags & (1 << 31):
            (off,) = struct.unpack_from('<I', b, p)
            p += 4
        else:
            (off,) = struct.unpack_from('<q', b, p)
            p += 8
        if flags & (1 << 30):
            (usize,) = struct.unpack_from('<I', b, p)
            p += 4
        else:
            (usize,) = struct.unpack_from('<q', b, p)
            p += 8
        if comp_idx:
            if flags & (1 << 29):
                (csize,) = struct.unpack_from('<I', b, p)
                p += 4
            else:
                (csize,) = struct.unpack_from('<q', b, p)
                p += 8
        else:
            csize = usize
        blocks = []
        if comp_idx and nblocks:
            if nblocks == 1 and not encrypted:
                pass
            for i in range(nblocks):
                if flags & (1 << 31):
                    (bs,) = struct.unpack_from('<I', b, p)
                    p += 4
                else:
                    (bs,) = struct.unpack_from('<q', b, p)
                    p += 8
                blocks.append(bs)
        return dict(
            off=off,
            usize=usize,
            csize=csize,
            comp=self.methods[comp_idx],
            enc=encrypted,
            nblocks=nblocks,
            bsize=bsize,
            blocks=blocks,
        )

    def read(self, name):
        e = self.entry(self.files[name])
        # entry header on disk: offset(8) size(8) usize(8) compidx(4) hash(20) [+blocks] [enc flag 1] [blocksize 4]
        hdr = 8 + 8 + 8 + 4 + 20
        if e['comp']:
            hdr += 4 + e['nblocks'] * 16
        hdr += 1 + 4
        base = e['off'] + hdr
        if not e['comp']:
            self.fh.seek(base)
            return self.fh.read(e['usize'])
        out = bytearray()
        pos = base
        sizes = e['blocks'] or [e['csize']]
        for bs in sizes:
            self.fh.seek(pos)
            out += zlib.decompress(self.fh.read(bs))
            pos += bs
        return bytes(out[: e['usize']])


if __name__ == '__main__':
    pakdir = sys.argv[1]
    out = sys.argv[2]
    with open(out, 'w') as fo:
        for p in sorted(glob.glob(os.path.join(pakdir, '*.pak'))):
            try:
                pk = Pak(p)
            except Exception as ex:
                print('ERR', p, ex)
                continue
            for f in pk.files:
                fo.write(f'{os.path.basename(p)}\t{f}\n')
            print(os.path.basename(p), len(pk.files), 'files, methods', pk.methods[1:3])
