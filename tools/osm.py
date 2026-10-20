#!/usr/bin/env python3
"""Turn an Overpass JSON dump into local-metre features for a map: polygons (water, grass, wood, pitch, garden,
buildings with heights, park outline), lines (paths, drives, roads, bridges) and points (trees, lamps, monuments,
fountains, benches, named places). Frame: origin (lat, lon), +X east rotated so +Y_local = `north_yaw` ... i.e.
local axes are the park grid: u along the park's long axis (bearing `axis_deg`), v across it."""

import json, math, sys, collections


def loader(path):
    d = json.load(open(path))
    nodes = {}
    ways = {}
    rels = []
    for e in d['elements']:
        if e['type'] == 'node':
            nodes[e['id']] = e
        elif e['type'] == 'way':
            ways[e['id']] = e
        else:
            rels.append(e)
    return nodes, ways, rels


class Frame:
    def __init__(self, lat0, lon0, axis_deg, flip_north=False):
        self.lat0, self.lon0 = lat0, lon0
        self.mlat = 111132.0
        self.mlon = 111320.0 * math.cos(math.radians(lat0))
        a = math.radians(axis_deg)
        self.c, self.s = math.cos(a), math.sin(a)
        self.flip = -1.0 if flip_north else 1.0

    def xy(self, lat, lon):
        e = (lon - self.lon0) * self.mlon
        n = (lat - self.lat0) * self.mlat
        u = e * self.s + n * self.c  # along the axis (bearing axis_deg): unit vector (sin a, cos a) in (east, north)
        v = e * self.c - n * self.s  # across (to the right of the axis)
        return (
            v * self.flip,
            u * self.flip,
        )  # local X = across, local Y = along; flipped so the spawn faces up the park


def way_coords(w, nodes, fr):
    out = []
    for nid in w.get('nodes', []):
        n = nodes.get(nid)
        if n:
            out.append(fr.xy(n['lat'], n['lon']))
    return out


def rel_polys(rel, ways, nodes, fr):
    """Outer rings of a multipolygon relation (inner rings returned separately)."""
    outers, inners = [], []
    segs = {'outer': [], 'inner': []}
    for m in rel.get('members', []):
        if m['type'] != 'way' or m['ref'] not in ways:
            continue
        role = 'inner' if m.get('role') == 'inner' else 'outer'
        segs[role].append(list(ways[m['ref']]['nodes']))
    for role, lst in segs.items():
        rings = []
        pool = [s for s in lst if len(s) > 1]
        while pool:
            ring = pool.pop()
            changed = True
            while changed and ring[0] != ring[-1]:
                changed = False
                for i, s in enumerate(pool):
                    if s[0] == ring[-1]:
                        ring += s[1:]
                        pool.pop(i)
                        changed = True
                        break
                    if s[-1] == ring[-1]:
                        ring += s[-2::-1]
                        pool.pop(i)
                        changed = True
                        break
                    if s[-1] == ring[0]:
                        ring = s[:-1] + ring
                        pool.pop(i)
                        changed = True
                        break
                    if s[0] == ring[0]:
                        ring = s[::-1][:-1] + ring
                        pool.pop(i)
                        changed = True
                        break
            rings.append(ring)
        for ring in rings:
            pts = [fr.xy(nodes[n]['lat'], nodes[n]['lon']) for n in ring if n in nodes]
            if len(pts) >= 3:
                (outers if role == 'outer' else inners).append(pts)
    return outers, inners


def area(poly):
    return 0.5 * abs(
        sum(
            poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly))
        )
    )


def classify(t):
    if not t:
        return None
    if t.get('natural') in ('water',) or t.get('water') or t.get('waterway') == 'riverbank':
        return 'water'
    if t.get('building') and t.get('building') != 'no':
        return 'building'
    if t.get('building:part'):
        return 'building_part'
    if t.get('leisure') == 'playground':
        return 'plaza'
    if (
        t.get('landuse') in ('grass', 'meadow', 'recreation_ground', 'village_green')
        or t.get('leisure') in ('pitch', 'garden', 'golf_course')
        or t.get('natural') in ('grassland',)
    ):
        return 'grass'
    if t.get('natural') in ('wood', 'scrub') or t.get('landuse') == 'forest':
        return 'wood'
    if t.get('natural') in ('bare_rock', 'rock'):
        return 'rock'
    if t.get('leisure') in ('park', 'nature_reserve'):
        return 'park'
    if t.get('amenity') in ('parking',):
        return 'parking'
    if t.get('highway') in ('pedestrian',) and t.get('area') == 'yes':
        return 'plaza'
    if t.get('place') == 'square' or t.get('leisure') == 'track':
        return 'plaza'
    if t.get('amenity') == 'fountain':
        return 'fountain'
    if t.get('leisure') == 'ice_rink':
        return 'rink'
    if t.get('natural') == 'yes' and t.get('name'):
        return 'wood'
    if t.get('man_made') in ('obelisk', 'tower') or t.get('historic') in ('monument', 'memorial'):
        return 'monument'
    return None


def extract(path, fr, bbox_m=5000):
    nodes, ways, rels = loader(path)
    F = dict(polys=[], lines=[], points=[])
    used_in_rel = set()
    for r in rels:
        t = r.get('tags', {})
        k = classify(t)
        if t.get('type') != 'multipolygon' or not k:
            continue
        outers, inners = rel_polys(r, ways, nodes, fr)
        for m in r.get('members', []):
            used_in_rel.add(m['ref'])
        for o in outers:
            if max(abs(c) for p in o for c in p) > bbox_m:
                continue
            F['polys'].append(
                dict(
                    kind=k,
                    pts=[[round(x, 1), round(y, 1)] for x, y in o],
                    holes=[[[round(x, 1), round(y, 1)] for x, y in h] for h in inners],
                    tags={
                        kk: v
                        for kk, v in t.items()
                        if kk
                        in (
                            'name',
                            'height',
                            'building:levels',
                            'building',
                            'natural',
                            'leisure',
                            'landuse',
                            'water',
                            'sport',
                            'roof:shape',
                            'building:colour',
                            'amenity',
                            'tourism',
                            'historic',
                        )
                    },
                )
            )
    for w in ways.values():
        t = w.get('tags', {})
        pts = way_coords(w, nodes, fr)
        if len(pts) < 2 or max(abs(c) for p in pts for c in p) > bbox_m:
            continue
        closed = w['nodes'][0] == w['nodes'][-1] and len(pts) >= 4
        k = classify(t)
        if k and closed and w['id'] not in used_in_rel:
            F['polys'].append(
                dict(
                    kind=k,
                    pts=[[round(x, 1), round(y, 1)] for x, y in pts[:-1]],
                    holes=[],
                    tags={
                        kk: v
                        for kk, v in t.items()
                        if kk
                        in (
                            'name',
                            'height',
                            'building:levels',
                            'building',
                            'natural',
                            'leisure',
                            'landuse',
                            'water',
                            'sport',
                            'roof:shape',
                            'building:colour',
                            'amenity',
                            'tourism',
                            'historic',
                            'man_made',
                        )
                    },
                )
            )
        elif (
            t.get('highway')
            or t.get('railway')
            or t.get('man_made') in ('bridge', 'pier')
            or t.get('barrier')
            or t.get('waterway')
        ):
            F['lines'].append(
                dict(
                    kind=t.get('highway')
                    or t.get('railway')
                    or t.get('man_made')
                    or t.get('barrier')
                    or t.get('waterway'),
                    pts=[[round(x, 1), round(y, 1)] for x, y in pts],
                    tags={
                        kk: v
                        for kk, v in t.items()
                        if kk
                        in (
                            'name',
                            'bridge',
                            'tunnel',
                            'surface',
                            'width',
                            'lanes',
                            'footway',
                            'oneway',
                            'layer',
                            'barrier',
                            'lit',
                            'bicycle',
                            'horse',
                        )
                    },
                )
            )
    for n in nodes.values():
        t = n.get('tags')
        if not t:
            continue
        x, y = fr.xy(n['lat'], n['lon'])
        if abs(x) > bbox_m or abs(y) > bbox_m:
            continue
        kind = None
        if t.get('natural') == 'tree':
            kind = 'tree'
        elif t.get('highway') == 'street_lamp':
            kind = 'lamp'
        elif t.get('amenity') in (
            'bench',
            'fountain',
            'drinking_water',
            'shelter',
            'toilets',
            'cafe',
            'restaurant',
            'ice_cream',
            'bicycle_rental',
            'theatre',
            'bar',
            'fast_food',
        ):
            kind = t['amenity']
        elif t.get('historic') or t.get('tourism') in ('artwork', 'attraction', 'viewpoint', 'information'):
            kind = t.get('historic') or t.get('tourism')
        elif t.get('leisure') or t.get('man_made') or t.get('name'):
            kind = t.get('leisure') or t.get('man_made') or 'named'
        if kind:
            F['points'].append(
                dict(
                    kind=kind,
                    x=round(x, 1),
                    y=round(y, 1),
                    tags={
                        kk: v
                        for kk, v in t.items()
                        if kk
                        in (
                            'name',
                            'artwork_type',
                            'memorial',
                            'leaf_type',
                            'height',
                            'subject',
                            'genus',
                            'species',
                            'diameter_crown',
                        )
                    },
                )
            )
    return F


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    lat0, lon0, axis = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
    fr = Frame(lat0, lon0, axis, flip_north=True)
    F = extract(src, fr)
    json.dump(F, open(dst, 'w'))
    c = collections.Counter(p['kind'] for p in F['polys'])
    l = collections.Counter(p['kind'] for p in F['lines'])
    pt = collections.Counter(p['kind'] for p in F['points'])
    print('polys', sum(c.values()), dict(c))
    print('lines', sum(l.values()), dict(l.most_common(14)))
    print('points', sum(pt.values()), dict(pt.most_common(25)))
    named = sorted(
        set(
            p['tags'].get('name')
            for p in F['polys'] + F['points']
            if p['tags'].get('name') and abs(p.get('x', p['pts'][0][0] if 'pts' in p else 0)) < 500
        )
    )
    print(len(named), 'named within 500 m of the axis:', named[:200])
