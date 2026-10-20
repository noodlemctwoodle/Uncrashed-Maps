---
name: uncrashed-maps
description: Build, validate and install custom maps for Uncrashed FPV Drone Simulator (UE 4.27) from this repo. Use for any map generation, race/gate, placement, decal, landscape or asset-table question about Uncrashed; every fact here was measured from the game files or from player-built Workshop maps, not guessed.
---

# Uncrashed map building

Everything below was verified against the game's pak files, the editor data tables, or Workshop maps built by
players in the real editor. When something is not covered here, measure it the same way (see "How to verify")
before using it. Never assume a mesh pivot, a rotation convention or a limit.

## Where things live (this Mac)
- Game: `~/Library/Application Support/Steam/steamapps/common/Uncrashed FPV Drone Sim/Uncrashed-Mac-Shipping.app`
  (paks under `Contents/UE4/Uncrashed/Content/Paks`, pak v11, unencrypted, Zlib). Extracted assets: `data/extracted/`.
- Maps the game loads: `~/Library/Application Support/Uncrashed/76561197969360950/MapEditor/User/<Name>/`
  (`<Name>.json`, `<Name>.info`, `Thumbnail.jpg`, optional `Decals/`). Decal PNGs must ALSO be copied to
  `MapEditor/UserDecals/` and `MapEditor/MapDecals/` or they render blank.
- Workshop maps (ground truth for conventions): `~/Library/Application Support/Steam/steamapps/workshop/content/1682970/`.
- Steam Cloud restores deleted map folders; delete in-game or at the Steam remote-storage page for app 1682970.

## File format (measured)
- `S_AssetsTransform`: `[{Rname, Transform:[{Rotation{X,Y,Z,W}, Translation{cm}, Scale3D}], UniqueGroupTag}]`.
  `Rname` = row of `DT_MapEditorAssets` (804 rows, `data/dt_assets.json`; bounds/pivots in `data/catalog.json`).
- `Race`: `CheckPoints[{Transform, RowName}]`, `StartTransform`, `Laps`, `BestTime`, `Spoints[]`. `.info`:
  `{BaseMapRow, Name, CreatorSteamID, CreationTimeUnix, Track}`. `Track:false` maps ignore `StartTransform` and
  spawn at the base level's PlayerStart (world origin; BaseBoard faces yaw -90, BaseLandscape04 too).
- Base levels: `BaseBoard` flat 6048 m at Z 0 (flyable box 2 km around origin); `BaseLandscape04` "Mountain"
  2580 m, valley floor exactly -15.00 m at the origin, flat only inside an irregular bowl of about X -300..+220,
  Y -250..+260 for large zones (`data/flat_cells04.json`); `BaseLandscape02` grassy 2.42 km.
- Landscape heights: `tools/landscape.py` decodes the heightmap textures (`height = loc.z + (h-32768)*scale/128`).
  Validated against six Workshop maps built on BaseLandscape04: ground-standing objects sit at 0.00-0.08 m
  (sd 0.04-0.26). `height_cm` returns None off the landscape: skip those points, never fall back to -15 m.

## Rotations and conventions (measured on 17 Workshop tracks)
- Quaternion yaw: `Z = sin(yaw/2), W = cos(yaw/2)`. Coordinates are UE cm, Z up, left-handed cross product.
- Race: start yaw AND every gate yaw = flight bearing MINUS 90 deg (the gate's local +Y is the flight
  direction). +90 looks the same for two-sided gates but reverses every one-way gate and the pilot stand.
  `Spoints[0]` is at the start; `Spoints[i]` sits at gate i-1 with the gate's yaw, 0.5 m below its centre. No
  Workshop track stores a STARTGATE checkpoint; the pilot stand comes from `StartTransform`.
- In-game start actor `BP_StartRace` = Gate2 mesh + GateStart2 at `StartTransform`, detection box at the pivot;
  gate 1 lies on the start's local +Y in every Workshop track. Put respawn 0 behind the start line (12 m here).
  Checkpoint `Scale3D` is honoured: Workshop scales 2 m gates up to 5.5x (Gate2 types in X/Z, inflatables uniform);
  the detection-box offset scales with it. Keep every opening >= 2.5 m above ground on BaseLandscape04.
- Gate opening centre = pivot translation + the row's BoxDetect offset (`data/gate_bounds.json`): DefaultGate,
  DefaultOneW, Invisible, InflRond02 translate at their centre (pivots -100/-150/-173 cm); inflatables are
  ground-pivoted with the opening 1.5 m (InflSimpl), 3.8-4.8 m (InflDive/InflElev/InflRound01) up.
- Decals (`BP_ME_Decals`, DecalSize 7.5x200x200): basis X into the surface, Y world-down, Z = X x Y; scale
  (depth, height/4, width/4); PNG upright; row name = PNG filename. User-confirmed.

## Mesh pivots and bounds
- `data/catalog.json` now has bounds for every row except decals: static meshes from `ExtendedBounds` (basic
  shapes omit `Origin`; treat as 0), blueprint rows from the union of their StaticMeshComponent meshes
  (`tools/bounds_fix.py`), four estimates flagged `bounds_est` (electric poles, Megascans pipe, Maple08).
- Basic shapes (SM_Cube, SM_Cylinder, SM_CubeHole, SM_Pente) are 1 m, centre pivot. Ground planes
  (SM_BaseGround_0-1) 4x4x0.1 m centre pivot. BP_meWater 4 m tile, pivot AT the surface, 2.1 m deep.
  SM_ConcreteFloor01 (R303) 4x4x0.3, pivot at the TOP. Brick wall R318 0.4x4x4 base pivot. Window walls 4x4 base.
- Meshes whose base is ABOVE the pivot hover if placed at ground height (train boxcar +0.68 m). Meshes whose
  base is below the pivot are meant to sink a little (trees -0.2..-0.5, houses -0.3..-0.5, buildings -1.2..-1.35,
  rocks -0.3..-0.5, dome R118 is centre-pivot -31 m). `put()` in `tools/build_fpvpark.py` applies the
  catalog `rest()` correction automatically.
- The editor's `PivotPointOffset` column is NOT applied by the game to stored transforms (R303 says -30 but
  Workshop floors sit with their top at the translation). Trust mesh bounds, not that column.
- Bp_Grass renders grey on Mac (no Mac material override): use green cubes for lawns.

## Placement rules that stop the known bugs
1. Floating objects: place every object at the ground height of ITS OWN (x, y), never at the zone centre's.
   Vertical members use `post()` (1 m footing sunk into the ground). Pads over uneven ground get a 2 m
   concrete skirt. Props on upper floors only where a floor tile exists. People never get a dz guess.
2. Blocked gaps: every feature registers its flight gap with `tube(x0,y0,z0,x1,y1,z1,r,strict)`; the clearance
   pass deletes every prop inside any tube; `strict` tubes also abort the build if a structure is in them.
3. Random placement: nothing is scattered on arbitrary flat cells. Zones belong to the central arena or to a
   named district, slide at most `max_slide` m to find flat free ground (skipped and counted otherwise) and
   modules face the nearest road piece (`road_yaw`). Zones are placed big-first; gates are placed relative to
   the recorded `ZONE_AT[name]` positions, never the design coordinates.
4. Order: arena features -> race gates (relative to `ZONE_AT`) -> corridor reserved -> districts, landmarks,
   modules, dressing, scatter -> clearance -> checks. Anything placed before the corridor exists can land on the
   race line, and structural rows (cubes, floors, walls, containers, scaffolds) are never deleted by the
   clearance pass, so the build fails instead of hiding the collision.
5. Race lines: every leg start->gate1->...->start is a straight segment; `tools/raceline.py` tests it against
   every mesh OBB (1.5 m tube, floors >1 m below the line exempt) and the terrain. Features are flown along
   their open axis with a gate at each end. Build aborts if any leg is blocked.
6. Density/flow: the road loop is the spine (fences, pavements, tree lines, flow gates every 60 m, crowds at
   corners, billboards facing the road), districts are dressed with themed props, forest belts ring the bowl.

## Data pipeline for real places
- OpenStreetMap via Overpass (`https://overpass-api.de/api/interpreter`, send a User-Agent or you get 406; retry on
  502 with backoff) gives everything in one pull: buildings with `height` (NYC import), water with islands, lawns,
  woods, rock, paths with `bridge`/`tunnel`/`width` (widths can be feet-and-inches), trees with `genus`, lamps,
  benches, statues. `tools/osm.py <dump> <out> <lat0> <lon0> <axis_deg>` converts to local metres (+X west, +Y
  south when flip_north) with multipolygon assembly; set the frame so the spawn (origin, facing -Y on BaseBoard)
  looks along the map's main axis. NYC Open Data (Socrata) is the fallback for building heights.
- Aerial reference: USGS NAIP `imagery.nationalmap.gov/.../USGSNAIPImagery/ImageServer/exportImage` (public
  domain; request a size with the bbox's Mercator aspect or the image is stretched). NYC's own tile service moved
  behind api-portal.nyc.gov.
- Asset library: `tools/build_index.py` -> `data/asset_index.json` + `docs/ASSETS.md` (all 804 rows: size, pivot,
  base offset, collision, physics, Mac material, tags); query with `tools/assets.py` (`find('tree', max_h=12)`,
  `rest(row)`). Editor categories: Small_assets, Wall, Foliage, Interractive, Small structure, Big structure,
  Basic shape, Big_assets, Custom, Decals, Tools, Institutional, Gates.
- Public repo: https://github.com/noodlemctwoodle/Uncrashed-Maps. Never commit `data/extracted`, thumbnails, pak
  listings or raw dumps (see .gitignore); keep personal paths out of code (Steam ID via UNCRASHED_STEAM_ID).

## Workflow
1. `python3 tools/build_fpvpark.py` (add `--rookie` for the beginner-race map FPVParkRookie) builds, validates (race legs, strict tubes, floaters, off-landscape) and
   installs FPVPark; it prints `zones:` (actual positions) and `stats:` (what was skipped). Fix skips by
   moving/shrinking zones, not by relaxing checks.
2. Visual checks without the game: `tools/racemap.py` (top-down race plan), `tools/preview.py` (oblique),
   `tools/mapcheck.py` (floaters/buried), `tools/raceline.py <json> --clearance 2.0` (margin).
3. NYC: `tools/build_nyc.py` (GIS city), Central Park: `tools/build_centralpark.py` (OSM; `--lite`), see README.

## How to verify a new fact
- Mesh/pivot: `tools/uasset.py` `Asset(path).read_props(...)['ExtendedBounds']` after `tools/bounds_fix.py`-style
  extraction; cross-check with Workshop usage (`BaseBoard` maps have ground at Z 0).
- Conventions: measure across all Workshop maps (`glob` the folder above), never from one map.
- Rendering questions (materials, decals): only the game can answer; ask the user for a screenshot.
