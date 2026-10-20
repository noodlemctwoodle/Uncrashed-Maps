"""Minimal UE4 (pak v11, unencrypted, Zlib) reader: list and extract files.

Purpose
    Open one of the game's ``.pak`` archives, decode its directory index and read single files out of it. This is the
    only pak code the repo needs: Uncrashed ships unencrypted version-11 paks whose entries are either stored or
    Zlib-compressed (``methods`` is ``['', 'Zlib', '', '', '', '']`` for every pak on this Mac).

Usage
    python3 tools/pakread.py <pak dir> <listing.txt>   -> one "<pak>\\t<path>" line per file, a summary per pak
    from pakread import Pak; Pak(path).read(name)       -> bytes (see tools/pakextract.py, build_catalog.py)

File-format facts the code relies on (UE 4.27 FPakInfo / FPakFile, pak version 11)
    Footer: the last 221 bytes of the file are the FPakInfo:
        0   EncryptionKeyGuid (16)    16  bEncryptedIndex (1)      17  Magic 0x5A6F12E1 (u32)
        21  Version (u32, 11)         25  IndexOffset (i64)        33  IndexSize (i64)
        41  IndexHash (20, SHA1)      61  five compression-method names, 32 ANSI chars each (= 221)
      Method index 0 means "stored", so ``methods`` is prefixed with an empty string.
    Primary index (at IndexOffset, IndexSize bytes): MountPoint FString, NumEntries i32, PathHashSeed u64,
      bHasPathHashIndex i32 [+ offset i64, size i64, hash 20], bHasFullDirectoryIndex i32 [+ offset i64, size i64,
      hash 20], EncodedPakEntriesSize i32 and the encoded entries blob. Only the full directory index is used to
      resolve names: it is ``{dir: {file: i32 offset into the encoded blob}}`` with FString keys.
    FString: i32 length including the NUL; negative length means UTF-16LE with |n| code units.
    Encoded entry (FPakFile::DecodePakEntry): one u32 of flags followed by variable-width fields, see ``Pak.entry``.
    On-disk entry header (FPakEntry::Serialize) precedes the data at ``off``: Offset i64 (stored as 0, i.e. relative,
      confirmed on these paks), Size i64, UncompressedSize i64, CompressionMethodIndex u32, Hash 20, and when
      compressed an i32 block count plus 16 bytes (start i64, end i64) per block, then Flags u8 and
      CompressionBlockSize u32. ``Pak.read`` only needs its length to find the first data byte.

Gotchas
    Everything is read with little-endian struct formats. Encryption is detected but never decrypted. The
    block-size loop in ``entry`` has a known quirk for single-block entries (see its docstring).
"""

import struct, zlib, os, sys, glob

# FPakInfo::PakFile_Magic: identifies a valid footer (any pak version).
MAGIC = 0x5A6F12E1


def read_fstring(buf, pos):
    """Decode a UE4 FString at ``pos`` in ``buf``.

    Layout: i32 length that counts the terminating NUL; a negative length means the payload is UTF-16LE with
    ``-length`` code units, otherwise ``length`` single bytes (decoded as Latin-1, which never fails).

    Returns ``(string without trailing NULs, position after the string)``.
    """
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
    """One open ``.pak`` archive: footer, compression methods and the ``{path: encoded-entry offset}`` directory.

    Attributes
        path, fh        the file and its open binary handle (kept open for ``read``)
        version         pak version from the footer (11 for this game)
        methods         six compression-method names, index 0 = stored ('')
        mount           mount point string, e.g. ``../../../``; file keys are ``mount + dir + file``
        count           number of entries declared by the index
        encoded         the encoded pak-entries blob (bytes); ``files`` values are offsets into it
        files           ``{full path: offset into encoded}`` for every file in the full directory index
    """

    def __init__(self, path):
        """Parse the footer and the full directory index of the pak at ``path``.

        Raises AssertionError when the footer magic does not match (wrong file or unsupported layout). Paks without a
        full directory index (``has_fdi == 0``) yield an empty ``files`` dict.
        """
        self.path = path
        self.fh = open(path, 'rb')
        sz = os.path.getsize(path)
        # The v11 FPakInfo footer is a fixed 221 bytes at the end of the file (field offsets in the module docstring).
        self.fh.seek(sz - 221)
        foot = self.fh.read(221)
        magic, ver = struct.unpack_from('<II', foot, 17)
        assert magic == MAGIC, path
        self.version = ver
        off, isz = struct.unpack_from('<qq', foot, 25)
        # Five 32-byte NUL-padded ANSI method names start at byte 61; prepend '' so index 0 means "not compressed".
        self.methods = [''] + [foot[61 + i * 32 : 61 + (i + 1) * 32].split(b'\0')[0].decode() for i in range(5)]
        self.fh.seek(off)
        idx = self.fh.read(isz)
        p = 0
        # Primary index header (FPakFile::LoadIndex, v10+): mount point, entry count, path-hash seed, then two
        # optional secondary-index descriptors (offset i64 + size i64 + SHA1 20) and the encoded entries blob.
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
            # Full directory index: i32 dir count; per dir an FString name and i32 file count; per file an FString name
            # and the i32 offset of its encoded entry. Directory names already end in '/', so '//' is collapsed.
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
        """Decode the encoded pak entry that starts at offset ``eo`` in ``self.encoded``.

        Layout (FPakFile::DecodePakEntry): a u32 flags word
            bit 31  Offset fits in 32 bits        bit 30  UncompressedSize fits in 32 bits
            bit 29  CompressedSize fits in 32 bits  bits 23-28  compression method index (6 bits)
            bit 22  encrypted                      bits 6-21  compression block count (16 bits)
            bits 0-5  block size in 2 KiB units (<< 11); the escape value 0x3F means an explicit u32 follows
        then Offset (u32/i64 by bit 31), UncompressedSize (u32/i64 by bit 30), CompressedSize (u32/i64 by bit 29,
        only when compressed; stored entries use the uncompressed size) and the per-block compressed sizes.

        Returns a dict: ``off`` (absolute file offset of the on-disk entry header), ``usize``, ``csize`` (bytes),
        ``comp`` (method name or ''), ``enc`` (bool), ``nblocks``, ``bsize`` (block size in bytes) and ``blocks``
        (list of compressed block sizes).

        Gotcha (empirical, measured on every pak of this game): UE stores NO block size for a single unencrypted
        block (the ``pass`` branch), yet the loop below still reads one, so ``blocks[0]`` is then the next entry's
        flags word (0xE0000000-ish) and the last entry of a pak raises ``struct.error``. ``read`` tolerates the
        bogus size because ``zlib.decompress`` ignores trailing bytes. Multi-block sizes always sum to ``csize``.
        The 4-vs-8-byte choice for block sizes follows bit 31; every offset in these paks is below 4 GiB, so the
        8-byte branch has never been exercised here.
        """
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
        """Return the uncompressed bytes of the file ``name`` (a key of ``self.files``).

        Skips the on-disk FPakEntry header that precedes the payload, then either copies ``usize`` raw bytes or
        Zlib-inflates each compressed block in turn (blocks are stored back to back). Any compression method other
        than Zlib would reach ``zlib.decompress`` and fail; the game only uses Zlib. Encrypted entries are not
        handled. Raises KeyError for unknown names.
        """
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
        # A single-block entry carries a bogus size (see ``entry``); the fallback to csize is only taken when the
        # list is empty. Trailing bytes beyond the deflate stream are ignored by zlib, and the output is clipped.
        sizes = e['blocks'] or [e['csize']]
        for bs in sizes:
            self.fh.seek(pos)
            out += zlib.decompress(self.fh.read(bs))
            pos += bs
        return bytes(out[: e['usize']])


if __name__ == '__main__':
    # CLI: list every file of every pak in a directory into one tab-separated text file.
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
