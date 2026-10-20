"""Polygon helpers shared by the NYC and Central Park builders (extracted from build_nyc.py).

Pure 2-D geometry on the map's local frame: points are (x, y) tuples in metres, angles are radians measured
counter-clockwise from +X (math.atan2 convention). A "rectangle" is the tuple (cx, cy, lx, ly, th): centre, side
along the orientation `th`, side across it, orientation. That tuple is what the builders turn into one scaled cube
(`box(...)`) or ground plane, so every routine here that returns rectangles returns it in exactly this shape.

What the builders use this for:
- `decompose` / `best_rect` / `min_rect`: turn an OSM or GIS building footprint into one or a few rectangles.
- `rect_faces`: the four facades of such a rectangle, for window decals and signage.
- `point_in_poly`, `poly_area`, `centroid`: rasterising polygons into occupancy grids, sizing and placing props.
- `clip_to_square`: trimming park polygons to the board edge.

`GRID_SNAP` is module state set by the caller (the NYC builder sets it to the Manhattan street-grid yaw); when set,
`best_rect` prefers a grid-aligned box over the free minimum-area one if it is not much bigger (see the 1.18 below).
"""

import math


def l2w(cx, cy, yaw, u, v):
    """Local rectangle frame -> world: (u along `yaw`, v 90 deg counter-clockwise from it) offset from (cx, cy).

    All lengths in metres, `yaw` in radians. Returns the world (x, y) tuple.
    """
    c, s = math.cos(yaw), math.sin(yaw)
    return cx + u * c - v * s, cy + u * s + v * c


GRID_SNAP = None  # set by the caller to snap rectangles to a street grid; None = free orientation


# ---- geometry ---------------------------------------------------------------
def poly_area(pts):
    """Area of a simple polygon (shoelace formula), m^2, always positive regardless of winding."""
    return 0.5 * abs(
        sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    )


def centroid(pts):
    """Area-weighted centroid (x, y) of a simple polygon.

    Falls back to the mean of the vertices when the signed area is ~0 (degenerate or self-cancelling ring), so a
    thin sliver never divides by zero.
    """
    a = cx = cy = 0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if abs(a) < 1e-9:
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return cx / (3 * a), cy / (3 * a)


def convex_hull(pts):
    """Convex hull by Andrew's monotone chain, O(n log n).

    Sorts the unique points, builds the lower chain left to right and the upper chain right to left, popping any
    point that would make a clockwise (or collinear, `<= 0`) turn. Returns the hull vertices counter-clockwise with
    no repeated end point; collinear points on an edge are dropped. With <= 2 distinct points the sorted points are
    returned as they are.
    """
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        """z of (a - o) x (b - o): > 0 for a counter-clockwise turn o -> a -> b."""
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def min_rect(pts):
    """Minimum-area enclosing rectangle of a point set -> (cx, cy, lx, ly, th).

    One side of the minimum-area bounding rectangle is always collinear with a convex-hull edge, so it is enough to
    try the orientation of every hull edge: rotate all points into that frame (u along the edge, v across), take the
    axis-aligned extent, keep the smallest area. `lx` is the side along `th` (radians), `ly` the side across it, and
    the centre is rotated back into world coordinates. Metres in, metres out.
    """
    hull = convex_hull(pts)
    best = None
    for i in range(len(hull)):
        x0, y0 = hull[i]
        x1, y1 = hull[(i + 1) % len(hull)]
        th = math.atan2(y1 - y0, x1 - x0)
        c, s = math.cos(th), math.sin(th)
        us = [p[0] * c + p[1] * s for p in pts]
        vs = [-p[0] * s + p[1] * c for p in pts]
        lx, ly = max(us) - min(us), max(vs) - min(vs)
        if best is None or lx * ly < best[0]:
            cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (lx * ly, cu * c - cv * s, cu * s + cv * c, lx, ly, th)
    return best[1:]


def point_in_poly(x, y, pts):
    """Even-odd (ray casting) point-in-polygon test.

    Casts a ray from (x, y) towards +X and counts the polygon edges it crosses; an odd count means inside. Works
    for concave and self-intersecting rings; points exactly on an edge may land on either side.
    """
    inside = False
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x0 + (y - y0) * (x1 - x0) / (y1 - y0) > x:
            inside = not inside
    return inside


def largest_rect(grid):
    """Largest all-True axis-aligned rectangle in a boolean grid (list of rows).

    Classic histogram method, O(rows * cols): for each row, `hist[c]` is the number of consecutive True cells ending
    at this row in column c; the largest rectangle whose bottom edge is this row is then the largest rectangle under
    that histogram, found with a monotonic stack (a sentinel column of height 0 at `c == C` flushes the stack).
    Returns (row0, col0, height, width) in cells, or None when the grid has no True cell.
    """
    R, C = len(grid), len(grid[0])
    hist = [0] * C
    best = (0, None)
    for r in range(R):
        for c in range(C):
            hist[c] = hist[c] + 1 if grid[r][c] else 0
        stack = []
        for c in range(C + 1):
            cur = hist[c] if c < C else 0
            start = c
            while stack and stack[-1][1] > cur:
                s, hgt = stack.pop()
                area = hgt * (c - s)
                if area > best[0]:
                    best = (area, (r - hgt + 1, s, hgt, c - s))
                start = s
            stack.append((start, cur))
    return best[1]


GRID_SNAP = None  # set once the street grid orientation is known (second assignment; both leave it None at import)


def aligned_rect(pts, th):
    """Bounding rectangle of the points at the fixed orientation `th` (radians) -> (cx, cy, lx, ly, th).

    Same projection as `min_rect` but for one given direction; used to snap footprints to a street grid.
    """
    c, s = math.cos(th), math.sin(th)
    us = [p[0] * c + p[1] * s for p in pts]
    vs = [-p[0] * s + p[1] * c for p in pts]
    cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    return (cu * c - cv * s, cu * s + cv * c, max(us) - min(us), max(vs) - min(vs), th)


def best_rect(pts):
    """Rectangle to represent a footprint: the minimum-area one, or the `GRID_SNAP`-aligned one when that is within
    18 % of its area (so near-square footprints follow the street grid instead of coming out at odd angles)."""
    r = min_rect(pts)
    if GRID_SNAP is None:
        return r
    g = aligned_rect(pts, GRID_SNAP)
    return g if g[2] * g[3] <= 1.18 * r[2] * r[3] else r


def decompose(pts, max_rects=12):
    """Cover a footprint polygon with up to `max_rects` rectangles -> list of (cx, cy, lx, ly, th), metres/radians.

    Single rectangle when the best bounding rectangle already covers the polygon well (polygon area >= 74 % of the
    rectangle), when the footprint is narrow (shorter side < 7 m, too thin to split usefully) or degenerate. Otherwise
    the polygon is rasterised in the rectangle's own frame (cell = max(2 m, longest side / 40), so at most ~40 cells
    along) and `largest_rect` is applied greedily: take the biggest remaining all-inside rectangle, clear it, repeat
    until 97 % of the inside cells are covered, `max_rects` is reached or the next piece would be under 2 cells.
    This keeps L- and U-shaped buildings as a few boxes. All output rectangles share the orientation `th`.
    """
    area = poly_area(pts)
    cx, cy, lx, ly, th = best_rect(pts)
    if lx * ly <= 0 or area / (lx * ly) >= 0.74 or min(lx, ly) < 7:
        return [(cx, cy, lx, ly, th)]
    c, s = math.cos(th), math.sin(th)
    loc = [((p[0] - cx) * c + (p[1] - cy) * s, -(p[0] - cx) * s + (p[1] - cy) * c) for p in pts]
    cell = max(2.0, max(lx, ly) / 40)
    nu, nv = max(1, int(math.ceil(lx / cell))), max(1, int(math.ceil(ly / cell)))
    # grid[j][i]: cell centre (i along u, j along v) inside the polygon, in the rectangle frame
    grid = [
        [point_in_poly(-lx / 2 + (i + 0.5) * cell, -ly / 2 + (j + 0.5) * cell, loc) for i in range(nu)]
        for j in range(nv)
    ]
    total = sum(sum(r) for r in grid)
    out = []
    covered = 0
    while len(out) < max_rects and total - covered > 0.03 * total:
        rect = largest_rect(grid)
        if not rect or rect[2] * rect[3] < 2:
            break
        r0, c0, hh, ww = rect
        for r in range(r0, r0 + hh):
            for cc in range(c0, c0 + ww):
                grid[r][cc] = False
        covered += hh * ww
        # cell indices -> rectangle-frame centre (u, v) -> world via l2w
        u = -lx / 2 + (c0 + ww / 2) * cell
        v = -ly / 2 + (r0 + hh / 2) * cell
        out.append((*l2w(cx, cy, th, u, v), ww * cell, hh * cell, th))
    return out or [(cx, cy, lx, ly, th)]


def clip_to_square(pts, half):
    """Sutherland-Hodgman clip of a polygon to the axis-aligned square [-half, half]^2.

    Clips against the four half-planes in turn (x >= -half, x <= half, y >= -half, y <= half); each pass keeps the
    vertices inside and inserts the edge/boundary intersection wherever an edge crosses. Returns the clipped ring
    (may have new vertices) or [] when fewer than 3 vertices survive. Metres in, metres out.
    """

    def clip(poly, inside, intersect):
        """One Sutherland-Hodgman pass against a half-plane given by `inside(p)` and `intersect(p, q)`."""
        out = []
        for i in range(len(poly)):
            cur, prev = poly[i], poly[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(intersect(prev, cur))
        return out

    def ix(p, q, axis, val):
        """Point where segment p-q crosses the line coordinate[axis] == val."""
        t = (val - p[axis]) / (q[axis] - p[axis])
        return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))

    poly = pts
    for axis, val, keep in ((0, -half, 1), (0, half, -1), (1, -half, 1), (1, half, -1)):
        if len(poly) < 3:
            return []
        poly = clip(poly, lambda p: (p[axis] - val) * keep >= 0, lambda p, q: ix(p, q, axis, val))
    return poly if len(poly) >= 3 else []


def rect_faces(cx, cy, lx, ly, th):
    """4 facades: (fx, fy, length, normal_yaw, u_edge, v_edge, nu, nv).

    For the rectangle (cx, cy, lx, ly, th): `fx, fy` is the world centre of the face, `length` its width in metres,
    `normal_yaw` the world yaw (radians) of its outward normal, `(u_edge, v_edge)` the face centre in the rectangle's
    local frame and `(nu, nv)` the outward unit normal in that frame. Order: +v side, -v side, +u side, -u side.
    """
    out = []
    for u, v, L, nu, nv in (
        (0, ly / 2, lx, 0, 1),
        (0, -ly / 2, lx, 0, -1),
        (lx / 2, 0, ly, 1, 0),
        (-lx / 2, 0, ly, -1, 0),
    ):
        fx, fy = l2w(cx, cy, th, u, v)
        out.append((fx, fy, L, th + math.atan2(nv, nu), u, v, nu, nv))
    return out
