#!/usr/bin/env python3
"""Turn an Overpass JSON dump into local-metre features for a map: polygons (water, grass, wood, pitch, garden,
buildings with heights, park outline), lines (paths, drives, roads, bridges) and points (trees, lamps, monuments,
fountains, benches, named places). Frame: origin (lat, lon), +X east rotated so +Y_local = `north_yaw` ... i.e.
local axes are the park grid: u along the park's long axis (bearing `axis_deg`), v across it.

usage: osm.py <overpass.json> <features.json> <lat0> <lon0> <axis_deg>
    e.g. the Central Park build: data/centralpark_osm.json -> data/centralpark_features.json with the frame from
    data/centralpark_frame.json (lat0 40.770427, lon0 -73.972342, axis_deg 16.5). Fetch the dump from
    https://overpass-api.de/api/interpreter with a User-Agent header (406 otherwise; retry 502 with backoff).

Input: the Overpass JSON `elements` list (nodes with lat/lon, ways with node id lists, relations with members),
all carrying their OSM `tags`. Output: a JSON dict
    {'polys':  [{kind, pts: [[x, y], ...], holes: [[[x, y], ...], ...], tags}],
     'lines':  [{kind, pts: [[x, y], ...], tags}],
     'points': [{kind, x, y, tags}]}
with every coordinate in local metres rounded to 0.1 m and `tags` reduced to the whitelists in `extract`. Anything
farther than `bbox_m` (default 5000 m) from the origin on either axis is dropped.

Frame (class `Frame`): an equirectangular projection about (lat0, lon0) (111132 m per degree of latitude,
111320 * cos(lat0) m per degree of longitude), rotated so that `u` runs along the compass bearing `axis_deg`
(degrees clockwise from north) and `v` runs 90 deg to its right. Local X = v, local Y = u, both multiplied by -1
when `flip_north` is set. The command line always sets `flip_north=True`, which is what the Uncrashed boards need:
the freestyle spawn sits at the origin facing -Y, so looking along -Y means looking along `axis_deg` (up the park),
and for axis_deg = 0 that gives +X = west, +Y = south. Without the flip +X is to the right of the axis and +Y along it.

Polygon `kind` (from `classify`, first match wins): 'water' (natural=water, water=*, waterway=riverbank),
'building' (building=* except 'no'), 'building_part', 'plaza' (playgrounds, pedestrian areas, squares, tracks),
'grass' (grass/meadow/recreation/village-green landuse, pitches, gardens, golf, grassland), 'wood' (wood, scrub,
forest, and named natural=yes), 'rock' (bare_rock/rock), 'park' (park, nature_reserve), 'parking', 'fountain',
'rink' (ice_rink), 'monument' (obelisk, tower, historic monument/memorial).
Line `kind` is the raw tag value: the highway type ('footway', 'path', 'steps', 'pedestrian', 'bridleway',
'cycleway', 'service', 'residential', 'tertiary', ...), the railway type, 'bridge' or 'pier' (man_made outlines of
bridges and piers), a barrier type, or a waterway type. Line tags keep bridge/tunnel/width/layer/... so a builder can
raise bridges and parse widths (which may be feet-and-inches).
Point `kind`: 'tree' (natural=tree, with genus/species), 'lamp' (street_lamp), an amenity name (bench, fountain,
cafe, ...), a historic or tourism value (memorial, artwork, attraction, ...), a leisure or man_made value, or
'named' for any other node that has a name.
"""

import json, math, sys, collections


def loader(path):
    """Read an Overpass JSON dump into node/way/relation dicts keyed by id.

    An Overpass `out body; >; out skel qt;` dump lists every way twice: once with its tags and once as a bare
    skeleton from the node recursion. The tagged copy must win, otherwise names, highway classes and bridge/tunnel
    tags vanish (that silently dropped the transverse roads and most main streets the first time round)."""
    d = json.load(open(path))
    nodes, ways, rels = {}, {}, []
    for e in d['elements']:
        if e['type'] == 'node':
            if e['id'] not in nodes or e.get('tags'):
                nodes[e['id']] = e
        elif e['type'] == 'way':
            if e['id'] not in ways or e.get('tags'):
                ways[e['id']] = e
        else:
            rels.append(e)
    return nodes, ways, rels


class Frame:
    """Lat/lon -> local metres about (lat0, lon0), rotated to the bearing `axis_deg` (see the module docstring).

    `flip_north=True` negates both local axes so that a viewer at the origin facing -Y looks along the axis bearing;
    `flip_north=False` keeps +Y along the axis and +X to its right. Accurate to the flat-earth approximation, which
    is fine for a few km around the origin.
    """

    def __init__(self, lat0, lon0, axis_deg, flip_north=False):
        """lat0/lon0 in degrees (the local origin), axis_deg the compass bearing of local u, flip_north see above."""
        self.lat0, self.lon0 = lat0, lon0
        # metres per degree: latitude is nearly constant, longitude shrinks with cos(latitude)
        self.mlat = 111132.0
        self.mlon = 111320.0 * math.cos(math.radians(lat0))
        a = math.radians(axis_deg)
        self.c, self.s = math.cos(a), math.sin(a)
        self.flip = -1.0 if flip_north else 1.0

    def xy(self, lat, lon):
        """Project one (lat, lon) in degrees -> (x, y) local metres."""
        e = (lon - self.lon0) * self.mlon
        n = (lat - self.lat0) * self.mlat
        u = e * self.s + n * self.c  # along the axis (bearing axis_deg): unit vector (sin a, cos a) in (east, north)
        v = e * self.c - n * self.s  # across (to the right of the axis)
        return (
            v * self.flip,
            u * self.flip,
        )  # local X = across, local Y = along; flipped so the spawn faces up the park


def way_coords(w, nodes, fr):
    """Local (x, y) points of a way's node chain, in order; node ids missing from the dump are skipped."""
    out = []
    for nid in w.get('nodes', []):
        n = nodes.get(nid)
        if n:
            out.append(fr.xy(n['lat'], n['lon']))
    return out


def rel_polys(rel, ways, nodes, fr):
    """Outer rings of a multipolygon relation (inner rings returned separately).

    OSM multipolygons list their rings as member ways with role 'outer' or 'inner', and a ring is often split over
    several ways. For each role the member node-id chains are joined end to end: a chain is taken from the pool and
    extended with any remaining chain that touches either of its ends (reversed when needed) until it closes or
    nothing fits (an unclosed chain is kept as it is). Returns (outers, inners) as lists of point lists in local
    metres; rings with fewer than 3 points are dropped. The inners are NOT matched to a particular outer, the caller
    treats every inner as a hole of every outer (correct for the usual one-outer lake with islands).
    """
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
                    # four ways a chain can attach: its start or end to the ring's end, its end or start to the
                    # ring's start; the shared node is dropped so it is not duplicated
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
    """Shoelace area of a ring in local metres, m^2 (same as geom.poly_area; kept so this module stands alone)."""
    return 0.5 * abs(
        sum(
            poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly))
        )
    )


def classify(t):
    """Map an OSM tag dict to a polygon kind (see the module docstring), or None when the area is not of interest.

    The order is the priority: water beats everything (a reservoir tagged as leisure too stays water), buildings beat
    landuse, lawns beat woods, and the park outline itself ('park') comes after the surfaces inside it. `natural=yes`
    with a name catches named natural features (used in the Central Park dump for wooded areas like the Ramble).
    """
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
    """Convert the dump at `path` with frame `fr` -> {'polys', 'lines', 'points'} (see the module docstring).

    `bbox_m` (metres) drops any feature with a coordinate beyond +-bbox_m on either axis. Three passes:
    1. multipolygon relations with a classified kind: each outer ring becomes a polygon carrying all the relation's
       inner rings as holes; every member way is remembered so it is not emitted again as a plain closed way;
    2. ways: a closed way (first node == last, >= 4 points) with a classified kind becomes a polygon (the repeated
       closing point is dropped); any other way that is a highway, railway, man_made bridge/pier, barrier or
       waterway becomes a line whose kind is that tag's value;
    3. tagged nodes become points (tree, lamp, amenities, historic/tourism, leisure/man_made, or 'named').
    Tags are reduced to the whitelist each branch needs (name, height, levels, surface, width, genus, ...).
    """
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
            # a closed way without a polygon kind (e.g. a man_made=bridge outline) still lands here as a line,
            # which is how the builders get bridge and pier outlines
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
    # usage: osm.py <overpass.json> <features.json> <lat0> <lon0> <axis_deg>; always flips so +Y runs back down the
    # axis (the spawn at the origin faces -Y), then prints kind counts and the named features near the axis
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
