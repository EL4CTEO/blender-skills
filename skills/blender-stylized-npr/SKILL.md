---
name: blender-stylized-npr
description: Stylized / NPR looks in Blender 5.2 - toon and cel shading (bands, shadow tint, rim, hard specular), anime faces with custom normals, inverted-hull outlines with smoothed outline normals for game engines, Line Art and Freestyle lines, Grease Pencil drawing, unlit export. Use for anime, cartoon, comic, cel-shaded or outlined styles.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.2.0"
---

# Stylized / NPR

The execution model is in `blender-core`. Base colors still come from `blender-pbr-materials`/`blender-texturing`. This skill replaces how they're lit.

## One call each
```
scripts/toon_setup.py -- --objects Hero Sword --bands 2 --rim 0.4 --outline 0.004
scripts/toon_setup.py -- --objects Hero --bands 3 --spec 0.3 --smooth-normals      # + engine outline data
scripts/toon_setup.py -- --objects Hero --lighting scene                           # EEVEE: all lights + cast shadows
scripts/toon_setup.py -- --line-art --outline 0                                    # scene-wide Line Art
scripts/toon_setup.py -- --objects Hero Sword --remove --line-art                  # exact restore
```

## toon_setup.py
- Inserts an `NPR_Toon` emission group between each material's Principled base color and the output, and records the original surface link for `--remove`. Re-running updates values in place.
- **`--lighting key`** (default, Cycles + EEVEE): shading = N·L against one sun (`--light`; `NPR_Key` is created if there's none). Drivers follow the sun's rotation, so rotate the sun to art-direct the shadow shape. This is how engine toon shaders work, and the look matches after export.
- **`--lighting scene`**: Shader to RGB on a white diffuse, so every light and cast shadow shapes the bands. **EEVEE only.** Measured: in Cycles, Shader to RGB returns a constant regardless of light (identical render at 0, 3 and 10 W/m² sun).
- Bands: 2 (lit/shadow, classic anime) or 3 (adds a mid band 0.45 above `--threshold`). `--softness` (0.02) is the half-width of the band edge, so 0 aliases. `--shadow-tint` multiplies the base color: use cool and saturated (0.6, 0.55, 0.75), never grey/black, because grey shadows read as dirty.
- `--rim` (0–1) adds a lit-side rim, and `--spec` (0–1) a hard Blinn highlight disc (0.2–0.4 for hair/metal, 0 for skin).
- Sets **view transform Standard**: AgX/Filmic desaturate and compress flat colors, so the albedo you pick is the pixel you get only under Standard. The original is restored on `--remove`.

## Outlines (pros use several at once)
| Method | Where it works | Notes |
|---|---|---|
| Inverted hull (`--outline`, m) | Cycles, EEVEE, engines | Solidify outward, flipped normals, outline slot, Backfacing→transparent. Width 2–6 mm on a 1.75 m character. `--outline-group` = vertex group for width (taper toward tips, 0 inside the mouth) |
| `--smooth-normals` | engine outline shaders | `NPR_OutlineNormal` corner color = position-welded normal in tangent space (0.5 + 0.5n). Hard edges/UV splits no longer open gaps. Decode `n = TBN·(c·2−1)` |
| Line Art (`--line-art`, Grease Pencil) | renders | contour + crease + intersection from the camera. Needs a scene camera. `--line-radius` (m) |
| Freestyle | renders | `scene.render.use_freestyle = True`, `line_thickness` px. Slowest, most options |
Known hull limits: lines at intersections and inner creases are missing (use Line Art for those in renders), and hard-edged meshes split the hull. In Blender, merge by distance before the Solidify. In engines, use `--smooth-normals`.

## Anime faces and hair
- Face shadows from real normals look blotchy. Transfer **custom normals** from a simple ellipsoid proxy: a Data Transfer modifier with `use_loop_data=True`, `data_types_loops={'CUSTOM_NORMAL'}`, `loop_mapping='POLYINTERP_NEAREST'` (no auto smooth needed since 4.1), masked by a face vertex group. Engines import the custom normals (FBX/glTF export normals).
- For a stylized nose/cheek shadow, many games use an SDF face shadow texture sampled with the light angle in-engine. Author it as a grayscale threshold map, not in the node tree.
- Hair: a strong `--spec` plus a hand-painted highlight band ("angel ring") in the base color texture.

## Grease Pencil (5.x API)
```python
gp = bpy.data.grease_pencils.new("Ink"); ob = bpy.data.objects.new("Ink", gp); scene.collection.objects.link(ob)
mat = bpy.data.materials.new("Ink"); bpy.data.materials.create_gpencil_data(mat); gp.materials.append(mat)
drawing = gp.layers.new("Lines").frames.new(1).drawing
drawing.add_strokes([3]); s = drawing.strokes[0]
for i, p in enumerate(s.points): p.position, p.radius = (i * 0.5, 0, 0), 0.01   # radius in m
```
Strokes expose `cyclic`, `material_index`, `fill_id`, `hide_stroke`. Raw attributes: `drawing.attributes` (`position`, `radius`). `GreasePencilv3`/`grease_pencils_v3` are gone (5.0). 5.2 Line Art can emit fill strokes (`fill_strokes`).

## To game engines
Node toon shading doesn't export. Export the base color textures and rebuild the toon ramp in the engine (UE material/post-process, Unity URP toon shader, Godot `ShaderMaterial`), driven by the same sun direction. Ship the hull as a second material slot (apply the modifier), or as `NPR_OutlineNormal` for a shader outline pass.
For flat, unlit assets in glTF, use a **Background** shader, or Light Path *Is Camera Ray* mixing Transparent→Background: both export as `KHR_materials_unlit`. Emission exports as emissive on a black base, not unlit (measured).

## Gotchas
- Apply scale before `--outline`: Solidify thickness is in object space.
- Bloom and AO fight the flat look. Keep the world dim and uniform, and use one key light plus maybe a rim light.
- `--lighting scene` bands shift with light energy (luminance 0.3 ≈ threshold 0). Raise/lower `--threshold` instead of the light power.
