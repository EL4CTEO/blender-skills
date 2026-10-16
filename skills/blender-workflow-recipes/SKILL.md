---
name: blender-workflow-recipes
description: End-to-end Blender 5.2 playbooks chaining the blender-* skills with QA gates - game props (mid-poly, high-to-low), game characters (sculpt/AI mesh to rigged, animated export), Roblox props/accessories/avatars, AI or downloaded asset cleanup, procedural environments, web/AR assets, product turntables, mood/weather shots (night, rain, snow, fog). Use for complete multi-stage asset requests.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Workflow Recipes

`S` = the skills folder. Every `.py` runs headless via `python S/blender-core/scripts/run_in_blender.py --blend F.blend S/<skill>/scripts/<x>.py -- ...`, or live via MCP import + `run()` (see `blender-core`). **Gate** = stop and fix before continuing. Save after every stage (`--save`).

## 1. Game prop, mid-poly (fast, no bake)
1. Blockout at real scale (`blender-hardsurface-modeling`). Gate: `ob.dimensions` vs reference.
2. UV the blockout **before** beveling (the Bevel/Boolean modifiers carry UVs): `uv_pack.py --objects SM_X --method seams --seams-from-sharp 60` → `texel_density.py --res 2048 --set 512`
3. `apply_stack.py --objects SM_X --preset midpoly [--cutters ...]` (keep it live; `--apply --triangulate` only on the export copy)
4. Materials: `build_pbr_material.py --preset ...` or tiling/trim textures.
5. Gate: `qa_check.py --objects SM_X --profile game` passes, plus `look` (angles, material + wireframe).
6. `mesh_stats.py --budget <platform>` → `make_lods.py --objects SM_X --rename`
7. `export_asset.py --preset <engine> --objects SM_X_LOD0 SM_X_LOD1 ...` Gate: re-import dims / GLB summary.

## 2. Game prop, high → low baked (hero quality)
1. High poly: hardsurface `--preset subd` or sculpt (`sculpt_ops.py`), named `X_high`.
2. Low: `auto_retopo.py --objects X_high --tris N --method planar|decimate|quadriflow`, or manual. Rename it `SM_X`.
3. `uv_pack.py --objects SM_X --method seams --seams-from-sharp 60 --margin-px 16`
4. Gate: `qa_check.py` on `SM_X` (game) **and** `X_high` (render profile, no inverted parts).
5. `bake_maps.py --low SM_X --high X_high --maps normal ao curvature id --pack-orm [--directx for Unreal]`
6. `build_pbr_material.py --name M_X --textures //textures --objects SM_X` (+ basecolor/roughness from texturing).
7. Gate: `look` in material shading (no seams/waviness), then steps 6–7 of recipe 1.

## 3. Game character (sculpt or AI mesh → animated export)
1. Source mesh (sculpt / `generate_3d` / scan) at real height, facing -Y, feet on Z=0. Run `qa_check.py --profile render`.
2. `auto_retopo.py --method quadriflow --tris 20000` (or manual retopo for heroes, keeping the edge flow rules). `uv_pack.py --method min_stretch`.
3. `bake_maps.py --low Body --high Body_src --maps normal ao basecolor` (basecolor via emission override if the source has colors/materials).
4. `rigify_build.py --add basic_human --fit Body` → place joints (look xray) → `--metarig META_Body --generate`
5. `bind_mesh.py --armature RIG_Body --meshes Body` → `stress_poses.py --armature RIG_Body` → `look(mode="frames")`. Gate: no collapse at the elbows/knees/shoulders. Fix weights.
6. `rigify_build.py --rig RIG_Body --game-skeleton` → `rig_check.py --armature GAME_RIG_Body --profile unity|unreal`
7. Animate on RIG_Body (`blender-animation`) → `bake_action.py --source RIG_Body --target GAME_RIG_Body [--root-motion xy --hips spine]`
8. `export_asset.py --preset unity_skeletal|unreal_skeletal --objects GAME_RIG_Body` (meshes are included as children). Gate: GLB/FBX summary shows skins + all clips. Engine scale check.

## 4. Roblox
- **MeshPart prop**: recipe 1 with `--profile roblox` in QA (≤20k tris, watertight, no n-gons, single UV 0–1), separate grayscale maps (no ORM), `export_asset.py --preset roblox` (FBX) or `roblox_gltf`. Textures 1024² (PBR).
- **Rigid accessory**: ≤4k tris, an attachment point empty matching an R15 `_Att` name, `--preset roblox`.
- **Layered clothing**: start from Roblox's official cage templates. Build `<Name>_InnerCage`/`_OuterCage` (never change cage vertex count/order/UVs), skin to R15 bones, ≤4 influences, no weights on Root. Validate in Studio's Accessory Fitting Tool.
- **Avatar body**: 15 `_Geo` parts, R15 skeleton, attachments, outer cages, 10,742 tri budget. Read `blender-export-pipelines/references/roblox.md` first.
- Upload: Studio `AssetService:CreateAssetAsync` for batches.

## 5. Cleaning AI-generated / downloaded assets
1. Import (`import_asset` / `generate_3d` / file). Scale to real size (`world_bounding_box`), origin to the bottom, ground at z=0, `transform_apply`.
2. `scene_audit.py --fix purge scale` → `qa_check.py --profile game`. Typical findings: non-manifold, duplicate verts, inverted islands, floating debris, z-fighting shells.
3. Fix: `make_lods.py --cleanup` (merge/degenerate/loose), recalc normals, delete floating debris (or `remesh` via `sculpt_ops.py` for garbage topology), then `auto_retopo.py --method decimate` to budget.
4. Re-UV if the UVs are fragmented (`uv_pack.py`) and re-bake from the original (`bake_maps.py --high original`).
5. Gate: QA passes + `look`. Never ship generated meshes unreviewed.

## 6. Procedural environment
1. Terrain/ground mesh, then a scatter tree with `gn_builder.py --spec scatter.json --apply Ground --set Density=... Seed=...` (recipes in `blender-geometry-nodes/references/recipes.md`).
2. Assets to scatter: optimized props with LODs (recipe 1). Keep instances (don't realize) for engines that support instancing (`export_gpu_instances`).
3. Gate: `mesh_stats.py` on the evaluated result, plus `look` from the gameplay camera height.

## 7. Web / AR asset
Recipe 1 or 2 with budgets `--budget web` (≤30k tris, 1–2 materials, 2k textures) → `export_asset.py --preset web` (meshopt + WebP) → optional `gltf-transform optimize --texture-compress ktx2`. USDZ for iOS AR: `--preset usd --out x.usdz`. Gate: GLB summary (size < 5 MB) and Khronos PBR Neutral look-dev match.

## 8. Product shot / turntable
1. Materials with measured values (`build_pbr_material.py --preset`), and QA for z-fighting/floating parts (very visible in close-ups).
2. Set the render resolution, then `turntable.py --objects Product --rig studio --backdrop --frames 120 --lens 85`
3. `render_batch.py --preset preview --frames 1` → review → `--preset product --frames 1-120 --format PNG` → encode, or `--format MP4`.
4. Gate: no fireflies or clipped highlights (AgX / Khronos PBR Neutral), and the product sits on the backdrop (contact shadow).

## 9. Mood / weather shot (rainy night, snowy morning, foggy dawn)
1. Scene at real scale with a camera. QA the hero assets first (wet reflections and snow expose z-fighting and gaps).
2. `scene_mood.py --time night --fog-visibility 250` (or `--mood cyberpunk|horror|underwater|desert`). Add practical lights (street, windows, neon) at real color temperatures.
3. Weather: `precipitation.py --type rain --intensity heavy --ground <ground/roofs>` → `surface_weather.py --objects <surfaces> --wetness 0.7 --puddles 0.4 --ripples 1 --streaks 0.5` → `lightning.py --flashes 2`. Snow: `--type snow` + `--snow 0.8 --snow-depth 0.06`.
4. Gate: `render_batch.py --preset preview --frames <mid>,<flash>` at the final aspect ratio. Rain must read (backlit), puddles must reflect a light, the night must keep contrast. Then render the full loop (frame range = the precipitation loop).
