#!/usr/bin/env python3
"""Prefabs: small composite objects built from real editor assets, each verified on its own in the game.

Every prefab is a function `name(kit, x, y, yaw, **params)` registered in PREFABS. A map builder composes a map
from prefabs; `tools/showroom.py` places every prefab on a grid in a tiny map so one editor load checks them all.
Conventions: metres and radians; `yaw` is the prefab's main axis (a bridge's span, a road's direction, the way a
bench row runs); the kit supplies terrain-following placement (MapKit, see tools/mapkit.py).

Rules the prefabs enforce (each one was a bug seen in the game first):
- vehicles: long axis along the road from the mesh bounds, only on carriageway, lane offset to the right
- bridges over a road cut: deck spans the cut only, path-wide, piers at the walls, real stairs or textured ramps
- fountain basins: a solid masonry ring with the water inside and below the rim
- bench rows: long axis along the path, seat facing it
- nothing is placed inside another prefab's footprint: each prefab reports its footprint radius
"""

import math
import random

from mapkit import (
    BOWER,
    CAFE,
    CUBE,
    DECK_ON_POSTS,
    GROUND,
    KIOSKS,
    LAYER,
    PARAPET,
    PLAYGROUND,
    STAIR_A,
    l2w,
    rest,
    size,
)

PREFABS = {}
LAMP_SHORT, TRASH, WATER, STATUE_FIGURE = "NewRow_20", "NewRow_323", "NewRow_183", "NewRow_802"
PEOPLE = ["NewRow_252", "NewRow_255", "NewRow_801", "NewRow_802"]
CARS = ["NewRow_103", "NewRow_257", "NewRow_93", "NewRow_775"]
rng = random.Random(5)


def prefab(name, radius):
    """Register a prefab with the footprint radius (m) it needs kept clear."""

    def deco(fn):
        PREFABS[name] = (fn, radius)
        return fn

    return deco


# ---- roads and vehicles ------------------------------------------------------------------------------------
@prefab("road_with_traffic", 30)
def road_with_traffic(kit, x, y, yaw, length=50.0, width=12.0, cars=4):
    """A straight asphalt road with a centre line and correctly headed cars in both lanes."""
    kit.surface("asphalt", x, y, length, width, yaw)
    kit.box("yellow", x, y, kit.g(x, y) + LAYER["asphalt"] + 0.01, 0.01, length - 4, 0.3, yaw)
    on_road = lambda px, py: (
        abs(((px - x) * math.cos(yaw) + (py - y) * math.sin(yaw))) < length / 2
        and abs((-(px - x) * math.sin(yaw) + (py - y) * math.cos(yaw))) < width / 2
    )
    for i in range(cars):
        u = -length / 2 + (i + 0.5) * length / cars
        lane = 3.0 if i % 2 == 0 else -3.0
        cx, cy = l2w(x, y, yaw, u, 0)
        kit.vehicle(CARS[i % len(CARS)], cx, cy, yaw + (0 if lane > 0 else math.pi), on_road, lane)


@prefab("road_cut_with_footbridge", 40)
def road_cut_with_footbridge(kit, x, y, yaw, length=60.0, width=12.0, wall_h=3.6, path_w=3.6):
    """A transverse road in a walled cut with a path crossing over it: the pedestrian bridge spans only the cut
    (deck as wide as the path, piers at the walls) with stairs down each side."""
    road_with_traffic(kit, x, y, yaw, length, width, cars=3)
    for sgn in (-1, 1):
        kit.wall(
            [l2w(x, y, yaw, -length / 2, sgn * (width / 2 + 0.8)), l2w(x, y, yaw, length / 2, sgn * (width / 2 + 0.8))],
            "retaining",
            wall_h,
        )
    kit.bridge(
        x,
        y,
        width + 2 * 0.8 + 3.0,
        path_w + 0.6,
        yaw + math.pi / 2,
        clear_h=wall_h + 1.0,
        deck="flagstone",
        stairs=True,
        span=width + 5.0,
    )
    foot = (width + 1.6 + 3.0) / 2 + 8.61 * (wall_h + 1.6) / 5.3  # where kit.bridge puts the stair foot
    for sgn in (-1, 1):  # the path either side
        a_ = l2w(x, y, yaw, 0, sgn * foot)  # the path starts exactly at the stair foot
        b_ = l2w(x, y, yaw, 0, sgn * 40)
        kit.ribbon([a_, b_], path_w, "pavement")


# ---- bridges ------------------------------------------------------------------------------------------------
@prefab("footbridge_stone", 30)
def footbridge_stone(kit, x, y, yaw, length=20.0, width=4.2, clear_h=3.2):
    """A stone footbridge (brick piers, concrete deck, flagstone surface, stone parapets, stairs) over a path."""
    kit.ribbon([l2w(x, y, yaw + math.pi / 2, -25, 0), l2w(x, y, yaw + math.pi / 2, 25, 0)], 3.6, "pavement")
    kit.bridge(x, y, length, width, yaw, clear_h=clear_h, deck="flagstone", stairs=True)


@prefab("footbridge_wood", 30)
def footbridge_wood(kit, x, y, yaw, length=12.0, width=3.6):
    """A rustic wooden footbridge from the deck-on-posts mesh with stairs, over a stream of water tiles."""
    for u in range(-20, 21, 3):
        px, py = l2w(x, y, yaw + math.pi / 2, u, 0)
        kit.add(WATER, px, py, kit.g(px, py) + 0.3, 1.0, 1.0, 1.0, yaw)
    kit.wooden_bridge(x, y, length, width, yaw, 3.0)


# ---- water features -------------------------------------------------------------------------------------------
@prefab("fountain_basin", 22)
def fountain_basin(kit, x, y, yaw, radius=14.5, rim_h=0.75, figure=True):
    """A round masonry basin: brick ring, water inside below the rim, a pedestal and a figure on top."""
    g = kit.g(x, y) + LAYER["flagstone"]
    kit.surface("flagstone", x, y, radius * 2 + 12, radius * 2 + 12, yaw)
    kit.basin(x, y, radius, rim_h, z_base=g)
    kit.add("NewRow_261", x, y, g + 1.5, 3.0, 3.0, 3.0)  # grey cylinder pedestal, centre pivot
    kit.add("NewRow_261", x, y, g + 3.5, 6.0, 6.0, 1.0)
    if figure:
        kit.add(STATUE_FIGURE, x, y, g + 4.0, 2.4, 2.4, 2.4, yaw + math.pi)


@prefab("shoreline", 30)
def shoreline(kit, x, y, yaw, length=50.0):
    """A pond edge: water tiles subdivided to the shore, bank rocks and a willow."""
    for u in range(-int(length / 2), int(length / 2), 4):
        for v in range(4, 30, 4):
            px, py = l2w(x, y, yaw, u, v)
            kit.add(WATER, px, py, kit.g(x, y) + 0.3, 1.0, 1.0, 1.2, yaw)
    for u in range(-int(length / 2), int(length / 2), 8):
        px, py = l2w(x, y, yaw, u, 1.5)
        kit.add("NewRow_71", px, py, kit.g(px, py), 1.0, 1.0, 1.0, rng.uniform(0, 6.28))
    px, py = l2w(x, y, yaw, 0, -5)
    kit.add("NewRow_171", px, py, kit.g(px, py), 1.0, 1.0, 1.0, 0.0)


# ---- furniture --------------------------------------------------------------------------------------------------
@prefab("path_with_furniture", 30)
def path_with_furniture(kit, x, y, yaw, length=50.0, width=3.6):
    """A paved path with benches facing it on both sides, lamps, a bin and walkers."""
    a_, b_ = l2w(x, y, yaw, -length / 2, 0), l2w(x, y, yaw, length / 2, 0)
    kit.ribbon([a_, b_], width, "pavement")
    for i in range(3):
        u = -length / 2 + (i + 0.5) * length / 3
        for side in (-1, 1):
            bx, by = l2w(x, y, yaw, u, side * (width / 2 + 0.9))
            kit.bench(bx, by, yaw, side)
        lx, ly = l2w(x, y, yaw, u + 6, (width / 2 + 0.6))
        kit.add(LAMP_SHORT, lx, ly, kit.g(lx, ly), 1, 1, 1, yaw + math.pi / 2)
    tx, ty = l2w(x, y, yaw, 2, -(width / 2 + 0.5))
    kit.add(TRASH, tx, ty, kit.g(tx, ty), 1, 1, 1, yaw)
    for i in range(4):
        px, py = l2w(x, y, yaw, rng.uniform(-length / 2, length / 2), rng.uniform(-width / 2 + 0.5, width / 2 - 0.5))
        kit.add(rng.choice(PEOPLE), px, py, kit.g(px, py) + LAYER["pavement"], 1, 1, 1, yaw + (0 if i % 2 else math.pi))


@prefab("kiosk_cluster", 16)
def kiosk_cluster(kit, x, y, yaw):
    """Two market kiosks and a food cart on flagstones with a few customers."""
    kit.surface("flagstone", x, y, 24, 18, yaw)
    kit.kiosk(*l2w(x, y, yaw, -6, 0), yaw)
    kit.kiosk(*l2w(x, y, yaw, 6, 0), yaw)
    cx, cy = l2w(x, y, yaw, 0, -5)
    kit.add("NewRow_246", cx, cy, kit.g(cx, cy) + rest("NewRow_246"), 1, 1, 1, yaw)
    for i in range(5):
        px, py = l2w(x, y, yaw, rng.uniform(-9, 9), rng.uniform(-7, 5))
        kit.add(rng.choice(PEOPLE), px, py, kit.g(px, py) + LAYER["flagstone"], 1, 1, 1, rng.uniform(0, 6.28))


@prefab("playground", 16)
def playground(kit, x, y, yaw):
    """A fenced playground with five pieces of play equipment on a paved pad."""
    pts = [l2w(x, y, yaw, u, v) for (u, v) in ((-12, -10), (12, -10), (12, 10), (-12, 10), (-12, -10))]
    kit.surface("flagstone", x, y, 24, 20, yaw)
    kit.wall(pts, "fence", 1.5)
    for i, row in enumerate(PLAYGROUND[:5]):
        px, py = l2w(x, y, yaw, -8 + i * 4, rng.uniform(-5, 5))
        kit.add(row, px, py, kit.g(px, py) + LAYER["flagstone"] + rest(row), 1, 1, 1, rng.uniform(0, 6.28))


@prefab("gazebo", 10)
def gazebo(kit, x, y, yaw, scale=1.0):
    """The park gazebo mesh on a flagstone pad (scale 2 makes the carousel house)."""
    bw, bl, bh = size(BOWER)
    kit.surface("flagstone", x, y, bw * scale + 4, bl * scale + 4, yaw)
    kit.add(BOWER, x, y, kit.g(x, y) - 0.1, scale, scale, max(1.0, scale * 0.7), yaw)


@prefab("cafe", 12)
def cafe(kit, x, y, yaw):
    """A park cafe building with a terrace of tables and chairs."""
    kit.add(CAFE[0], x, y, kit.g(x, y), 1, 1, 1, yaw)
    kit.surface("flagstone", *l2w(x, y, yaw, 0, 9), 14, 8, yaw)
    for i in range(3):
        tx, ty = l2w(x, y, yaw, -4 + i * 4, 9)
        kit.add("NewRow_353", tx, ty, kit.g(tx, ty) + LAYER["flagstone"], 1, 1, 1, yaw)
        kit.add("NewRow_352", *l2w(tx, ty, yaw, 0, 1.3), kit.g(tx, ty) + LAYER["flagstone"], 1, 1, 1, yaw + math.pi)


@prefab("stairs_and_terrace", 16)
def stairs_and_terrace(kit, x, y, yaw, rise=4.4):
    """A raised terrace (embankment with retaining walls and a parapet) and a real flight of stairs down."""
    g = kit.g(x, y)
    kit.box("concrete", *l2w(x, y, yaw, -10, 0), g + rise - 0.6, 0.6, 20, 20, yaw)
    kit.surface("flagstone", *l2w(x, y, yaw, -10, 0), 20, 20, yaw, z_base=g + rise - 0.6)
    kit.wall([l2w(x, y, yaw, 0, -10), l2w(x, y, yaw, 0, 10)], "retaining", rise)
    kit._raised_parapet([l2w(x, y, yaw, -0.5, -10), l2w(x, y, yaw, -0.5, 10)], g + rise)
    fx, fy = l2w(x, y, yaw, 8.6 * rise / 5.67, 0)
    kit.stairs(fx, fy, yaw + math.pi, rise, 6.0)


@prefab("statue_on_plinth", 6)
def statue_on_plinth(kit, x, y, yaw):
    """A bronze-looking figure on a black plinth (the only statue mesh is a wire globe)."""
    kit.box("black", x, y, kit.g(x, y) - 0.2, 1.8, 1.6, 1.6, yaw)
    kit.add(PEOPLE[3], x, y, kit.g(x, y) + 1.6, 1.4, 1.4, 1.4, yaw)


@prefab("probe_stair_deck", 20)
def probe_stair_deck(kit, x, y, yaw):
    """Measurement probe: a stair and a deck placed by bounding box at yaw 0, with a red cube at the stair's local
    -Y end, a blue cube at its +Y end and a yellow cube at the deck centre, so one screenshot tells which way the
    stair climbs and that place() centres the meshes."""
    g = kit.g(x, y)
    kit.place(STAIR_A, x, y, g, 1, 1, 1, 0.0)
    kit.box("red", x, y - 5.5, g, 1.0, 1.0, 1.0)
    kit.box("blue", x, y + 5.5, g, 1.0, 1.0, 1.0)
    kit.place(DECK_ON_POSTS, x + 20, y, g, 1, 1, 1, 0.0)
    kit.box("yellow", x + 20, y, g + 4.2, 1.0, 1.0, 1.0)
