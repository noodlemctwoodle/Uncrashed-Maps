import sys, os, glob

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
            rel = f.replace('../../../', '')
            dst = os.path.join(outdir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(data)
            print(len(data), rel)
