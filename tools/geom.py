"""Polygon helpers shared by the NYC and Central Park builders (extracted from build_nyc.py)."""
import math
def l2w(cx, cy, yaw, u, v):
    c, s = math.cos(yaw), math.sin(yaw); return cx + u * c - v * s, cy + u * s + v * c
GRID_SNAP = None   # set by the caller to snap rectangles to a street grid; None = free orientation
# ---- geometry ---------------------------------------------------------------
def poly_area(pts):
    return 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))))
def centroid(pts):
    a = cx = cy = 0
    for i in range(len(pts)):
        x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % len(pts)]; f = x0 * y1 - x1 * y0; a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
    if abs(a) < 1e-9: return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return cx / (3 * a), cy / (3 * a)
def convex_hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2: return pts
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]
def min_rect(pts):
    hull = convex_hull(pts); best = None
    for i in range(len(hull)):
        x0, y0 = hull[i]; x1, y1 = hull[(i + 1) % len(hull)]
        th = math.atan2(y1 - y0, x1 - x0); c, s = math.cos(th), math.sin(th)
        us = [p[0] * c + p[1] * s for p in pts]; vs = [-p[0] * s + p[1] * c for p in pts]
        lx, ly = max(us) - min(us), max(vs) - min(vs)
        if best is None or lx * ly < best[0]:
            cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            best = (lx * ly, cu * c - cv * s, cu * s + cv * c, lx, ly, th)
    return best[1:]
def point_in_poly(x, y, pts):
    inside = False; n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x0 + (y - y0) * (x1 - x0) / (y1 - y0) > x: inside = not inside
    return inside
def largest_rect(grid):
    R, C = len(grid), len(grid[0]); hist = [0] * C; best = (0, None)
    for r in range(R):
        for c in range(C): hist[c] = hist[c] + 1 if grid[r][c] else 0
        stack = []
        for c in range(C + 1):
            cur = hist[c] if c < C else 0; start = c
            while stack and stack[-1][1] > cur:
                s, hgt = stack.pop(); area = hgt * (c - s)
                if area > best[0]: best = (area, (r - hgt + 1, s, hgt, c - s))
                start = s
            stack.append((start, cur))
    return best[1]
GRID_SNAP = None   # set once the street grid orientation is known
def aligned_rect(pts, th):
    c, s = math.cos(th), math.sin(th)
    us = [p[0] * c + p[1] * s for p in pts]; vs = [-p[0] * s + p[1] * c for p in pts]
    cu, cv = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
    return (cu * c - cv * s, cu * s + cv * c, max(us) - min(us), max(vs) - min(vs), th)
def best_rect(pts):
    r = min_rect(pts)
    if GRID_SNAP is None: return r
    g = aligned_rect(pts, GRID_SNAP)
    return g if g[2] * g[3] <= 1.18 * r[2] * r[3] else r
def decompose(pts, max_rects=12):
    area = poly_area(pts); cx, cy, lx, ly, th = best_rect(pts)
    if lx * ly <= 0 or area / (lx * ly) >= 0.74 or min(lx, ly) < 7: return [(cx, cy, lx, ly, th)]
    c, s = math.cos(th), math.sin(th)
    loc = [((p[0] - cx) * c + (p[1] - cy) * s, -(p[0] - cx) * s + (p[1] - cy) * c) for p in pts]
    cell = max(2.0, max(lx, ly) / 40)
    nu, nv = max(1, int(math.ceil(lx / cell))), max(1, int(math.ceil(ly / cell)))
    grid = [[point_in_poly(-lx / 2 + (i + 0.5) * cell, -ly / 2 + (j + 0.5) * cell, loc) for i in range(nu)] for j in range(nv)]
    total = sum(sum(r) for r in grid); out = []; covered = 0
    while len(out) < max_rects and total - covered > 0.03 * total:
        rect = largest_rect(grid)
        if not rect or rect[2] * rect[3] < 2: break
        r0, c0, hh, ww = rect
        for r in range(r0, r0 + hh):
            for cc in range(c0, c0 + ww): grid[r][cc] = False
        covered += hh * ww
        u = -lx / 2 + (c0 + ww / 2) * cell; v = -ly / 2 + (r0 + hh / 2) * cell
        out.append((*l2w(cx, cy, th, u, v), ww * cell, hh * cell, th))
    return out or [(cx, cy, lx, ly, th)]
def clip_to_square(pts, half):
    """Sutherland-Hodgman clip of a polygon to the axis-aligned square [-half, half]^2."""
    def clip(poly, inside, intersect):
        out = []
        for i in range(len(poly)):
            cur, prev = poly[i], poly[i - 1]
            if inside(cur):
                if not inside(prev): out.append(intersect(prev, cur))
                out.append(cur)
            elif inside(prev): out.append(intersect(prev, cur))
        return out
    def ix(p, q, axis, val):
        t = (val - p[axis]) / (q[axis] - p[axis]); return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
    poly = pts
    for axis, val, keep in ((0, -half, 1), (0, half, -1), (1, -half, 1), (1, half, -1)):
        if len(poly) < 3: return []
        poly = clip(poly, lambda p: (p[axis] - val) * keep >= 0, lambda p, q: ix(p, q, axis, val))
    return poly if len(poly) >= 3 else []
def rect_faces(cx, cy, lx, ly, th):
    """4 facades: (fx, fy, length, normal_yaw, u_edge, v_edge, nu, nv)."""
    out = []
    for (u, v, L, nu, nv) in ((0, ly / 2, lx, 0, 1), (0, -ly / 2, lx, 0, -1), (lx / 2, 0, ly, 1, 0), (-lx / 2, 0, ly, -1, 0)):
        fx, fy = l2w(cx, cy, th, u, v); out.append((fx, fy, L, th + math.atan2(nv, nu), u, v, nu, nv))
    return out

