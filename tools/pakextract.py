"""Extract every pak file whose path contains one of the given substrings.

Usage
    python3 tools/pakextract.py <pak dir> <out dir> <substring> [<substring> ...]

Inputs: a directory of UE4 v11 paks (see tools/pakread.py) and one or more case-sensitive substrings that are
matched against the full in-pak path (e.g. ``../../../Uncrashed/Content/MapEditor/DataTables/``).
Outputs: each matching file written below ``<out dir>`` with the leading ``../../../`` mount prefix removed, so
``../../../Uncrashed/Content/X.uasset`` lands at ``<out dir>/Uncrashed/Content/X.uasset``; one "<size> <path>" line
is printed per file. Existing files are overwritten. Paks are processed in sorted name order, so a path present in
two paks ends up with the later pak's copy.
"""

import sys, os, glob

# Make the sibling pakread module importable when run as a script from any working directory.
sys.path.insert(0, os.path.dirname(__file__))
from pakread import Pak

pakdir, outdir = sys.argv[1], sys.argv[2]
pats = sys.argv[3:]
os.makedirs(outdir, exist_ok=True)
for p in sorted(glob.glob(os.path.join(pakdir, '*.pak'))):
    pk = Pak(p)
    for f in pk.files:
        if any(pat in f for pat in pats):
            data = pk.read(f)
            # Strip the mount point: in-pak paths are relative to <app>/Contents/UE4/Uncrashed/Content/Paks.
            rel = f.replace('../../../', '')
            dst = os.path.join(outdir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(data)
            print(len(data), rel)
