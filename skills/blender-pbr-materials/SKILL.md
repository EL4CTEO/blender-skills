---
name: blender-pbr-materials
description: Physically based materials in Blender 5.2 - metal/roughness rules, Principled BSDF inputs, color spaces (sRGB vs Non-Color), measured albedo/F0 values, texture-set auto-wiring, ORM channel packing, DirectX vs OpenGL normals, alpha modes, displacement, view transforms (AgX, Khronos PBR Neutral), engine-ready material rules. Use when creating, fixing, or exporting materials and textures.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# PBR Materials

The execution model is in `blender-core`. Measured values are in [references/pbr-values.md](references/pbr-values.md).

## Fast paths
- Texture set → material: `scripts/build_pbr_material.py -- --name M_Crate --textures //tex/crate --objects SM_Crate`. It detects maps by filename (Poly Haven, ambientCG, Substance, UE suffixes), sets color spaces, splits ORM, flips DirectX normals, and routes AO to glTF.
- Solid physically-plausible material: `--preset gold|iron|plastic|rubber|wood|glass|skin|...` with an optional `--color R G B` (sRGB).

## The rules (violations are what make renders look "CG")
1. **Metallic is binary**: 0 (dielectric) or 1 (raw metal). Use in-between values only on transition pixels (dust or rust edges on metal). Painted metal counts as dielectric.
2. **Base color = albedo with no lighting**: no baked shadows/AO/highlights. Dielectric range is sRGB ~30–240 (linear 0.012–0.87): charcoal ≈ 50, fresh snow ≈ 240. Metals: base color = F0 reflectance, sRGB 180–255, never dark.
3. **Roughness carries the realism**. Break it up with grunge, smudges and wear. A constant roughness value looks fake; vary it ±0.1–0.2 across a surface.
4. **Color spaces**: Base Color and Emission use `sRGB`. Roughness, Metallic, Normal, AO, Height, Opacity and ORM use `Non-Color`. A wrong color space is the #1 bug (washed-out normals, wrong roughness).
5. **Specular**: leave `IOR` 1.5 and `Specular IOR Level` 0.5 for almost all dielectrics. Change IOR only for known materials (water 1.33, glass 1.5, diamond 2.42).
6. **Normal maps**: Blender, glTF, Unity and Roblox use **OpenGL** (Y+). Unreal and Substance's DirectX preset use **DirectX** (Y-), so flip G when converting. The bake and the target must use the same tangent basis (MikkTSpace) and the same triangulation.
7. **AO**: the Principled BSDF has no AO input. For engines, ship AO in the ORM red channel. For Cycles renders, don't multiply AO into base color, because the renderer computes occlusion.

## Principled BSDF (5.2) quick map
`Base Color`, `Metallic`, `Roughness`, `IOR`, `Alpha`, `Normal`, `Thin Wall` (5.2: leaves/paper/fabric sheets without volume), `Subsurface Weight/Radius/Scale` (skin, wax; Scale in meters ≈ 0.005–0.02 for skin), `Specular IOR Level`, `Specular Tint`, `Anisotropic`, `Transmission Weight` (glass/liquids), `Coat Weight/Roughness/Normal` (car paint, varnish), `Sheen Weight` (cloth, velvet), `Emission Color/Strength` (strength in W/m²-ish units; 1–10 for screens, 50+ for bulbs), `Thin Film Thickness/IOR` (soap, oil, coated lenses), `Diffuse Roughness`.

## Engine export rules
| Target | Maps | Packing | Normal |
|---|---|---|---|
| glTF / web / Godot | baseColor(+alpha), metallicRoughness, normal, occlusion, emissive | glTF: **R=AO G=Rough B=Metal** (ORM) | OpenGL |
| Unreal | BaseColor, Normal, ORM | R=AO G=Rough B=Metal | DirectX (UE flips on import if the texture is marked) |
| Unity URP/HDRP | BaseMap, Normal, MetallicSmoothness / HDRP MaskMap | URP: R=Metal A=**Smoothness** (1-rough). HDRP Mask: R=Metal G=AO B=DetailMask A=Smoothness | OpenGL |
| Roblox SurfaceAppearance | ColorMap(+alpha), NormalMap, MetalnessMap, RoughnessMap, EmissiveMaskContent | separate grayscale maps, no packing | OpenGL, tangent space |
- Only image-texture → BSDF chains export. Procedural nodes, Mix nodes and math become nothing in engines, so bake them first (`blender-texture-baking`).
- One material per texture set. Every extra material is an extra draw call (`blender-game-optimization`).
- Power-of-two textures (512/1024/2048/4096). Use PNG/TGA for data maps, never JPEG for normals.

## Alpha
`mat.surface_render_method = "DITHERED"` (cutout/alpha-clip, sorts correctly, good for foliage/hair cards) or `"BLENDED"` (true transparency, glass/UI). Connect `Alpha`. glTF exports CLIP/BLEND from the alpha setup. Prefer dithered/clip for games.

## Displacement
Height map → `Displacement` node → Material Output `Displacement`. `mat.displacement_method`: `BUMP` (shading only, everywhere), `BOTH`/`DISPLACEMENT` (Cycles, needs dense or adaptively subdivided geometry: Subdivision modifier `use_adaptive_subdivision`). Scale is in meters; midlevel 0.5 for 8-bit, 0 for 32-bit EXR.

## View transform (judge materials under the right one)
`scene.view_settings.view_transform`: **AgX** (default, photographic), **Khronos PBR Neutral** (what-you-see-is-the-albedo; use for asset/product review and glTF parity), **Standard** (UI/graphics/textures that must match pixels), ACES 1.3/2.0 (VFX pipelines). Never bake or author textures while looking through Filmic/AgX with an extreme "Look".

## Procedural → texture
Procedural setups (noise/voronoi wear, curvature masks via `Geometry > Pointiness` (Cycles) or `Ambient Occlusion` node, edge wear via `Bevel` node normals) are fine for renders. For engines, bake them to the texture set (`blender-texture-baking`). Node Wrangler (bundled) `Ctrl+Shift+T` does the same as `build_pbr_material.py`, but needs the UI.

## Gotchas
- `material.use_nodes` is deprecated in 5.x. New materials already have Principled + Output.
- `mat.diffuse_color` only affects the viewport (Solid mode/workbench), not renders or export.
- Images loaded headless need `image.colorspace_settings.name` set **before** baking or export.
- Shared texture images used by several materials: change the color space once, because it's per image.
