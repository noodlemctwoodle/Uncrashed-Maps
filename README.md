# Uncrashed map tooling

Generates custom maps for **Uncrashed: FPV Drone Simulator** (Steam app 1682970, Unreal Engine 4.27)
from real-world GIS data, without using the in-game editor by hand.

First map: **NYC** — Midtown Manhattan, the 2 km × 2 km flyable square centred on 5th Avenue and 38th Street
(roughly 28th to 48th Street, 8th Avenue to 2nd Avenue, so the Empire State Building, Times Square, Herald
Square, Grand Central and the Chrysler Building are all in), built from NYC Open Data building footprints with
real roof heights and the city street centreline file with real street widths.

## Playing the map

The build script installs one map, **NYC** (in-game name "New York City - Midtown Manhattan", about 92 000
placed assets plus 2 300 window and billboard decals), straight into the game's local map folder:

```
~/Library/Application Support/Uncrashed/<SteamID64>/MapEditor/User/NYC/
    NYC.json        the map
    NYC.info        name, base level, creator, timestamp
    Thumbnail.jpg   top-down render
    Decals/         240 generated PNG window-grid and billboard textures
```

**Steam Cloud.** The game syncs this folder to Steam Cloud (`steam_autocloud.vdf`). Deleting a map folder on disk
is not enough: Steam restores it from the cloud on the next launch. To remove a map for good, delete it inside the
game, or delete its files on Steam's Remote Storage page for the app
(`https://store.steampowered.com/account/remotestorageapp/?appid=1682970`) and then delete the folder on disk.

Open Uncrashed, go to the Environment & Track Editor, and load it from your local maps. You spawn in the middle
of the 5th Avenue / 38th Street intersection facing the Empire State Building 380 m away. A copy lives in `maps/NYC/`.

## Second map: FPV Airspace Park

`python3 tools/build_fpvpark.py` builds and installs **FPVPark** ("FPV Airspace Park"), a purpose-built freestyle
and race map on the Mountain landscape base level. Every object is placed on the real terrain: `tools/landscape.py`
decodes the level's landscape heightmap textures from the game files (validated: the sampler returns exactly
−15.00 m at the level's PlayerStart), and the flat valley floor it reveals is an irregular bowl of roughly
900 × 750 m. Placement is a designed layout, not a scatter: the road loop is reserved first and is the park's spine; the central
arena holds the chained freestyle features in race order; five themed districts (downtown with the three Neo towers,
dome and mid-rises; farm with hamlet and village; industrial with train yard, crane yard and dive tower; junkyard
with the skatepark; lake with a beach) sit around it inside the flat bowl, each with its own modules and a dressing
pass of themed props, all facing the nearest road piece. Every zone slides at most a set distance to find flat, free
ground and is skipped and counted otherwise. Every object stands on the terrain height at its own position with the
catalog's rest-height correction, vertical members carry a 1 m footing, pads carry a 2 m skirt, and every feature
registers its flight gaps as tubes: props inside a tube are deleted and a structure inside a strict tube aborts the
build. Build-time checks that must pass: all race legs clear, no structure in a strict tube, zero floating objects
(`tools/mapcheck.py`), nothing off the landscape. Density comes from the road dressing (fences, pavements, tree lines,
21 flow gates, crowds), district dressing and forest belts of 22,000 pines ringing the bowl (about 35,000 instances).

**Designed freestyle line.** A 72 m dive spire with holed floors whose holes alternate side (a slalom dive), ledges
on every floor and a split-S platform; a bando with a 30 m gauntlet wing of single-window walls, a 2.5 m column
corridor and a holed roof; three power-loop goalposts at 10, 13 and 16 m plus an overhang slab; a 44 m bridge on
pillars for underpasses and loops; a row of vertical gap panels tightening from 1.6 m to 0.9 m and a 2 m slot wall;
a bent 50 m tunnel; offset container stacks three high with bridged pairs to fly under; a 100 m tree tunnel; an
orbit tower; a pole line; and the arch row, gap field, skatepark, second bando, dive tower and three 300 m towers
with 40 m dive ledges. The bowl is then filled with up to 90 modules (container maze, pipes, tire slalom, hesco
fort, car park, tent camp, hay, rocks, tree ring, tunnel chain, column forest, arches, tank farm, train, picnic,
neon garden, balloons, scaffold cluster, pallet yard, ramp pair, goalposts).

**Race.** 26 gates, 3 laps, planned as straight flight lines (`maps/FPVPark/race_plan.png`): the home straight
through the pit arch, a tall inflatable, then a line-up gate and two one-way gates along the gauntlet wing's first
floor (a 6 m wide, 3.7 m tall corridor beside the hall, open at both ends), a big round gate straight out of it, an
elevated gate and a low gate in the east field, a drop to the lake and an invisible gate 2 m over the water, under
the three rising power-loop bars and the overhang slab in one line, across the jump field and past the skatepark,
round the orbit tower, under the bridge deck between its middle pillars (a round gate at each end to line up), a
40 m climb along the spire's south face, a one-way gate 3 m over its top and a 77 m dive down beside it, then home.
Every feature is flown along its open axis with a gate at each end, so no leg asks for a turn inside a corridor.
`tools/raceline.py` checks every leg (start → gate 1 → … → start) as a straight segment against the oriented
bounds of every placed mesh and the terrain; the build aborts if any leg is blocked at a 1.5 m tube (only the wing
is tighter than 2 m). Storage follows what 17 Workshop tracks all do: start and gate yaw = flight bearing − 90°
(the gate's local +Y is the flight direction, which is also why one-way gates face the right way), gate heights
from the gate table's pivot and detection-box offsets (`data/gate_bounds.json`), respawn point 0 at the start and
respawn i at gate i−1 with the gate's yaw, 0.5 m below it. No Workshop track stores a STARTGATE checkpoint; the
in-game start actor (`BP_StartRace`: a Gate2 mesh plus `GateStart2`, detection box at the pivot) comes from
`StartTransform`, and in every Workshop track gate 1 lies exactly on the start's local +Y axis. Respawn point 0 is
placed 12 m behind the start line facing it, so the drone crosses the start gate first (half the hand-made Workshop
tracks move it to gate 1 instead; the other half leave it at the start). Workshop tracks scale the 2 m gates up to
5.5x, so gates here are scaled: 6 m Default/OneW gates in the open, 3 m inside the wing, 5 m under the bridge,
inflatables 1.5x, and no opening lower than 2.5 m (the valley floor undulates up to 1.5 m).

**Rookie race.** `python3 tools/build_fpvpark.py --rookie` installs a second map, **FPVParkRookie** ("FPV Airspace
Park: Rookie"): the same park with a 20-gate beginner race of big, low inflatables (1.5x InflSimpl, openings 2.5 m)
down the home straight and round the road loop vertex by vertex, so every leg follows the road through its flow
gates with no structure to thread (`maps/FPVParkRookie/race_plan.png`).

**FPV Airspace advertising.** Twelve two-sided 24 m billboards spaced along the road loop and facing it, each in a
clearing, plus one facing the start line; a Hollywood-style "FPV AIRSPACE" in 3 m cubes standing on the slope
north-east of the bowl; a "FPV-AIRSPACE.APP" cube sign beside the pits; cube lettering on the start arch; and the
fly-through logo. Billboard artwork is PNG decals (your app icon and README strapline) written to the map's
`Decals/` folder and copied into the editor's `MapEditor/UserDecals/` and `MapEditor/MapDecals/` libraries, which
is where its UI blueprint loads user PNGs from (`--no-decals` to skip). Decal basis as described under the NYC
windows below.

## Regenerating

```bash
python3 tools/build_nyc.py
```

Window-grid and billboard decals are part of the map (pass `--no-windows` to leave them out). They use the
editor's custom-decal loader, the same mechanism Workshop maps use for user PNG decals.

Needs only the system Python (plus Pillow for the thumbnail, which is optional). Input data is already
in `data/`. To refresh it, the datasets are:

- Buildings: `https://data.cityofnewyork.us/resource/5zhs-2jue.json` (fields `the_geom`, `height_roof` in feet,
  `construction_year`, `bin`)
- Parks: `https://data.cityofnewyork.us/resource/enfh-gkve.json` (`multipolygon`, `signname`, `typecategory`)
- Land (shoreline-clipped 2020 census tracts): `https://data.cityofnewyork.us/resource/63ge-mke6.json`
- Streets: `https://data.cityofnewyork.us/resource/inkn-q76z.json` (fields `the_geom`, `streetwidth` in feet,
  `stname_label`, `trafdir`, level codes)

All are queried with `$where=intersects(the_geom,'POLYGON((...))')` and paginated with `$limit`/`$offset`. The
whole-board datasets (`data/ring_*.json`, `data/land_tracts.json`) use a square of ±4.3 km around the spawn because
the 6 km board is rotated 44° from north and its corners reach 4.2 km.

## Third map: Central Park

`python3 tools/build_centralpark.py` builds and installs **CentralPark** ("New York City - Central Park") from
OpenStreetMap on the flat Empty board. `tools/osm.py` turns an Overpass dump (`data/centralpark_osm.json`, not in the
repo; fetch it with the query in the script) into `data/centralpark_features.json`: polygons (water with islands,
lawns, woods, rock outcrops, plazas, buildings with heights), lines (paths, drives, transverses, arches) and points
(5,000 mapped trees, benches, lamps, statues). The frame (`data/centralpark_frame.json`) puts the origin on the Mall at
the Literary Walk with the Mall running up −Y, so the freestyle spawn looks straight up the elm walk to Bethesda
Terrace. Every lake and pond is tiled with water, every path and drive is paved along its real geometry, the 19
mapped arches and bridges are raised decks on stone abutments you can fly under, and landmarks OSM only names are
modelled on top: the Mall's four elm rows, Bethesda Terrace with its arcade, twin stairs and the Angel fountain,
Belvedere Castle on a Vista Rock mound over Turtle Pond, the Obelisk, Bow Bridge, the Carousel, Delacorte, the
Bandshell, Tavern on the Green, Cherry Hill, the Imagine mosaic (a decal), the Reservoir's fence and the Sheep Meadow
fence. The surrounding city uses OSM footprints and heights (supertalls by name) with window decals only on faces that
look at the park. About 61,000 instances; `--lite` drops sidewalks, roof clutter and distant small buildings.
Reference imagery: `data/centralpark_naip.png` (USGS NAIP, public domain). OSM data © OpenStreetMap contributors, ODbL.

## How the map is built

- The **Empty board** base level (`BaseMapRow: BaseBoard`) is a flat 6 km landscape at Z = 0.
- Freestyle maps (`Track: false`) ignore `Race.StartTransform`; the drone spawns at the base level's PlayerStart,
  which on the Empty board is the world origin facing yaw −90° (−Y). The map is therefore centred on the
  5th Avenue / 38th Street intersection and the whole frame is rotated 44° so −Y points at the Empire State Building.
- Coordinates are Unreal centimetres, Z = up; north is at yaw 44° (stored in `CustomWeather.northyaw`).
- The board's `MapSettings` actor defines a 2000 × 2000 × 1500 m flyable range box around the origin; buildings
  and streets outside it are dropped.
- Every building footprint becomes one rectangle when its minimum-area rectangle covers at least 74 % of the
  polygon. Otherwise the footprint is rasterised in the rectangle's frame and greedily split into up to
  twelve rectangles, so L- and U-shaped buildings keep their shape.
- Named buildings in the footprint data (landmarks such as the New York Public Library, hotels, churches) always keep
  stone box massing. Other rectangles up to 60 m tall are tiled with the editor's textured building meshes (four office blocks from
  the ParkingGarage pack, a brick low-rise and an old workshop) whenever a grid of them fits within 30 %
  non-uniform scaling, stacking up to three high. About a third of the buildings get real windows this way.
- Everything else is a box. Materials come from age and height: triplanar brick for low pre-war buildings,
  triplanar concrete for pre-war towers (reads as limestone), grey for post-war mid-rise and dark black for
  post-war glass towers. Pre-war towers between 45 and 250 m get 1916-zoning "wedding cake" setbacks.
- Roofs get New York clutter: wooden-style water towers (the farm silo asset scaled down), elevator
  bulkheads and a parapet wall on masonry buildings.
- The Empire State Building (381 m roof, antenna to 443 m), Chrysler Building (spire to 319 m) and
  One Vanderbilt (427 m) get hand-tuned stepped massing.
- Streets are thin black boxes along each centreline segment at the recorded width, with raised concrete
  sidewalks on both sides trimmed at the intersections. Avenues sit 1 cm above cross streets to avoid
  z-fighting. Two-way streets get a yellow centre line. Elevated segments (Park Avenue viaduct) are skipped.
- Sidewalk widths are measured per street side so the pavement reaches the building line. Lane lines and
  ladder crosswalks are thin white boxes.
- Street furniture: elms and maples along the kerbs, tall floodlight poles on avenues and short lamps on
  side streets (night-light blueprints), yellow Camaros as taxis plus white cars and vans in the lanes,
  pedestrians (the editor's pilot figures) on every sidewalk, trash cans, food carts, benches, planters and
  fuse boxes, seventy scaffolding sidewalk sheds with cones and pallets around them.
- Void filling: a 2 m coverage grid finds every patch inside the built-up area that is neither building nor
  street. Small ones become rear yards (dumpsters, pallets, barrels, bushes), large ones become parking lots
  (asphalt, parked cars in rows, a lamp) or plazas (trees, benches, planters, people).
- Parks come from the NYC Parks Properties dataset (`enfh-gkve`, saved in `data/midtown_parks.json`) and are
  laid out before the void filler runs so nothing else lands on them. Neighbourhood parks get lawns, trees,
  benches and people; playgrounds get a concrete base, play equipment and a chain-link fence; triangles and
  plazas get planters, cafe furniture, trees, people and a statue; the Park Avenue malls become planted
  medians. Bryant Park is laid out by hand on top of its polygon: gravel base, the Great Lawn with people and
  chairs on it, two rows of plane trees along each long side with tables and chairs beneath, the fountain at
  the west end, kiosks and lamps.
- Building rectangles are snapped to the Manhattan street grid whenever the grid-aligned bounding box is
  within 18 % of the minimum-area one, so near-square footprints no longer come out at odd angles.
- Signage is placed only on true ground-level box facades (never on the textured meshes or set-back tiers,
  whose real walls differ from the bounding box), at most three varied screens per facade.
- FPV features: four construction sites with open concrete skeletons (floors on columns, no walls), tower
  cranes, scaffolding, fencing and plant; three open multi-storey parking decks with ramps and parked cars;
  a dozen glazed skybridges between facing towers; and the elevated Park Avenue viaduct around Grand Central,
  built from the centreline file's elevated level codes (17, 21, 22) with ramps, parapets and piers.
- The whole 6 km board is used. The central 2 km square has full detail. The mid ring (1 to 2 km) has every
  building over 5 m as a box, roads with sidewalks and street trees, and parks with grass and trees. The outer
  ring (2 to 3 km) has buildings over 14 m, roads and parks. Union Square, Madison Square Park, Washington
  Square and the south end of Central Park fall in these rings.
- Ground surfaces are the editor's textured 4 m ground planes (`SM_BaseGround_0-1` rows with triplanar
  materials): asphalt for roads and parking, pavement for sidewalks and plazas, gravel for park paths, dirt for
  construction sites. These are the rows Workshop maps use for the same purpose.
- Lawns are a plain green surface. The editor's grass blueprint (`Bp_Grass_C`) uses a wind-animated grass
  material with no macOS override (the asset table ships "no wind" Mac materials for every tree and bush but
  not for the grass), and it renders untextured grey on a Mac, so it is not used.
- Rivers use the water blueprint (`BP_meWater_C`, a 4 m × 4 m × 2.1 m volume whose pivot is the water surface),
  placed as 100 m tiles wherever neither the shoreline-clipped census tracts nor a park polygon shows land
  (the 2020 tracts leave Central Park uncovered). The size and pivot come from
  the blueprint's own component and mesh bounds, read from the game files.
- Park polygons that cross the board edge (Central Park) are clipped to the board before layout.
- Parks get gravel perimeter and cross paths, lamps, benches along the paths, dense trees and bushes, planters
  and people. The south end of Central Park alone has several hundred trees.
- Times Square: Broadway from 42nd to 47th is a pedestrian plaza with cafe tables, chairs and planters, the
  facades facing the bowtie carry grids of LED screens plus a few giant ones and neon tubes, and the red
  TKTS steps with people sitting on them stand at Duffy Square. Herald Square (Broadway 33rd to 35th) gets
  the same plaza treatment plus statues and screens.
- Window decals: for every plain box facade at least 30 m tall that is not a party wall against a neighbour,
  a decal is projected onto the face with a generated window-grid PNG (punched windows on masonry, curtain
  wall on glass towers), and Times Square facades get generated billboard decals. Decal basis, which matches
  editor-placed wall decals in Workshop maps exactly and Unreal's deferred-decal shader (texture U along local
  Z, V along local Y, projection along +X): X points into the surface, Y straight down, Z = X × Y along the
  wall; scale X = depth, Y = height / 4, Z = width / 4 (the editor's decal size is 4 m). PNGs are copied into
  the editor's `MapEditor/UserDecals/` and `MapEditor/MapDecals/` libraries, which is where it loads them from.

`tools/preview.py <map.json> <out.png> [cx cy radius]` renders an oblique preview of any map without the game.
`tools/raceline.py <map.json> [--clearance m]` reports every race leg that a mesh or the terrain blocks,
`tools/racemap.py <map.json> <out.png> [half-size m]` draws the race plan (footprints, numbered gates with
opening heights, straight legs, start arrow) top-down, `tools/mapcheck.py <map.json>` lists floating, buried and
off-landscape objects, and `tools/bounds_fix.py` completes `data/catalog.json` with bounds for basic shapes and
blueprint rows (union of their component meshes). `data/gate_bounds.json` holds each gate row's pivot and
detection-box offset. The heightmap sampler was validated against six player-built Workshop maps on the Mountain
landscape (ground objects within 0.1 m). The measured conventions (gate yaw, pivots, decal basis, placement rules) are summarised in this README and in the tool docstrings.

## Map file format (reverse engineered)

A map is a folder containing `<Name>.json`, `<Name>.info` and `Thumbnail.jpg`. Workshop downloads add
`Steam.wrk` and an optional `Decals/` folder. The JSON has these top-level keys:

| key | content |
|-----|---------|
| `S_AssetsTransform` | list of `{Rname, Transform[], UniqueGroupTag[]}`; one entry per asset row, one transform per instance, tags are `"None"` |
| `BaseMapRow` | row name in `DT_LevelName` (`BaseBoard`, `BaseLandscape`, `BaseLandscape02..04`, `MountainOpen`, `DriftTrack`, ...) |
| `WeatherIndex` | integer weather preset |
| `Race` | `CheckPoints[]`, `StartTransform`, `Laps`, `BestTime`, `Spoints[]` |
| `CamLoc` | menu camera transform |
| `CustomWeather` | `timeOfDay`, `northyaw`, `Cloud` (optional) |

Transforms are `{Rotation: quaternion XYZW, Translation: cm, Scale3D}`; the translation is the actor
pivot, so the cube is placed by its centre, the brick wall by its base and the concrete floor by its top.

`Rname` values are rows of the game's `DT_MapEditorAssets` DataTable. The rows used here:

| row | mesh | base size | pivot |
|-----|------|-----------|-------|
| `NewRow_13` / `_46` yellow / `_79` blue / `_84` red / `_268` green / `_256` grey / `_378` violet / `_109` black | `SM_Cube` | 1 × 1 × 1 m | centre |
| `NewRow_14` / `_64` / `_81` / `_89` / `_272` / `_261` grey / `_380` / `_113` black | `SM_Cylinder` | 1 m diameter, 1 m tall | centre |
| `NewRow_303` | `SM_ConcreteFloor01`, triplanar concrete | 4 × 4 × 0.30 m | top (z from −0.29 to +0.01) |
| `NewRow_318` | `SM_ConcreteWall01`, triplanar brick | 0.3 × 4 × 4 m | bottom centre |

`data/catalog.json` lists all 804 rows with mesh path, category and bounding box (metres = values / 100).

## Tools

| script | purpose |
|--------|---------|
| `tools/pakread.py` | minimal reader for the game's `.pak` files (version 11, unencrypted, Zlib); lists every file |
| `tools/pakextract.py` | extracts files matching a substring from the paks |
| `tools/uasset.py` | reads cooked UE4.27 `.uasset`/`.uexp`: names, imports, exports, tagged properties, DataTable rows |
| `tools/build_catalog.py` | dumps `DT_MapEditorAssets` and reads each mesh's bounds into `data/catalog.json` |
| `tools/build_nyc.py` | builds and installs the NYC map |

Extracted game assets are ignored by git; everything in `data/` that is committed is either public data
or metadata derived from the game.
