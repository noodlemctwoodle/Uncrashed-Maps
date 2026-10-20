#!/usr/bin/env python3
"""Parts: complete map features built from real editor assets, each verified in the game before a map uses it.

A part is a function `part(sc, <geometry>, **options)` that builds into a Scene (tools/scene.py). Map builders
stitch parts along mapped geometry (polylines and polygons in metres); they never place a bench, a car or a
bridge pier themselves. Every part also has a demo registered in DEMOS, which `tools/showroom.py` lays out on a
grid for one in-game check and `tools/test_prefabs.py` checks by geometry and by a golden hash.

Rules the parts enforce (each one was a bug seen in the game first):
- roads carry everything a road has: carriageway, lane dashes, kerbs, sidewalks on both sides, lamps, bins,
  walkers on the sidewalks (never on the carriageway) and cars in the lanes (never off the asphalt)
- a vehicle's long axis comes from the catalogue bounds (the van is long on Y, the cars on X)
- a bridge is straight: its axis is the chord of the path it carries, the deck spans just the cut, the stairs
  or ramps land exactly where the path was cut back, and nothing else stands on its footprint
- a road cut keeps its carriageway continuous under every bridge; drives crossing it get gaps in the walls
- a fountain basin is a solid masonry ring with the water inside and below the rim
- benches run along the path with the seat facing it; nothing is placed inside a keep-clear zone
"""

import math

from mapkit import BOWER, CAFE, DECK_ON_POSTS, PLAYGROUND, STAIR_A, STAIR_RISE, l2w, size
from scene import BRIDGE, PATH, ROAD, SIDEWALK, WATER, point_in_poly

# ---- rows -------------------------------------------------------------------------------------------------------
LAMP_TALL, LAMP_SHORT, TRASH = "NewRow_3", "NewRow_20", "NewRow_323"
PEOPLE = ["NewRow_252", "NewRow_255", "NewRow_801", "NewRow_802"]
PEOPLE_SIT = ["NewRow_254", "NewRow_800"]
CARS = ["NewRow_103", "NewRow_257", "NewRow_93", "NewRow_775"]
WATER_ROW = "NewRow_183"
ROCKS = ["NewRow_71", "NewRow_162"]
WILLOW, BUSHES = "NewRow_171", ["NewRow_164", "NewRow_226"]
FOOD_CART, FOOD_STALL, TABLE, CHAIR = "NewRow_246", "NewRow_247", "NewRow_353", "NewRow_352"
STATUE_FIGURE = "NewRow_802"
WALL_H = 3.6  # retaining-wall height of a road cut
DEMOS = {}


def demo(name, radius):
    """Register a showroom demo: fn(sc, x, y, yaw) builds the part with sample geometry; radius (m) is its footprint."""

    def deco(fn):
        DEMOS[name] = (fn, radius)
        return fn

    return deco


# ---- polyline helpers --------------------------------------------------------------------------------------------
def along(pts, step, start=0.0):
    """Yield (x, y, yaw, distance) every `step` metres along a polyline."""
    acc, nxt = 0.0, start
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        yaw = math.atan2(y1 - y0, x1 - x0)
        while nxt <= acc + L:
            t = (nxt - acc) / L
            yield x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, yaw, nxt
            nxt += step
        acc += L


def length(pts):
    return sum(math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:]))


def offset(pts, d):
    """A polyline shifted `d` metres to its left (negative = right), joints mitred."""
    out = []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        yaw = math.atan2(b[1] - a[1], b[0] - a[0])
        out.append((x - d * math.sin(yaw), y + d * math.cos(yaw)))
    return out


def simplify(pts, tol=0.25):
    """Douglas-Peucker: drop the vertices that stay within `tol` m of a straight line."""
    if len(pts) < 3:
        return list(pts)
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    L = math.hypot(x1 - x0, y1 - y0) or 1e-9
    worst, wi = 0.0, 0
    for i, (x, y) in enumerate(pts[1:-1], 1):
        d = abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / L
        if d > worst:
            worst, wi = d, i
    if worst <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[: wi + 1], tol)[:-1] + simplify(pts[wi:], tol)


def clip(pts, blockers):
    """The parts of a polyline outside every (x, y, r) circle. Untouched polylines come back as they are; the
    others are sampled at 1 m, cut, and simplified again (a vertex per metre would mean a plane per metre)."""
    near = [b for b in blockers if any(math.hypot(x - b[0], y - b[1]) < b[2] + 40 for (x, y) in pts)]
    if not near:
        return [list(pts)]
    out, run = [], []
    for x, y, yaw, dist in along(pts, 1.0):
        if any(math.hypot(x - bx, y - by) < br for (bx, by, br) in near):
            if len(run) > 1:
                out.append(simplify(run))
            run = []
        else:
            run.append((x, y))
    if len(run) > 1:
        out.append(simplify(run))
    return out


def points_at(pts, P, R):
    """The two points of a polyline R metres along it either side of its nearest sample to P."""
    samples = [(x, y, dist) for x, y, yaw, dist in along(pts, 0.5)]
    _, _, d0 = min(samples, key=lambda q: math.hypot(q[0] - P[0], q[1] - P[1]))
    a_ = min(samples, key=lambda q: abs(q[2] - (d0 - R)))
    b_ = min(samples, key=lambda q: abs(q[2] - (d0 + R)))
    return (a_[0], a_[1]), (b_[0], b_[1])


def seg_cross(a, b, c, d):
    """Intersection point of segments a-b and c-d, or None."""
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = a, b, c, d
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1)) if 0 <= t <= 1 and 0 <= u <= 1 else None


# ---- paths and roads --------------------------------------------------------------------------------------------
def path(
    sc,
    pts,
    width=3.6,
    material="pavement",
    furniture=True,
    blockers=(),
    lamps=36.0,
    benches=18.0,
    bins=110.0,
    people=30.0,
):
    """A paved path with its furniture: lamps alternating sides, benches facing the path, bins and walkers on it.
    `blockers` are (x, y, r) circles (bridge approaches) the path is cut back from."""
    for part in clip(pts, blockers) if blockers else [pts]:
        sc.ribbon(part, width, material, max_piece=32.0)
        sc.mark_line(part, width, PATH)
        if not furniture:
            continue
        for x, y, yaw, dist in along(part, 1.0):
            if sc.occ_at(x, y) == BRIDGE or not sc.clear_at(x, y):
                continue
            side = 1 if int(dist / lamps) % 2 == 0 else -1
            if dist % lamps < 1:
                sc.put(LAMP_SHORT, *l2w(x, y, yaw, 0, side * (width / 2 + 0.6)), 0, 1.0, yaw + side * math.pi / 2)
                sc.st("lamps")
            if benches and dist % benches < 1 and dist % lamps >= 1:
                sc.bench(*l2w(x, y, yaw, 0, -side * (width / 2 + 0.9)), yaw, -side)
            if dist % bins < 1 and dist > 0:
                sc.put(TRASH, *l2w(x, y, yaw, 1.5, side * (width / 2 + 0.5)), 0, 1.0, yaw)
            if people and dist % people < 1 and dist > 0:
                v = sc.rng.uniform(-width / 2 + 0.6, width / 2 - 0.6)
                sc.put(
                    sc.rng.choice(PEOPLE),
                    *l2w(x, y, yaw, 0, v),
                    0,
                    1.0,
                    yaw + (0 if sc.rng.random() < 0.5 else math.pi),
                )
                sc.st("people")
    sc.st("paths")


def road(sc, pts, width=12.0, sidewalk=3.0, lamps=30.0, cars=45.0, people=16.0, line=True, kerb=True, blockers=()):
    """A street: asphalt carriageway, dashed centre line, kerbs, a sidewalk each side with tall lamps, bins and
    walkers, and cars in both lanes heading along their lane. `sidewalk=0` gives a bare carriageway (road cuts)."""
    for part in clip(pts, blockers) if blockers else [pts]:
        sc.ribbon(part, width, "asphalt", max_piece=32.0)
        sc.mark_line(part, width, ROAD)
        sc.roads.append((part, width))
        if line:
            for x, y, yaw, dist in along(part, 8.0, 4.0):
                sc.box("yellow", x, y, sc.g(x, y) + 0.10 + 0.012, 0.03, 3.0, 0.25, yaw)
        for sgn in (-1, 1):
            if kerb:
                for (x0, y0), (x1, y1) in zip(part, part[1:]):
                    L = math.hypot(x1 - x0, y1 - y0)
                    yaw = math.atan2(y1 - y0, x1 - x0)
                    kx, ky = l2w((x0 + x1) / 2, (y0 + y1) / 2, yaw, 0, sgn * (width / 2 + 0.15))
                    sc.box("grey", kx, ky, sc.g(kx, ky) + 0.05, 0.14, L + 0.3, 0.3, yaw)
            if sidewalk:
                walk = offset(part, sgn * (width / 2 + 0.3 + sidewalk / 2))
                sc.ribbon(walk, sidewalk, "pavement2", max_piece=32.0)
                sc.mark_line(walk, sidewalk, SIDEWALK)
        for x, y, yaw, dist in along(part, 1.0):
            if sc.occ_at(x, y) == BRIDGE or not sc.clear_at(x, y):
                continue
            side = 1 if int(dist / lamps) % 2 == 0 else -1
            if dist % lamps < 1:
                # on the sidewalk's outer half; a bare carriageway (a cut) gets them on the bank outside its walls
                v = width / 2 + 0.3 + (sidewalk - 0.4 if sidewalk else 1.9)
                sc.put(LAMP_TALL, *l2w(x, y, yaw, 0, side * v), 0, 1.0, yaw + side * math.pi / 2)
                sc.st("street_lamps")
            if sidewalk and dist % 90 < 1 and dist > 0:
                sc.put(TRASH, *l2w(x, y, yaw, 1.5, -side * (width / 2 + 0.8)), 0, 1.0, yaw)
            if sidewalk and people and dist % people < 1 and dist > 0:
                v = sc.rng.choice([-1, 1]) * (width / 2 + 0.3 + sc.rng.uniform(0.7, sidewalk - 0.7))
                sc.put(
                    sc.rng.choice(PEOPLE),
                    *l2w(x, y, yaw, 0, v),
                    0,
                    1.0,
                    yaw + (0 if sc.rng.random() < 0.5 else math.pi),
                )
                sc.st("people")
            if cars and dist % cars < 1 and dist > 0:
                lane = 1 if int(dist / cars) % 2 else -1  # lanes alternate so traffic runs both ways
                sc.vehicle(sc.rng.choice(CARS), x, y, yaw + (0 if lane > 0 else math.pi), sc.on_road, width / 4)
    sc.st("roads")


# ---- bridges and road cuts ---------------------------------------------------------------------------------------
BRIDGE_LEN = 12.0 + 1.6 + 3.0  # deck length over a 12 m cut: walls at 6.8 m, piers just outside them


def approach_run(width, rise):
    """Approach length: real stairs for paths under 6 m, ramps for wider ways."""
    return size(STAIR_A)[1] * rise / STAIR_RISE if width < 6.0 else max(12.0, rise * 4.0)


def footbridge(sc, x, y, yaw, width=4.2, clear_h=WALL_H + 1.0, span=BRIDGE_LEN, deck="flagstone"):
    """A straight footbridge over a cut: brick piers outside the walls, concrete deck, parapets, stairs (narrow)
    or ramps (wide) landing on the axis. Its footprint is marked BRIDGE so no part puts anything on it."""
    rise = clear_h + 0.6
    run = approach_run(width, rise)
    sc.bridge(x, y, span, width, yaw, clear_h=clear_h, deck=deck, stairs=width < 6.0, span=span)
    sc.mark_rect(x, y, span + 2 * run + 2, width + 4, yaw, BRIDGE)
    return run


def plan_crossings(cut_pts, cut_w, ways, wall_h=WALL_H):
    """Where mapped ways cross a road cut's centreline. ways = [(pts, width, is_drive)]. Returns
    (junctions, bridges): junctions = [(x, y, width)] for drives (at-grade, walls get a gap); bridges =
    [dict(x, y, yaw, w, R, links)] for paths, each straight along the chord of the path R metres either side."""
    junctions, foot = [], []
    for pts, w, is_drive in ways:
        for a, b in zip(cut_pts, cut_pts[1:]):
            for c, d in zip(pts, pts[1:]):
                P = seg_cross(a, b, c, d)
                if P is None:
                    continue
                (junctions if is_drive else foot).append((P[0], P[1], w, pts))

    def dedupe(recs, r):
        kept = []
        for rec in sorted(recs, key=lambda q: -q[2]):
            if not any(math.hypot(rec[0] - k[0], rec[1] - k[1]) < r for k in kept):
                kept.append(rec)
        return kept

    junctions = dedupe(junctions, 12.0)
    foot = [c for c in dedupe(foot, 14.0) if not any(math.hypot(c[0] - j[0], c[1] - j[1]) < 16.0 for j in junctions)]
    bridges = []
    for x, y, w, pts in foot:
        R = BRIDGE_LEN / 2 + approach_run(w, wall_h + 1.6)
        A, B = points_at(pts, (x, y), R)
        yaw = math.atan2(B[1] - A[1], B[0] - A[0])
        fa, fb = l2w(x, y, yaw, -R, 0), l2w(x, y, yaw, R, 0)
        if math.hypot(A[0] - fb[0], A[1] - fb[1]) < math.hypot(A[0] - fa[0], A[1] - fa[1]):
            fa, fb = fb, fa
        links = [
            [end, foot_] for end, foot_ in ((A, fa), (B, fb)) if math.hypot(end[0] - foot_[0], end[1] - foot_[1]) > 0.3
        ]
        bridges.append(dict(x=x, y=y, yaw=yaw, w=w, R=R, links=links))
    return [(x, y, w) for x, y, w, _ in junctions], bridges


def road_cut(sc, pts, width=12.0, wall_h=WALL_H, ways=(), cars=45.0):
    """A sunken-road stand-in (the terrain cannot be dug): a bare carriageway between retaining walls, with cars
    and lamps, the walls broken where drives cross at grade, and a straight footbridge wherever a path crosses.
    Returns dict(paths=[(x, y, r)], drives=[(x, y, r)]): the circles the crossing paths and drives must be cut
    back from (pass them as `blockers` to path() and road())."""
    junctions, bridges = plan_crossings(pts, width, ways, wall_h)
    for b in bridges:  # bridges first: the carriageway furniture then avoids their footprint
        footbridge(sc, b["x"], b["y"], b["yaw"], b["w"] + 0.6, wall_h + 1.0)
        for link in b["links"]:
            sc.ribbon(link, b["w"], "pavement")
    road(sc, pts, width, sidewalk=0, lamps=40.0, cars=cars, people=0, kerb=False)
    # the walls run width/2 + 0.8 off the centreline, so a gap circle around the junction point must reach them:
    # its radius is the hypotenuse of the half-gap and the wall offset (a circle of the half-gap alone never
    # touched the walls and they ran straight across the drive, as seen in the game)
    gaps = [(jx, jy, math.hypot(jw / 2 + 1.5, width / 2 + 0.8)) for (jx, jy, jw) in junctions]
    for sgn in (-1, 1):
        line = offset(pts, sgn * (width / 2 + 0.8))
        for part in clip(line, gaps) if gaps else [line]:
            sc.wall(part, "retaining", wall_h)
    sc.st("road_cuts")
    sc.st("cut_junctions", len(junctions))
    sc.st("cut_footbridges", len(bridges))
    return dict(
        paths=[(b["x"], b["y"], b["R"]) for b in bridges],  # cut crossing paths back to the bridge approaches
        drives=[
            (jx, jy, width / 2 - 0.3) for (jx, jy, jw) in junctions
        ],  # cut crossing drives inside the cut's asphalt
    )


# ---- water --------------------------------------------------------------------------------------------------------
def pond(sc, poly, rocks=True, willows=True):
    """A water body: tiles subdivided to 2 m at the shore, water 0.30 m over the highest ground inside it, bank rocks
    and willows along the shore. The polygon runs counter-clockwise (water on the left of its edges)."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    inside = [
        sc.g(x, y)
        for x in range(int(min(xs)), int(max(xs)) + 1, 6)
        for y in range(int(min(ys)), int(max(ys)) + 1, 6)
        if point_in_poly(x, y, poly)
    ]
    level = (max(inside) if inside else sc.g(xs[0], ys[0])) + 0.30

    def lay(x, y, s):
        corners = [(x + dx, y + dy) for dx in (-s / 2, s / 2) for dy in (-s / 2, s / 2)]
        ins = sum(point_in_poly(cx, cy, poly) for cx, cy in corners)
        if ins == 4 or (s <= 2 and ins >= 2):
            sc.add(WATER_ROW, x, y, level, s / 4, s / 4, 1.0)
            sc.mark(x, y, WATER)
            sc.st("water_tiles")
        elif ins > 0 and s > 2:
            for dx in (-s / 4, s / 4):
                for dy in (-s / 4, s / 4):
                    lay(x + dx, y + dy, s / 2)

    for x in range(int(min(xs)) - 4, int(max(xs)) + 8, 8):
        for y in range(int(min(ys)) - 4, int(max(ys)) + 8, 8):
            lay(x + 4, y + 4, 8)
    ring = list(poly) + [poly[0]]
    for x, y, yaw, dist in along(ring, 12.0):
        if rocks:
            rx, ry = l2w(x, y, yaw, 0, -1.2)
            if not point_in_poly(rx, ry, poly):
                sc.put(sc.rng.choice(ROCKS), rx, ry, 0.0, sc.rng.uniform(0.7, 1.3), sc.rng.uniform(0, 6.28))
                sc.st("bank_rocks")
        if willows and int(dist) % 48 == 0:
            wx, wy = l2w(x, y, yaw, 0, -5)
            if not point_in_poly(wx, wy, poly):
                sc.put(WILLOW, wx, wy, 0.0, 1.0, sc.rng.uniform(0, 6.28))
    sc.st("ponds")


def fountain(sc, x, y, radius=8.0, rim_h=0.75, figure=True, pad=True, benches=6):
    """A round fountain: flagstone pad, solid masonry basin with the water inside, a stepped pedestal and a figure
    on top, benches around it facing the water. The basin is a keep-clear zone for every other part."""
    g = sc.g(x, y) + (0.16 if pad else 0.0)
    if pad:
        sc.surface("flagstone", x, y, radius * 2 + 10, radius * 2 + 10, 0.0)
    sc.basin(x, y, radius, rim_h, z_base=g)
    sc.cylinder("grey", x, y, g, 2.6, 2.2)
    sc.cylinder("grey", x, y, g + 2.6, 0.8, 4.2)
    if figure:
        sc.add(STATUE_FIGURE, x, y, g + 3.4, 1.8, 1.8, 1.8, math.pi)
    sc.keep_clear.append((x, y, radius + 1.5))
    for i in range(benches):
        a = i / benches * 2 * math.pi
        bx, by = x + (radius + 2.6) * math.cos(a), y + (radius + 2.6) * math.sin(a)
        sc.bench(bx, by, a + math.pi / 2, -1)  # the seat faces the water
    sc.st("fountains")


# ---- plazas and small buildings ----------------------------------------------------------------------------------
def plaza(sc, poly, material="flagstone", people=0):
    """A paved area tiled with 8 m squares (4 m at the edge) inside a polygon."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    piece = 0
    for x in range(int(min(xs)), int(max(xs)) + 8, 8):
        for y in range(int(min(ys)), int(max(ys)) + 8, 8):
            corners = [(x + dx, y + dy) for dx in (0, 8) for dy in (0, 8)]
            ins = sum(point_in_poly(cx, cy, poly) for cx, cy in corners)
            if ins == 4:
                sc.surface(material, x + 4, y + 4, 8.2, 8.2, 0.0, piece)
                piece += 1
            elif ins:
                for dx in (0, 4):
                    for dy in (0, 4):
                        if point_in_poly(x + dx + 2, y + dy + 2, poly):
                            sc.surface(material, x + dx + 2, y + dy + 2, 4.2, 4.2, 0.0, piece)
                            piece += 1
    sc.mark_poly(poly, PATH)
    for i in range(people):
        px, py = sc.rng.uniform(min(xs), max(xs)), sc.rng.uniform(min(ys), max(ys))
        if point_in_poly(px, py, poly):
            sc.put(sc.rng.choice(PEOPLE), px, py, 0.16, 1.0, sc.rng.uniform(0, 6.28))
    sc.st("plazas")


def kiosks(sc, x, y, yaw, n=2, cart=True, people=5):
    """Market kiosks and a food cart on flagstones with customers."""
    sc.surface("flagstone", x, y, 12 * n, 18, yaw)
    for i in range(n):
        sc.kiosk(*l2w(x, y, yaw, -6 * (n - 1) + 12 * i, 0), yaw)
    if cart:
        sc.put(FOOD_CART, *l2w(x, y, yaw, 0, -5), 0.16, 1.0, yaw)
    for i in range(people):
        px, py = l2w(x, y, yaw, sc.rng.uniform(-6 * n + 1, 6 * n - 1), sc.rng.uniform(-7, 5))
        sc.put(sc.rng.choice(PEOPLE), px, py, 0.16, 1.0, sc.rng.uniform(0, 6.28))


def playground(sc, x, y, yaw, lx=24.0, ly=20.0):
    """A fenced playground with play equipment on a paved pad."""
    pts = [
        l2w(x, y, yaw, u, v)
        for (u, v) in ((-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2), (-lx / 2, -ly / 2))
    ]
    sc.surface("flagstone", x, y, lx, ly, yaw)
    sc.wall(pts, "fence", 1.5)
    for i, row in enumerate(PLAYGROUND[:5]):
        px, py = l2w(x, y, yaw, -lx / 2 + 4 + i * (lx - 8) / 4, sc.rng.uniform(-ly / 2 + 4, ly / 2 - 4))
        sc.put(row, px, py, 0.16, 1.0, sc.rng.uniform(0, 6.28))
    sc.st("playgrounds")


def gazebo(sc, x, y, yaw, scale=1.0):
    """The park gazebo mesh on a flagstone pad (scale 2 = the carousel house)."""
    bw, bl, bh = size(BOWER)
    sc.surface("flagstone", x, y, bw * scale + 4, bl * scale + 4, yaw)
    sc.add(BOWER, x, y, sc.g(x, y) - 0.1, scale, scale, max(1.0, scale * 0.7), yaw)


def cafe(sc, x, y, yaw, tables=3):
    """A park cafe building with a terrace of tables and chairs in front (local +Y)."""
    sc.add(CAFE[0], x, y, sc.g(x, y), 1, 1, 1, yaw)
    sc.surface("flagstone", *l2w(x, y, yaw, 0, 9), 4 * tables + 4, 8, yaw)
    for i in range(tables):
        tx, ty = l2w(x, y, yaw, -2 * (tables - 1) + 4 * i, 9)
        sc.put(TABLE, tx, ty, 0.16, 1.0, yaw)
        sc.put(CHAIR, *l2w(tx, ty, yaw, 0, 1.3), 0.16, 1.0, yaw + math.pi)


def terrace(sc, x, y, yaw, rise=4.4, lx=20.0, ly=20.0):
    """A raised terrace: a solid concrete mound faced with retaining-wall panels, a parapet along the front and a
    real flight of stairs down the middle of the front (local +X)."""
    g = sc.g(x, y)
    cx, cy = l2w(x, y, yaw, -lx / 2, 0)
    sc.box("concrete", cx, cy, g - 0.3, rise + 0.3, lx, ly, yaw)
    sc.surface("flagstone", cx, cy, lx, ly, yaw, z_base=g + rise)
    for face in (
        [(0, -ly / 2), (0, ly / 2)],
        [(0, ly / 2), (-lx, ly / 2)],
        [(-lx, ly / 2), (-lx, -ly / 2)],
        [(-lx, -ly / 2), (0, -ly / 2)],
    ):
        sc.wall([l2w(x, y, yaw, u, v) for (u, v) in face], "retaining", rise)
    sc._raised_parapet([l2w(x, y, yaw, -0.5, -ly / 2 + 4), l2w(x, y, yaw, -0.5, ly / 2 - 4)], g + rise + 0.16)
    run = size(STAIR_A)[1] * rise / STAIR_RISE
    sc.stairs(*l2w(x, y, yaw, run, 0), yaw + math.pi, rise, 6.0)


def statue(sc, x, y, yaw):
    """A figure on a black plinth (the only statue mesh in the game is a wire globe)."""
    sc.box("black", x, y, sc.g(x, y) - 0.2, 1.8, 1.6, 1.6, yaw)
    sc.add(STATUE_FIGURE, x, y, sc.g(x, y) + 1.6, 1.4, 1.4, 1.4, yaw)


# ---- showroom demos ------------------------------------------------------------------------------------------------
def _line(x, y, yaw, L):
    return [l2w(x, y, yaw, -L / 2, 0), l2w(x, y, yaw, L / 2, 0)]


@demo("road", 60)
def demo_road(sc, x, y, yaw):
    """A straight 70 m street with sidewalks, kerbs, lamps, walkers and cars."""
    road(sc, _line(x, y, yaw, 100), 12.0, cars=30.0)


@demo("road_bend", 40)
def demo_road_bend(sc, x, y, yaw):
    """A bending street: the sidewalks and kerbs must follow the bend without gaps."""
    road(sc, [l2w(x, y, yaw, -35, 10), l2w(x, y, yaw, -10, 2), l2w(x, y, yaw, 12, -6), l2w(x, y, yaw, 35, -2)], 12.0)


@demo("road_cut", 54)
def demo_road_cut(sc, x, y, yaw):
    """A 70 m road cut crossed by a footpath (bridge with stairs), a wide promenade (bridge with ramps) and a drive
    (at-grade junction with gaps in the walls)."""
    cut = _line(x, y, yaw, 70)
    foot = [l2w(x, y, yaw, -24, -40), l2w(x, y, yaw, -20, 40)]
    prom = [l2w(x, y, yaw, 2, -40), l2w(x, y, yaw, 2, 40)]
    drive = [l2w(x, y, yaw, 26, -40), l2w(x, y, yaw, 26, 40)]
    cut_backs = road_cut(sc, cut, 12.0, ways=[(foot, 3.6, False), (prom, 8.0, False), (drive, 10.0, True)])
    path(sc, foot, 3.6, "pavement", blockers=cut_backs["paths"], people=0)
    path(sc, prom, 8.0, "flagstone", blockers=cut_backs["paths"], people=0)
    road(sc, drive, 10.0, sidewalk=2.0, cars=30.0, people=0, blockers=cut_backs["drives"])


@demo("footbridge_bend", 50)
def demo_footbridge_bend(sc, x, y, yaw):
    """A path that bends across the cut: the bridge is straight along the chord and short links join the path."""
    cut = _line(x, y, yaw, 50)
    bend = [l2w(x, y, yaw, -14, -40), l2w(x, y, yaw, -4, -14), l2w(x, y, yaw, 4, 14), l2w(x, y, yaw, 16, 40)]
    cut_backs = road_cut(sc, cut, 12.0, ways=[(bend, 3.6, False)], cars=0)
    path(sc, bend, 3.6, "pavement", blockers=cut_backs["paths"], people=0)


@demo("path", 35)
def demo_path(sc, x, y, yaw):
    """A 60 m park path with lamps, benches, bins and walkers."""
    path(sc, _line(x, y, yaw, 60), 3.6)


@demo("fountain", 20)
def demo_fountain(sc, x, y, yaw):
    fountain(sc, x, y, 8.0)


@demo("pond", 35)
def demo_pond(sc, x, y, yaw):
    """A kidney-shaped pond with bank rocks and willows."""
    poly = [
        l2w(x, y, yaw, 24 * math.cos(a) * (1 + 0.3 * math.cos(2 * a)), 16 * math.sin(a))
        for a in [i / 24 * 2 * math.pi for i in range(24)]
    ]
    pond(sc, poly)


@demo("plaza", 25)
def demo_plaza(sc, x, y, yaw):
    plaza(
        sc,
        [l2w(x, y, yaw, u, v) for (u, v) in ((-18, -12), (18, -12), (24, 0), (18, 12), (-18, 12))],
        "flagstone",
        people=8,
    )


@demo("kiosks", 16)
def demo_kiosks(sc, x, y, yaw):
    kiosks(sc, x, y, yaw)


@demo("playground", 16)
def demo_playground(sc, x, y, yaw):
    playground(sc, x, y, yaw)


@demo("gazebo", 10)
def demo_gazebo(sc, x, y, yaw):
    gazebo(sc, x, y, yaw)


@demo("cafe", 12)
def demo_cafe(sc, x, y, yaw):
    cafe(sc, x, y, yaw)


@demo("terrace", 28)
def demo_terrace(sc, x, y, yaw):
    terrace(sc, x, y, yaw)


@demo("statue", 6)
def demo_statue(sc, x, y, yaw):
    statue(sc, x, y, yaw)


@demo("probe", 20)
def demo_probe(sc, x, y, yaw):
    """Measurement probe: a stair and a deck placed by bounding box with marker cubes (red = stair local -Y,
    blue = +Y, yellow = deck centre)."""
    g = sc.g(x, y)
    sc.place(STAIR_A, x, y, g, 1, 1, 1, 0.0)
    sc.box("red", x, y - 5.5, g, 1.0, 1.0, 1.0)
    sc.box("blue", x, y + 5.5, g, 1.0, 1.0, 1.0)
    sc.place(DECK_ON_POSTS, x + 20, y, g, 1, 1, 1, 0.0)
    sc.box("yellow", x + 20, y, g + 4.2, 1.0, 1.0, 1.0)
