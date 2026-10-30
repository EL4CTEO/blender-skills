---
name: blender-texturing
description: Texture authoring in Blender 5.2 - smart-material layers (edge wear, cavity grime, dust, rust, roughness breakup) from curvature/AO masks, z-fight-safe decal and sticker placement, trim sheets, tiling + vertex-color blends, texture painting, baking the look to game texture sets. Use when a material needs wear, dirt, a decal, trims or hand painting, not just wiring.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.2.0"
---

# Texturing

The execution model is in `blender-core`. Material wiring and measured values are in `blender-pbr-materials`, and bakes are in `blender-texture-baking`. This skill authors the *surface story*: where paint chips, where dirt collects, what's printed on it.

## One call each
```
scripts/smart_material.py -- --objects Crate --wear 0.5 --grime 0.4 --dust 0.3
scripts/smart_material.py -- --objects Crate --rust 0.6 --under-color 0.3 0.29 0.28    # rusty iron
scripts/smart_material.py -- --objects SM_Crate --wear 0.5 --curvature-map //tex/T_Crate_CURV.png --ao-map //tex/T_Crate_AO.png
scripts/decal.py -- --target Wall --at 0 -0.1 1.5 --image //decals/hazard.png --size 0.4
scripts/smart_material.py -- --objects Crate --remove                                  # exact restore
```

## How pros layer a material
Start with a clean base (correct albedo/roughness, `blender-pbr-materials`), then stack from the inside out: **base → edge wear → rust → grime → dust**. Each layer has a physical cause:
| Layer | Mask (cause) | Look |
|---|---|---|
| Edge wear | convex curvature (edges get hit) + chip noise | reveals the under-material: bare metal, primer, raw wood |
| Rust | cavities and worn edges + blotch noise | orange-brown, metallic 0, roughness ~0.85 |
| Grime | concave curvature + (1 − AO) (dirt collects where it can't be wiped) | dark, rougher, not metallic |
| Dust | world up-facing normal × patch noise (it settles from above) | light, roughness ~0.9 |
| Breakup | fine noise on roughness (±25%) | the cheapest realism win; never ship a flat roughness value |
Pure curvature looks procedural and even. Always multiply in noise so wear is heavy in some places and absent in others. Less is more: wear 0.2–0.4 reads as "used", and 0.7+ reads as "abandoned".

## smart_material.py
- Inserts one `TX_Layers` group in front of every Principled BSDF (Base Color, Roughness, Metallic) and records the originals, so `--remove` restores links and values exactly. Re-running updates values in place. All layer amounts stay inputs on the group node, so you can tweak them there.
- **Curvature**, live and portable (Cycles + EEVEE, no bake): the `TX_Curvature` point attribute is the mean elevation of the neighbours within `--edge-width` (m, default 0.02). It's density-independent: band ≈ edge width. Set the width to roughly the bevel width (1–3 cm on props, 5–10 cm on buildings). Cost: ~1.5 s per 30k verts.
- It needs **mid-poly density** (bevels/supports). When the median edge is > 4× the edge width, the result carries a `note`: wear would smear across whole faces. On low-poly game meshes, bake from the high (`bake_maps.py --high ... --maps normal ao curvature`) and pass `--curvature-map`/`--ao-map` (loaded as Non-Color, read through `--uv`).
- Noise is in **object space** (`--scale` = feature size in m), so masks stick to the asset when it moves. Mirrored/linked duplicates share the pattern, so vary `--scale` or the object if that shows.
- Colors are sRGB 0–1. Defaults: steel under paint (0.56, 0.57, 0.58, metallic 1, roughness 0.35). For wood under paint, use `--under-color 0.45 0.32 0.2 --under-metallic 0 --under-roughness 0.7`.

## To game engines
Engines don't run Blender node trees. Bake the result into a texture set: `bake_maps.py -- --low SM_Crate --maps basecolor roughness metallic normal --pack-orm` (self-bake, no `--high`). Then `build_pbr_material.py --textures` and export. Check the result with `blender-asset-qa` and a lit `look`.

## Decals (decal.py)
- Places a subdivided plane at the closest surface point to `--at`, oriented to the normal and spun by `--rotation`. A Shrinkwrap (project, above surface) keeps it `--offset` (2 mm) off the surface. It's parented, has no shadow, uses Dithered alpha, and its height follows the image aspect.
- It measures the gap at every triangle like `blender-asset-qa` does, and doubles `--subdiv` (to 128) until flat triangles stop dipping over convex creases. The result reports `gap_min_m`/`gap_max_m`. Never place decals at 0 offset: that's guaranteed z-fighting.
- Games: mesh decals cost a draw call each and need alpha sorting. Merge decals that share an atlas into one mesh, use engine projectors (UE Decal Actor, Unity URP Decal Projector, Godot `Decal`) for dynamic ones, or bake them into the base texture.

## Trim sheets, tiling, painting
Trim sheets, tiling with vertex-color blends, hand/texture painting (5.2 brush assets) and headless pixel writes: [references/trims-tiling-painting.md](references/trims-tiling-painting.md).

## Gotchas
- Mask textures (curvature, AO, roughness, ID) must be **Non-Color**. The script forces it, but hand-made nodes often don't.
- Apply scale before computing curvature or setting `--scale`. Both are world-sized.
- `TX_Curvature` is mesh data. Applying modifiers or remeshing afterward invalidates it, so re-run after topology changes.
- Viewport EEVEE vs Cycles: identical masks (no Bevel/Pointiness/AO shader nodes are used, because those are Cycles-only or screen-space).
