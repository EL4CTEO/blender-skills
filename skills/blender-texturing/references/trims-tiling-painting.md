# Trim sheets, tiling blends, texture painting (verified in Blender 5.2.3)

## Trim sheets (environment and hard-surface kits)
- One texture holds horizontal **strips** (trims) that tile in U: panels, edges, bolts, pipes, rails. Many meshes share one material, which means few draw calls, high texel density, and consistent wear.
- Layout: a 2048² or 4096² sheet with strip heights in powers of two (32/64/128/256/512 px), so mips don't bleed. Put the most-used trims tallest. Leave 4–8 px gutters.
- Model with UV-friendly pieces: each face's UVs go into exactly one strip, with U running along the length. Keep the kit's **texel density** fixed (`blender-retopology-uv` `texel_density.py`, e.g. 512 px/m) and let U overrun 0–1 to tile.
- Snap an island to a strip with numpy (`v0`/`v1` are the strip's bounds, 0–1 from the bottom):
```python
uv = me.uv_layers.active.uv; a = np.empty(len(uv) * 2, np.float32); uv.foreach_get("vector", a)
a = a.reshape(-1, 2); sel = ...  # loop indices of the island
a[sel, 1] = v0 + (a[sel, 1] - a[sel, 1].min()) / np.ptp(a[sel, 1]) * (v1 - v0)
uv.foreach_set("vector", a.ravel())
```
- Unique hero assets still get unique textures. Trims are for kits, architecture and vehicles' repeated parts.

## Tiling materials + vertex-color blends (large surfaces)
- Tiling textures (concrete, brick, ground) + a **color attribute** that blends a second layer (moss, dirt, wet). This keeps resolution infinite and memory tiny. Paint the mask in Vertex Paint (5.2: spherical falloff draws a surface-aligned cursor), or compute it (`blender-weather-fx` `--vertex-mask`, slope/height masks in `blender-environment-kits`).
- Height-blend instead of a linear fade: `t = clamp((hB − hA + (mask·2 − 1)) · contrast + 0.5)`. The second layer fills the cracks of the first first, which looks natural. The node is `ShaderNodeVertexColor` (`layer_name`).
- Engines get the mask as COLOR_0 (glTF exports the active color attribute, `export_vertex_color`). Rebuild the blend in the engine shader.

## Texture painting (live session with UI)
```python
img = bpy.data.images.new("T_Hand_BC", 2048, 2048)          # or load the baked base color
tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img
mat.node_tree.nodes.active = tex                           # the active image node is the paint target
bpy.ops.object.mode_set(mode="TEXTURE_PAINT")
bpy.ops.brush.asset_activate(asset_library_type="ESSENTIALS",
    relative_asset_identifier="brushes/essentials_brushes-mesh_texture.blend/Brush/Paint Hard")
ts = bpy.context.tool_settings.image_paint; ts.mode = "IMAGE"; ts.canvas = img   # or "MATERIAL"
```
- Essentials texture brushes include `Paint Hard`, `Paint Soft`, `Airbrush`, `Blur`, `Smear`, `Clone`, `Fill`, `Mask`, `Erase Hard`, `Paint Pixel Art`.
- Strokes from Python are fragile (`paint.image_paint(stroke=[...])` needs a 3D View region). Agents should set up the canvas and brushes and let the human paint, or write pixels directly.
- **Save images explicitly** (`img.filepath_raw = ...; img.save()`). Painted images live only in memory. 5.2 autosave covers texture paint sessions, but don't rely on it.
- Projection painting from a photo: `paint.project_image(image=...)` projects onto the mesh from the view (UI only). `ts.seam_bleed` (px) hides UV seams, and `ts.use_occlude` stops paint going through.

## Headless pixel writes (masks, IDs, procedural stencils)
```python
a = np.zeros((h, w, 4), np.float32); a[..., 3] = 1; a[y0:y1, x0:x1, 0] = 1   # rows = y from the bottom
img.pixels.foreach_set(a.ravel()); img.update(); img.save()
```
5.2 adds the `imbuf` module (`imbuf.new((w, h))`, `load`, `write`, `with_buffer` for buffer-protocol access, `quality`/`compress`) for file I/O without creating an Image data-block.
