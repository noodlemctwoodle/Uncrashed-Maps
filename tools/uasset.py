"""Small UE4.27 cooked .uasset/.uexp reader: names, imports, exports, tagged properties, DataTable rows.

Purpose
    Enough of the cooked package format to pull values out of the game's assets without the engine: the name table,
    import and export tables, the tagged-property list of any export (``read_props``) and the rows of a UDataTable
    (``datatable``). It is used by tools/build_catalog.py and tools/bounds_fix.py (``ExtendedBounds`` of static
    meshes, StaticMeshComponent transforms of blueprints), tools/landscape.py (landscape components and textures) and
    tools/build_index.py (enum display names).

Usage
    python3 tools/uasset.py <file.uasset>                 -> header summary and the first export's properties
    python3 tools/uasset.py <file.uasset> dt <rows.json>  -> dumps the DataTable rows (data/dt_assets.json came from
                                                             DT_MapEditorAssets this way)
    a = Asset(path); a.read_props(a.export_reader(i))     -> dict of the i-th export's properties

Inputs/outputs
    ``path`` names the ``.uasset`` (the header: summary, names, imports, exports); the ``.uexp`` next to it holds the
    export payloads and is read when present. Values come back as plain Python types: numbers, strings, dicts for
    structs, lists for arrays, ``None``/``'EXPORT:<name>'``/``'<outer>.<name>'`` for object references.

File-format facts the code relies on (FPackageFileSummary and friends, UE 4.27, cooked)
    Summary: Tag 0x9E2A83C1; LegacyFileVersion i32 (negative; -4 is the only value without the LegacyUE3Version i32
      that follows); FileVersionUE4 i32 (0 = "unversioned" cooked package); FileVersionLicenseeUE4 i32; for legacy
      <= -2 a custom-version array of i32 count + 20 bytes each (GUID 16 + version 4); TotalHeaderSize i32;
      FolderName FString; PackageFlags u32; NameCount/NameOffset; LocalizationId FString only when
      PKG_FilterEditorOnly (0x80000000) is clear and the version is 0 or >= 516; GatherableText count/offset;
      ExportCount/ExportOffset; ImportCount/ImportOffset. Later summary fields are not needed.
    Names: FString followed by two u16 hashes (4 bytes skipped per entry).
    Imports: ClassPackage FName, ClassName FName, OuterIndex i32, ObjectName FName (28 bytes each).
    Exports: ClassIndex, SuperIndex, TemplateIndex, OuterIndex (i32 x4), ObjectName FName, ObjectFlags u32,
      SerialSize i64, SerialOffset i64 = 44 bytes read, and the record is 104 bytes, so 60 are skipped
      (bForcedExport, bNotForClient, bNotForServer, PackageGuid, PackageFlags, bNotAlwaysLoadedForEditorGame,
      bIsAsset and the five dependency i32s).
    FName: i32 index into the name table + i32 number; number 0 is the plain name, n > 0 renders as ``Name_{n-1}``.
    Package index: 0 = null, negative = import ``-i - 1``, positive = export ``i - 1``.
    Export payloads: SerialOffset counts from the start of the package including the header, and cooked packages
      split the payloads into the ``.uexp``, so the uexp position is ``SerialOffset - TotalHeaderSize``.
    FPropertyTag: Name FName (``None`` ends a property list), Type FName, Size i32, ArrayIndex i32, then per type:
      StructProperty adds StructName FName + 16-byte StructGuid; BoolProperty carries its u8 value in the tag (Size
      is 0, nothing follows); ByteProperty/EnumProperty add EnumName FName; ArrayProperty/SetProperty add InnerType
      FName; MapProperty adds InnerType + ValueType FNames. A u8 HasPropertyGuid flag ends the tag, followed by a
      16-byte GUID when set. ``Size`` bytes of payload follow, which ``read_props`` uses to resync after each value.
    Native structs (``NATIVE``) are serialised as raw fields without tags; everything else is a nested tag list.
    UDataTable: the object's own properties, an i32 (the UObject GUID flag, 0 here), i32 row count, then per row
      RowName FName + the row struct's tagged properties.

Gotchas
    Only the property types the game's tables use are decoded; unknown types return ``'<Type>'`` and are skipped by
    size. Map/Set payloads are skipped the same way. Array elements of ByteProperty are always read as FNames.
"""

import struct, json, sys, os

# Structs UE serialises natively (no tags): struct format string and the field names in serialisation order.
# FColor is stored BGRA; FGuid is four u32; FDateTime/FTimespan are i64 ticks.
NATIVE = {
    'Vector': ('fff', ['X', 'Y', 'Z']),
    'Rotator': ('fff', ['Pitch', 'Yaw', 'Roll']),
    'Quat': ('ffff', ['X', 'Y', 'Z', 'W']),
    'Vector2D': ('ff', ['X', 'Y']),
    'Vector4': ('ffff', ['X', 'Y', 'Z', 'W']),
    'LinearColor': ('ffff', ['R', 'G', 'B', 'A']),
    'Color': ('BBBB', ['B', 'G', 'R', 'A']),
    'IntPoint': ('ii', ['X', 'Y']),
    'Guid': ('IIII', ['A', 'B', 'C', 'D']),
    'DateTime': ('q', ['Ticks']),
    'Timespan': ('q', ['Ticks']),
    'FrameNumber': ('i', ['V']),
}


class R:
    """Little-endian cursor over a bytes buffer: ``b`` is the data, ``p`` the current position."""

    def __init__(self, b, p=0):
        """Start reading ``b`` at byte offset ``p``."""
        self.b = b
        self.p = p

    def u(self, fmt):
        """Unpack ``struct`` format ``fmt`` (little-endian prefix added) and advance.

        Returns a single value for one-field formats, else the tuple.
        """
        v = struct.unpack_from('<' + fmt, self.b, self.p)
        self.p += struct.calcsize('<' + fmt)
        return v if len(v) > 1 else v[0]

    def fstr(self):
        """Read an FString: i32 length including the NUL; negative = UTF-16LE with |n| code units, else Latin-1.

        Returns the string without its terminator ('' for a zero length).
        """
        n = self.u('i')
        if n == 0:
            return ''
        if n < 0:
            s = self.b[self.p : self.p + (-n) * 2].decode('utf-16-le')[:-1]
            self.p += (-n) * 2
        else:
            s = self.b[self.p : self.p + n].decode('latin-1')[:-1]
            self.p += n
        return s


class Asset:
    """A cooked package: ``hdr`` (.uasset bytes), ``exp`` (.uexp bytes), ``names``, ``imports``, ``exports``.

    ``imports`` are dicts ``class_package, class_name, outer (package index), name``; ``exports`` are dicts
    ``cls, outer (package indices), name, size, off`` (``off`` is the SerialOffset, see ``export_reader``).
    ``ver`` is FileVersionUE4 (0 for unversioned cooked packages), ``flags`` the PackageFlags, ``total_header`` the
    header size used to map export offsets into the .uexp.
    """

    def __init__(self, path):
        """Parse the summary, name table, import table and export table of ``path`` (``.uasset`` or its stem).

        Raises AssertionError on a bad package tag or a non-negative legacy version.
        """
        base = path[:-7] if path.endswith('.uasset') else path
        self.hdr = open(base + '.uasset', 'rb').read()
        self.exp = open(base + '.uexp', 'rb').read() if os.path.exists(base + '.uexp') else b''
        r = R(self.hdr)
        # FPackageFileSummary (field order in the module docstring).
        assert r.u('I') == 0x9E2A83C1
        legacy = r.u('i')
        assert legacy < 0
        if legacy != -4:
            r.u('i')
        self.ver = r.u('i')
        r.u('i')
        if legacy <= -2:
            n = r.u('i')
            r.p += 20 * n
        self.total_header = r.u('i')
        r.fstr()
        self.flags = r.u('I')
        name_count, name_off = r.u('ii')
        if not (self.flags & 0x80000000) and (self.ver == 0 or self.ver >= 516):
            r.fstr()
        r.u('ii')  # gatherable text
        exp_count, exp_off = r.u('ii')
        imp_count, imp_off = r.u('ii')
        # names
        r2 = R(self.hdr, name_off)
        self.names = []
        for _ in range(name_count):
            self.names.append(r2.fstr())
            r2.p += 4
        r2 = R(self.hdr, imp_off)
        self.imports = []
        for _ in range(imp_count):
            cp = self.fname(r2)
            cn = self.fname(r2)
            outer = r2.u('i')
            on = self.fname(r2)
            self.imports.append(dict(class_package=cp, class_name=cn, outer=outer, name=on))
        r2 = R(self.hdr, exp_off)
        self.exports = []
        for _ in range(exp_count):
            # FObjectExport: 44 bytes of fields we keep, then skip to the 104-byte record stride.
            cls, sup, tmpl, outer = r2.u('iiii')
            on = self.fname(r2)
            r2.u('I')
            ssize, soff = r2.u('qq')
            r2.p += 104 - 44
            self.exports.append(dict(cls=cls, outer=outer, name=on, size=ssize, off=soff))

    def fname(self, r):
        """Read an FName (name index i32 + number i32) from cursor ``r``.

        Returns the plain name for number 0, ``'{name}_{number-1}'`` otherwise, or ``'<bad i>'`` for an index outside
        the name table.
        """
        i, n = r.u('ii')
        s = self.names[i] if 0 <= i < len(self.names) else f'<bad {i}>'
        return s if n == 0 else f'{s}_{n - 1}'

    def ref(self, idx):
        """Resolve a package index to a readable path.

        0 -> None; negative -> the import chain joined with dots (e.g. ``/Script/Engine.StaticMesh``), following
        ``outer`` recursively; positive -> ``'EXPORT:<name>'`` for the export (outer not expanded).
        """
        if idx == 0:
            return None
        if idx < 0:
            im = self.imports[-idx - 1]
            out = self.ref(im['outer'])
            return (out + '.' if out else '') + im['name']
        return 'EXPORT:' + self.exports[idx - 1]['name']

    def export_reader(self, i=0):
        """Cursor positioned at the start of export ``i``'s payload inside the .uexp.

        Cooked SerialOffsets include the header, which lives in the .uasset, hence ``off - total_header``.
        """
        e = self.exports[i]
        return R(self.exp, e['off'] - self.total_header)

    def read_tag(self, r):
        """Read one FPropertyTag from ``r``.

        Returns None at the ``None`` terminator, else a dict with ``name``, ``type``, ``size`` (payload bytes),
        ``index`` (static-array index) and the type extras: ``struct`` (StructProperty), ``bool`` (the value itself
        for BoolProperty), ``enum`` (Byte/EnumProperty), ``inner`` (Array/Set/Map) and ``value`` (Map). The optional
        property GUID is skipped. The cursor is left at the first payload byte.
        """
        name = self.fname(r)
        if name == 'None':
            return None
        t = dict(name=name, type=self.fname(r))
        t['size'], t['index'] = r.u('ii')
        ty = t['type']
        if ty == 'StructProperty':
            t['struct'] = self.fname(r)
            r.p += 16
        elif ty == 'BoolProperty':
            t['bool'] = r.u('B')
        elif ty in ('ByteProperty', 'EnumProperty'):
            t['enum'] = self.fname(r)
        elif ty in ('ArrayProperty', 'SetProperty'):
            t['inner'] = self.fname(r)
        elif ty == 'MapProperty':
            t['inner'] = self.fname(r)
            t['value'] = self.fname(r)
        if r.u('B'):
            r.p += 16
        return t

    def read_value(self, r, t, end):
        """Decode the payload of tag ``t`` from ``r``; ``end`` is the payload end offset (None inside arrays).

        Encodings: Bool comes from the tag; Float/Int/UInt32/Int64 are raw; ByteProperty is an FName when the tag
        names an enum (``'None'`` means a plain u8); Enum/Name are FNames; Str is an FString; Object/Class/Interface
        are package indices resolved with ``ref``; Soft* references are FSoftObjectPath (FName path + FString
        sub-path, joined with ':'); Text is u32 flags + i8 history type, where -1 is a culture-invariant string
        (i32 has-string + FString) and 0 is Base (namespace, key, source FStrings; the source is returned), any other
        history is skipped to ``end`` as ``'<text>'``; Struct defers to ``read_struct``; Array is i32 count followed,
        for struct elements, by one inner tag and then untagged structs, or for other element types by raw values
        (``enum='x'`` forces FName decoding for byte elements). Unknown types skip to ``end`` and return ``'<Type>'``.
        """
        ty = t['type']
        if ty == 'BoolProperty':
            return bool(t['bool'])
        if ty == 'FloatProperty':
            return r.u('f')
        if ty == 'IntProperty':
            return r.u('i')
        if ty == 'UInt32Property':
            return r.u('I')
        if ty == 'Int64Property':
            return r.u('q')
        if ty == 'ByteProperty':
            return self.fname(r) if t.get('enum', 'None') != 'None' else r.u('B')
        if ty in ('EnumProperty', 'NameProperty'):
            return self.fname(r)
        if ty == 'StrProperty':
            return r.fstr()
        if ty in ('ObjectProperty', 'ClassProperty', 'InterfaceProperty'):
            return self.ref(r.u('i'))
        if ty in ('SoftObjectProperty', 'SoftClassProperty', 'AssetObjectProperty'):
            p = self.fname(r)
            sub = r.fstr()
            return p + (':' + sub if sub else '')
        if ty == 'TextProperty':
            # FText: u32 flags, i8 history type; -1 = None/culture invariant, 0 = Base (namespace, key, source).
            flags = r.u('I')
            hist = r.u('b')
            if hist == -1:
                if r.u('i'):
                    return r.fstr()
                return ''
            if hist == 0:
                r.fstr()
                r.fstr()
                return r.fstr()
            r.p = end
            return '<text>'
        if ty == 'StructProperty':
            return self.read_struct(r, t['struct'], end)
        if ty == 'ArrayProperty':
            # TArray: i32 count; struct arrays carry one FPropertyTag for the element type before the elements.
            n = r.u('i')
            inner = t['inner']
            out = []
            if inner == 'StructProperty':
                it = self.read_tag(r)
                for _ in range(n):
                    out.append(self.read_struct(r, it['struct'], None))
            else:
                for _ in range(n):
                    out.append(self.read_value(r, dict(type=inner, enum='x'), None))
            return out
        r.p = end
        return f'<{ty}>'

    def read_struct(self, r, sname, end):
        """Decode a struct value named ``sname``: a ``NATIVE`` raw layout, an FSoftObjectPath, or a tagged list.

        ``end`` is accepted for symmetry with ``read_value`` but not used. Returns a dict (or a string for
        SoftObjectPath).
        """
        if sname in NATIVE:
            fmt, keys = NATIVE[sname]
            vals = r.u(fmt)
            return dict(zip(keys, vals if isinstance(vals, tuple) else (vals,)))
        if sname == 'SoftObjectPath':
            p = self.fname(r)
            sub = r.fstr()
            return p + (':' + sub if sub else '')
        return self.read_props(r)

    def read_props(self, r):
        """Read a tagged property list from ``r`` until the ``None`` tag.

        Returns ``{name: value}``; static-array elements with a non-zero index are keyed ``'name[index]'``. After each
        value the cursor is forced to ``start + size`` so a partially decoded payload cannot desynchronise the
        stream (BoolProperty has no payload, so it is exempt). The cursor ends just after the terminator.
        """
        out = {}
        while True:
            t = self.read_tag(r)
            if t is None:
                return out
            start = r.p
            end = start + t['size']
            v = self.read_value(r, t, end)
            if t['type'] != 'BoolProperty':
                r.p = end
            key = t['name'] if t['index'] == 0 else f"{t['name']}[{t['index']}]"
            out[key] = v

    def datatable(self):
        """Read export 0 as a UDataTable.

        Returns ``(table properties, {row name: {property: value}})``. Layout after the table's own tagged
        properties: one i32 (the UObject GUID marker), i32 row count, then RowName FName + tagged row struct per row.
        """
        r = self.export_reader(0)
        props = self.read_props(r)
        r.u('i')  # extra int (object GUID marker / none)
        n = r.u('i')
        rows = {}
        for _ in range(n):
            rn = self.fname(r)
            rows[rn] = self.read_props(r)
        return props, rows


if __name__ == '__main__':
    a = Asset(sys.argv[1])
    print(
        'ver',
        a.ver,
        'names',
        len(a.names),
        'imports',
        len(a.imports),
        'exports',
        [(e['name'], a.ref(e['cls'])) for e in a.exports],
    )
    if len(sys.argv) > 2 and sys.argv[2] == 'dt':
        props, rows = a.datatable()
        print(json.dumps(props, indent=1)[:600])
        print(len(rows), 'rows')
        json.dump(rows, open(sys.argv[3], 'w'), indent=1)
        print(json.dumps(list(rows.items())[:3], indent=1))
    else:
        r = a.export_reader(0)
        print(json.dumps(a.read_props(r), indent=1)[:3000])
