---
name: blender-environment-kits
description: Game environments in Blender 5.2 - terrain from noise or heightmaps (erosion, terraces, play areas, slope/height materials, 16-bit heightmaps + splat maps for UE/Unity), biome scatter by slope/height/mask with Poisson spacing, modular kit metrics and validation (grid, pivots, seams, texel density). Use for levels, landscapes, forests, modular buildings, dungeons.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.2.0"
---

# Environment kits

The execution model is in `blender-core`. Custom GN tools are in `blender-geometry-nodes`, materials in `blender-texturing` (trims, vertex blends), and mood/weather in `blender-time-of-day`/`blender-weather-fx`.

## One call each
```
scripts/terrain.py -- --size 400 --res 513 --height 60 --type ridged --erosion 30 --flatten 0 0 40 --material
scripts/terrain.py -- --heightmap //hm.png --size 1000 --res 1009 --height 120 --export-splat //T_Splat.png
scripts/scatter.py -- --target Terrain --collection Trees --density 0.02 --min-distance 5 --max-slope 25 --height-max 45
scripts/scatter.py -- --target Terrain --collection Rocks --density 0.05 --max-slope 70 --align 0.8 --name ENV_Rocks
scripts/kit_check.py -- --objects SM_Wall_4m SM_Floor_4m SM_Door_4m --grid 0.5 --fix
```

## Terrain (terrain.py)
- Grid of `--res`² verts over `--size` m. Use **2^n + 1** for Unity (513/1025/2049, `.raw` 16-bit LE) and UE Landscape's recommended sizes (505/1009/2017/4033, 16-bit PNG). Above 1025, tile it.
- `--type fbm` (rolling), `ridged` (mountains), `hills` (hetero terrain). `--scale` = feature size m. `--erosion N` = thermal erosion steps (talus 33°): slopes relax and debris fills valleys. `--terrace` m = stepped flats. `--flatten X Y R` = a level play/build area blended back with a smoothstep.
- Writes `ENV_Slope` (deg/90) and `ENV_Height` (0–1) point attributes. `--material` builds grass/rock/snow from them: rock above 35°, snow above 75% height on slopes below ~40°, with noise-broken edges.
- Engines: `--export-heightmap` (PNG = 16-bit gray, `.raw` = 16-bit little-endian, row 0 = −Y edge; flip vertically in Unity if mirrored) plus `heightmap_z_scale_m` for the import Z scale. `--export-splat` = 16-bit RGBA weights (R grass, G rock, B snow, sum 1) for terrain layers. Both are written Raw (no display transform): measured round-trip error < 0.001.

## Scatter (scatter.py)
- One GN modifier per layer: Poisson disk (`--density` per m² max, `--min-distance` m), kept where the **interpolated surface normal** is within `--max-slope` and Z is inside `--height-min/max` (object space). `--mask` = vertex group or float attribute as density factor (paint it, or use `ENV_Height`).
- Collection children are instanced at their own origins with random yaw, `--scale` range, and `--align` (0 = upright trees, 0.6–1 = rocks hugging the slope). The source collection is excluded from the view layer.
- The result checks every instance against the real surface (`slope_max_deg`, `height_range`) and counts per source. Instances stay instances. `--realize` only when an exporter or boolean needs real mesh.
- Densities: forest trees 0.01–0.05/m² (min distance 4–8 m), bushes 0.05–0.2, rocks 0.01–0.1, grass clumps 2–20/m² (near camera only). Layer big → small: trees, then bushes masked away from trunks, then grass.
- Engines: glTF `export_gpu_instances=True` (EXT_mesh_gpu_instancing), or `--export-points file.json` (world transforms, Z-up m, wxyz quats) for UE foliage/PCG or Unity instancing scripts. FBX needs realized geometry or one object per instance.

## Modular kits (kit_check.py)
- **Metrics first**: pick a grid (0.5 m snap, 1/2/4 m modules) and keep it everywhere. Walls 3–4 m tall interior (player ~1.8 m eye 1.6 m, doors ≥ 1 × 2.2 m), floors 4 × 4 m, stairs 0.18 m rise / 0.28 m run. UE works in cm (×100 on import), Unity in m.
- **Pivot** convention (`--pivot corner` default, `bottom-center`, `center`) so pieces snap by increments. Footprint lengths are multiples of the grid. Thinner-than-a-cell dims (wall thickness, trims) may be off-grid.
- Open edges only on the piece's outer faces (seams); holes inside are errors. Seam verts must be on the grid so neighbours weld visually. Texel density within 25% of the kit median (`--texture` px). `SM_` names (`--prefix`).
- `--fix` applies rotation/scale and moves each origin to the pivot without moving geometry. Linked duplicates share mesh data, so fix the source once.
- Break repetition with trims and decals (`blender-texturing`), vertex-color blends, and rotated/mirrored variants (mirrors flip normals, so check with `blender-asset-qa`). Hide seams with trim pieces over joints.

## Gotchas
- Apply terrain/kit scale before scattering. Densities and slopes are world-based.
- Scatter height is in the target's object space. Keep terrains at the origin or offset `--height-*`.
- Huge Poisson counts are slow. Scatter per tile/area, or lower the density in the viewport and raise it for renders.
- Validate terrain + scatter with `blender-asset-qa` (floating instances on cliffs, z-fighting decals) and `blender-game-optimization` (instances, LODs, draw calls).
