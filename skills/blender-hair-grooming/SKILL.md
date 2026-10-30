---
name: blender-hair-grooming
description: Hair and fur in Blender 5.2 - hair curves on a surface, guides + interpolated children with the bundled hair node assets (clump, curl, noise, droop), density masks, Principled Hair BSDF (melanin), Curves Sculpt combing, 5.2 node Hair Dynamics, game hair cards with a rendered strand atlas, Alembic/USD groom export. Use for hair, fur, beards, eyebrows, grass tufts.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.2.0"
---

# Hair grooming

The execution model is in `blender-core`. Hair physics details are in `blender-simulation`, and look-dev in `blender-lighting-lookdev`.

## One call each
```
scripts/groom.py -- --surface Head --mask Scalp --length 0.15 --children 150000 --clump 0.5
scripts/groom.py -- --surface Head --mask Beard --length 0.02 --droop 0.2 --curl 0.004 --melanin 0.9 --name Beard
scripts/groom.py -- --surface Body --length 0.025 --droop 0.3 --clump 0.3 --name Fur
scripts/groom.py -- --cards Hair --card-count 150 --atlas-res 2048 --out //textures      # game hair cards
```

## How pros groom
1. **Surface first**: the scalp is a mesh (or the head itself) with **UVs** (hair attaches by UV) and a **vertex group** painted where hair grows. That group becomes the density mask, so soft edges give a natural hairline.
2. **Guides → children**: a few hundred to a few thousand guides carry the shape, and thousands of interpolated children give the volume. Style the guides, never the children.
3. **Shape in layers**: length, then clump (strands gather into locks), then curl/wave, then frizz/noise, then profile (thin tips). Keep each a separate modifier you can toggle.
4. **Comb by hand** for anything hero: Curves Sculpt mode brushes (`Comb`, `Add`, `Puff`, `Pinch`, `Grow/Shrink`, `Smooth`, `Slide`, `Density`, `Delete`, `Pull Tips`). Procedural droop gives a believable base, not a hairstyle.
5. Look-dev under the final lights. Hair reads mostly from **specular** and depth (clumps catch highlights), not albedo.

## groom.py
- Runs 5.2's Add Empty Hair (`object.curves_empty_hair_add`). It parents to the surface, sets `surface`/`surface_uv_map`, adds **Capture Rest Geometry** to the surface, and adds the node **Hair Dynamics** modifier (pinned last, experimental). Then it stacks the bundled assets: Generate (`--density` guides/m²) → Interpolate (`--children`/m², `--viewport` fraction in the viewport) → Clump → Curl → Displace + Shrinkwrap (`--droop` × length down, kept 2 mm above the surface) → Noise → Set Hair Curve Profile (`--radius`, tip taper).
- **Clump/curl guide distance = 10% of `--length`.** The asset's default 0.1 m collapses a whole head into a few tufts.
- Each asset stays a modifier with live inputs, so tweak there. Inputs by name: `getattr(md.properties.inputs, identifier).value`; vertex-group masks use `.type = "ATTRIBUTE"`, `.attribute_name`.
- It reports curves, mean length, the max root gap to the surface (must be ~0) and the modifier stacks. Evaluated counts in background mode use the viewport amount.

## Numbers
| | Value |
|---|---|
| Human scalp | ~100–150k hairs, ~200/cm². CG: 30k–150k rendered strands, 300–3000 guides |
| Strand radius | real 0.03–0.05 mm. Use 0.05 mm (`--radius 0.00005`), thicker with fewer strands |
| Melanin (Principled Hair, Chiang) | black 1.0 · dark brown 0.8 · brown 0.65 · light brown 0.45 · blond 0.25 · platinum 0.1. Red: 0.5 + redness 0.9. Grey: 0 + tint |
| Roughness | 0.25–0.35 (glossy) … 0.5 (dry). Radial roughness 0.3 |
| Fur | length 1–5 cm, density 200k–2M/m², little clump |
`HUANG` (4.0+) models elliptical cross-sections and is better for close-ups. `CHIANG` is the reference default.

## Game hair cards (`--cards HAIR`)
- Picks `--card-count` well-spread strands (farthest-point sampling) of the evaluated groom and builds a ribbon along each: `--card-width` m, tapering to 30% at the tip, lying flat on the surface (side = tangent × surface normal). UV v runs root 0 → tip 1, one atlas column per card (`--atlas-columns`).
- Renders the atlas with Cycles from flat strand clumps: `T_<name>_BC` (darker roots, coverage in alpha, Standard view), plus `T_<name>_RootTip` and `T_<name>_ID` (Raw, linear data). The card material uses Dithered alpha with no backface culling.
- Pros layer cards from the scalp outward: dense, wide, opaque cards on the scalp to hide skin; mid layers; then thin flyaway cards on top. Budgets: hero 20k–60k tris, NPC 5k–15k. Bend cards in S/C shapes, never flat planes, and check from every angle. Engines use alpha test/dither + depth prepass, root-tip for darkening/AO and ID for per-strand variation. Add a tangent (flow) map along V for anisotropic specular.

## Export grooms
Strand hair for UE Groom/Houdini: Alembic (`wm.alembic_export`) or USD (`wm.usd_export(export_curves=True)`). Both write the evaluated curves (measured: 246/246 curves round-trip). Bake the modifier stack first if the target needs guides only.

## Gotchas
- No UVs on the surface means `Generate` has nothing to attach to. Add UVs before grooming.
- Changing the surface topology after grooming breaks attachment. Groom last, or re-run.
- Scale: apply the head's scale. Lengths and densities are world meters.
- Viewport: keep `--viewport` ≤ 0.2 on full heads. Final strand counts only appear in renders.
- Hair Dynamics simulates on playback. For stills on frame 1 it's a pass-through. Bake it (`blender-simulation`) before animated renders.
