---
name: blender-texture-baking
description: Bake texture maps in Blender 5.2 Cycles - high-to-low normal maps with cage/extrusion, AO, curvature, ID, thickness, base color/roughness/metallic from procedurals, ORM packing, OpenGL vs DirectX, margins, GPU baking, fixing skewing/waviness/seams. Use when transferring sculpt or high-poly detail to game meshes or converting procedural materials to textures.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Texture Baking (Cycles)

The execution model is in `blender-core`. UVs come from `blender-retopology-uv` and materials from `blender-pbr-materials`.

## One call
```
scripts/bake_maps.py -- --low SM_Crate --high Crate_high Crate_bolts --maps normal ao curvature id \
   --res 2048 --samples 64 --margin-px 16 --pack-orm --out //textures
```
Self-bake (procedural → textures, no `--high`): `--low SM_Crate --maps basecolor roughness metallic normal --pack-orm`.
The script picks the GPU (OptiX/CUDA/HIP/Metal/oneAPI) and falls back to CPU, creates the target images with correct color spaces, cleans up its temporary nodes, and saves `T_<name>_<N|AO|CURV|BC|R|M|ORM...>.png`.

## Preparation checklist (most bake bugs come from this list)
1. **Low poly**: UVs unwrapped, no overlaps (stacked/mirrored islands moved +1 U), padding ≥ 8 px at the bake resolution, scale applied.
2. **Hard edges = UV seams** on the low poly. Use either smooth shading with the bake handling gradients, or hard edges split at seams. Never put a hard edge inside a UV island.
3. **Triangulate the low poly the same way the engine will**, or export the triangulated mesh. Mismatched triangulation shows as shading seams.
4. **High poly** covers the low completely and pokes out of it only a little. Floaters (bolts, panel details) can hover just above the surface, but must stay within the extrusion distance.
5. **Names**: `X_low` / `X_high` pairs. Bake per part, or explode the parts apart (move each pair along an axis) so neighbouring parts don't project onto each other, then put them back.
6. Apply modifiers on the high poly as needed (multires and subd are evaluated automatically).

## Rays: extrusion vs cage
- `--extrusion` (meters) pushes the ray origin outward from the low surface. It must be **greater than the farthest distance the high poly sticks out** of the low. The default is 2% of the low's diagonal; `max_ray_distance` is 2 × extrusion.
- **Cage** (`--cage Crate_cage`): a copy of the low with the same topology, inflated (Displace/"Push"). Use it when uniform extrusion fails (sharp concave corners, thin parts). Edit the cage locally where rays miss.
- Too small: holes or missing details. Too large: other parts of the mesh project in (intersections, "ghosting").

## Map guide
| Map | Space | Notes |
|---|---|---|
| normal | Non-Color, tangent, OpenGL (`--directx` for Unreal) | 16-sample AA is plenty; 8-bit PNG is fine for games |
| ao | Non-Color | 64–256 samples; bake with the high only (no ground) unless contact AO is wanted |
| curvature | Non-Color, 0.5 = flat | derived from the baked normal (convex white / concave dark); drives edge wear |
| id | sRGB | one flat color per high-poly **material**; use materials as masks |
| thickness | Non-Color | AO with inside rays; dark = thin; for SSS/translucency masks |
| basecolor/metallic/opacity | via emission override | reads the Principled inputs of the source materials (also procedural chains) |
| roughness, emit, combined | native Cycles passes | combined = lit result (lightmaps, stylized) |
| position | float | gradient masks |
ORM = R:AO G:Roughness B:Metallic, the glTF/Unreal standard. Unity uses a different packing (`blender-pbr-materials`).

## Fixing common artifacts
| Symptom | Cause | Fix |
|---|---|---|
| Wavy lines on cylinders | low poly too low, smoothing gradients | add segments, use a cage, or more support on the low |
| Skewed details (bolts lean) | ray direction follows the averaged low normals | hard edges + seams, a cage, or bake the floater separately |
| Black/garbage areas | rays miss or hit the back faces | raise extrusion, fix flipped normals (`blender-asset-qa`), check high coverage |
| Seams visible in engine | margin too small, hard edge without a seam, different tangents | margin ≥ 16 px @2k, seams at hard edges, export tangents (MikkTSpace) |
| Details from a neighbouring part | parts too close | explode the bake, or bake per object pair |
| Inverted green look in engine | OpenGL/DirectX mismatch | `--directx` for Unreal, or flip G in the texture importer |
| Stepping/banding | 8-bit with large flat gradients | bake to 16-bit (`float_buffer`) and dither on export |

## Baking non-PBR data
- **Vertex colors**: `bake.target = "VERTEX_COLORS"` with an active color attribute (useful for mobile and Roblox-free shading).
- **Lightmaps**: bake `combined` onto UV2 (`--uv-layer UVMap_Lightmap`) with the scene lights.
- **Multires** (no separate high object): `bake.use_multires=True`, `bake.type="NORMALS"|"DISPLACEMENT"|"VECTOR_DISPLACEMENT"`, `bake.use_lores_mesh=True`, then `bpy.ops.object.bake_image()`. The viewport level is the low, the sculpt level is the high.

## Gotchas
- The target image must be the **active** Image Texture node in **every** material of the low object (the script handles this).
- Baking in Cycles uses the active UV map (`--uv-layer` to pick).
- Images aren't saved automatically: `img.save()` or `save_render`. Packed or internal images disappear on reload.
- 5.2: the Cycles texture cache (`.tx`) is for render memory and doesn't affect bake results.
- Run `blender-asset-qa` on low + high first, because flipped normals and floating chunks produce most bake garbage.
