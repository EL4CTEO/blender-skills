# Weather for games and real-time

In engines, weather is a runtime system: particles, post-processing and material parameters. Blender's job is to deliver **meshes and masks** that the engine shaders read. Never export rain or snow instances as geometry.

## What to export from Blender
| Asset | How |
|---|---|
| Wetness/puddle/snow mask per vertex | `surface_weather.py --vertex-mask` → color attribute `ENV_Weather` (R puddles, G snow, B walls). Make it the active color attribute (`mesh.color_attributes.active_color_name = "ENV_Weather"`) |
| Mask textures | bake the wet material with `blender-texture-baking` (self-bake: basecolor/roughness), or bake the mask into a channel of a packed texture |
| Snow cover mesh | apply `ENV_SnowCover` (or export it as a separate LOD-able mesh), then `blender-asset-qa` + `blender-game-optimization` |
| Puddle decals | planes with a water material, slightly above the ground (≥ 2 mm, never coplanar: z-fighting) |
| Rain splash / ripple flipbooks | render a top-down ripple with `surface_weather` on a plane (orthographic camera), then pack the frames into an atlas |

Exporter flags (5.2): glTF `export_vertex_color="ACTIVE"` (or `"NAME"` + `export_vertex_color_name="ENV_Weather"`); FBX `colors_type="LINEAR"` for masks (sRGB would gamma-shift the values) with `prioritize_active_color=True`.

## Engine side (what reads the masks)
- **Unreal**: a wetness material function (darken albedo, lower roughness, puddle normal flatten), driven by a Material Parameter Collection `Wetness` × vertex color R. Rain = Niagara GPU sprites with depth-buffer collision, plus ripple decals.
- **Unity (URP/HDRP)**: a Shader Graph wet layer using vertex color, or HDRP decals for puddles. Rain = VFX Graph (GPU) with depth collision. Snow = a vertex color G blend to a snow layer.
- **Godot 4**: a ShaderMaterial reading `COLOR`, with GPUParticles3D + a particle collision heightfield.
- **Roblox**: no custom shaders. Use MaterialVariant / SurfaceAppearance swaps for wet and snowy versions, ParticleEmitter (`Speed`, `Acceleration`, `Drag`) for rain and snow, and Atmosphere (`Density`, `Haze`, `Glare`) for fog. Keep particle `Rate` low on mobile.

## Budgets
- Rain on mobile: around a few hundred camera-attached sprites. PC/console: thousands of GPU particles. Never use per-drop geometry.
- Masks: vertex colors cost nothing extra if the mesh already has colors. A mask texture shares an existing packed channel (for example the A of ORM).
- Fog: engine height fog (Unreal Exponential Height Fog, Unity Fog, Roblox Atmosphere). Match its density to `scene_mood` visibility: extinction ≈ 3.912 / visibility (m).
