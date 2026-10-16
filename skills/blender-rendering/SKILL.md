---
name: blender-rendering
description: Render with Blender 5.2 Cycles/EEVEE/Workbench - quality presets, GPU setup, adaptive sampling, denoising, light paths, color management (AgX, Khronos PBR Neutral, ACES), PNG/EXR/MP4 output, passes, the 5.0 compositor API, CLI and multi-camera batch rendering. Use for any still, animation or turntable render.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Rendering

The execution model is in `blender-core`. Scene lighting and cameras are in `blender-lighting-lookdev`.

## One call
```
scripts/render_batch.py -- --engine CYCLES --preset final --res 1920 1080 --out //render/hero_#### --frames 1
scripts/render_batch.py -- --preset preview --frames 1-120 --format MP4 --out //render/turntable
scripts/render_batch.py -- --cameras CamA CamB CamC --format EXR_MULTI --out //render/shots/
```
Presets: `preview` (Cycles 64 spp, threshold 0.05, 50% res; EEVEE 16), `final` (512 spp, 0.01; EEVEE 128 + raytracing), `product` (1024 spp, transparent background). GPU is picked automatically (OptiX > CUDA > HIP > Metal > oneAPI), and the denoiser matches (OptiX or OpenImageDenoise).

## Engine choice
| Engine | Use | Notes |
|---|---|---|
| Cycles | final quality, product, archviz, glass/SSS/caustics, baking | path tracer; set the GPU; adaptive sampling + denoise |
| EEVEE (5.x, ex-"Next") | fast look-dev, stylized, motion graphics, previews | ray-traced reflections/GI (`use_raytracing`), virtual shadow maps; needs a GPU even headless |
| Workbench | playblasts, clay/matcap reviews, QA sheets | instant, no lighting accuracy |
Engine ids: `CYCLES`, `BLENDER_EEVEE`, `BLENDER_WORKBENCH`.

## Cycles quality levers (ordered by impact)
1. **Adaptive sampling** (`adaptive_threshold` 0.01 final / 0.05 preview) + **denoise** (OIDN with albedo+normal passes, `denoising_input_passes="RGB_ALBEDO_NORMAL"`). Raising samples alone is the least efficient fix.
2. **Light paths**: interiors need diffuse bounces ≥ 4. Product shots: total 12, glossy 4, transmission 8–12 for glass. Clamp indirect 5–10 kills fireflies at a small energy cost.
3. **Light tree** (`use_light_tree`, on) for many lights. **Path guiding** (CPU only) for difficult indirect light.
4. Fewer, larger lights beat many small ones. Emissive meshes are noisier than area lights.
5. Persistent data (`render.use_persistent_data`) speeds up animations and turntables. Use `simplify` (max subdivision, texture limit) for previews.
6. 5.2: **texture cache** (`render.use_texture_cache`, `use_auto_generate_texture_cache`) cuts memory in texture-heavy scenes by generating `.tx` mip tiles.

## Color management (decide once per project)
- **AgX** (default): photographic, handles bright highlights. Looks: `AgX - Punchy`, `- Base Contrast`...
- **Khronos PBR Neutral**: shows albedo faithfully. Use it for product/e-commerce and asset reviews, and to match three.js `NeutralToneMapping`.
- **Standard**: graphics/UI/texture output that must match pixel values.
- **ACES 1.3 / 2.0**: VFX pipelines (plates, other DCCs).
- Use exposure (`view_settings.exposure`), not light power, for global brightness tweaks. Display device sRGB, or Display P3 / Rec.2100 for HDR delivery.

## Output formats
- Stills: PNG 8/16-bit (RGBA when the film is transparent) or JPEG for web previews.
- Comp/VFX: **EXR multilayer** (`EXR_MULTI`, DWAA 16-bit) with passes (Denoising Data, Cryptomatte, AO, Mist, Z). 5.0 renamed passes: `Diffuse Color`, `Depth`, etc.
- Video: render **frames first** (PNG/EXR), then encode (FFmpeg or the VSE), because a crash mid-MP4 loses everything. Direct MP4 is fine for previews. Set `image_settings.media_type` **before** `file_format` (5.0+).
- Transparent: `film_transparent=True` + PNG/EXR. A glass-only alpha needs `film_transparent_glass`.

## Compositor (5.0+ API)
```python
ng = bpy.data.node_groups.new("Comp", "CompositorNodeTree"); scene.compositing_node_group = ng
ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl, glare, out = ng.nodes.new("CompositorNodeRLayers"), ng.nodes.new("CompositorNodeGlare"), ng.nodes.new("NodeGroupOutput")
ng.links.new(rl.outputs["Image"], glare.inputs["Image"]); ng.links.new(glare.outputs["Image"], out.inputs[0])
```
There's no Composite node anymore: the group output is the final image. Many node options are now **input sockets** (Glare `Type`, `Threshold`, `Strength`), so `--describe` them with `blender-geometry-nodes/scripts/gn_builder.py`. File Output node: `directory`, `file_name`, `file_output_items`.

## CLI rendering (render farms, CI)
- `blender -b scene.blend -E CYCLES -o //out/frame_#### -F PNG -s 1 -e 120 -a` renders an animation. `-f 10` renders a single frame. Python args go after `--`.
- `-- --cycles-device OPTIX` (or CUDA/HIP/METAL/ONEAPI) selects the device without Python.
- Split frames across machines with `-s/-e`, or with Placeholders + No Overwrite (`render.use_placeholder`, `use_overwrite=False`) on shared storage.

## Gotchas
- `scene.render.engine` enum under-reports (add-on engines). Assign in try/except (the script does).
- EEVEE in background still needs a GPU context. In CI without a GPU, use Cycles CPU or Workbench.
- `bpy.ops.render.render(write_still=True)` writes `render.filepath`. Without `write_still`, the result only lives in `Render Result`.
- Noise in glass/caustics: enable caustics only if needed (`caustics_refractive`), raise transmission bounces, or fake it with Thin Wall (5.2) for windows.
- Fireflies: clamp indirect, a filter glossy / blur glossy (`blur_glossy` 0.5–1), and bigger light sources.
