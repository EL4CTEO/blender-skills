---
name: blender-weather-fx
description: Weather effects in Blender 5.2 - looping Geometry Nodes rain, snow, dust, ash and embers with ground hits and splashes, wet surfaces, puddles with animated ripples, wall streaks, snow cover (shader + real snow geometry), storm lightning with multi-stroke flashes and bolts, engine-ready weather masks. Use for rain, storm, snow, wet street, puddle, dust or ember scenes.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Weather FX

The execution model is in `blender-core`. Sky, sun/moon, fog and mood come from `blender-time-of-day`, so run `scene_mood.py` first, then add weather. Rendering settings are in `blender-rendering`.

## One call each
```
scripts/precipitation.py -- --type rain --intensity heavy --ground Street Roofs --wind 2 0
scripts/surface_weather.py -- --objects Street Car Walls --wetness 0.7 --puddles 0.4 --ripples 1 --streaks 0.5
scripts/lightning.py -- --flashes 2 --strokes 3
scripts/precipitation.py -- --type snow --intensity moderate --ground Terrain
scripts/surface_weather.py -- --objects Terrain Roofs --snow 0.8 --snow-depth 0.06
scripts/surface_weather.py -- --objects Street Car Walls --remove     # exact restore
```
A rainy night: `scene_mood.py --time night --fog-visibility 250` → rain → wetness + puddles → lightning. Rain and puddles at night are what sell a wet scene: wet surfaces reflect every practical light.

## precipitation.py (rain, snow, dust, ash, embers)
- Builds a GN modifier on `ENV_Weather_<Type>`. Its box covers what the camera sees across the frame range: world-fixed, so moving cameras don't drag the rain. With no camera, it covers a 18 m box. The floor is the lowest top of `--ground`.
- **Seamless loop with no simulation**: each particle lives N whole times per loop (`Lives`), so the last frame + 1 equals the first frame exactly. It renders any frame on its own and works headless.
- **Real speeds**: rain 7 m/s (9 at heavy/storm), snow 1, ash 0.6, dust 0.15, embers rise at 1.5, combined with `--wind X Y` (m/s).
- **Ground**: a raycast against the `--ground` objects stops particles at the first hit (roofs, awnings, streets). Rain spawns splash crowns lasting 80 ms at each hit, aligned to the surface normal.
- **Streaks, not motion blur**: rain is a 3-sided streak of length = speed × ½ frame (a 180° shutter), aligned to the travel direction. Motion blur off is cheaper and looks the same.
- Particles closer than 1.5 m to the camera are hidden (`Near Clear`), because huge blobs ruin shots. The viewport shows 10% (`Viewport Fraction`), renders show 100%.
- Density per intensity (particles/m³): rain 5/15/40/80, snow 10/30/80/160. Override with `--density`. The count is capped by `--max-count` (400k), and the result warns when it caps.
- All values remain modifier inputs (Count, Speed, Wind, Lives, Particle Size, Streak Length, Sway, Ground, Splash...), so tweak them there instead of re-running.

## surface_weather.py (wet, puddles, ripples, streaks, snow)
- Puts one `ENV_Weather` shader group in front of each Principled BSDF and records the originals on the material. `--remove` restores links and values exactly.
- **Wet** (Lagarde model): porous albedo darkens (up to 55% × `--porosity`), roughness drops, and a water film is added as **Coat**. Use porosity 0.6–0.9 for asphalt, concrete, wood and fabric, and 0.1–0.2 for metal, glass and plastic.
- **Puddles**: domain-warped world-space noise on up-facing faces. Coverage ≈ `--puddles`, feature size `--scale` (m, default 3). Inside a puddle: full coat, mirror coat roughness 0.02, and a flattened base normal, because water fills the cracks.
- **Ripples**: expanding rings, one per ~17 cm cell, driven by a `frame` driver (a simple expression, so it works without auto-run scripts). They only show inside puddles.
- **Streaks**: vertical noise on walls adds coat runs.
- **Snow**: up-facing coverage with a noisy edge, albedo 0.9, roughness 0.6 and a fine bump. `--snow-depth` adds real thickness with the `ENV_SnowCover` GN modifier: up-facing faces are subdivided and extruded upward by a noise height that is never zero, so there's no z-fighting. It uses the `ENV_M_Snow` material with subsurface.
- `--vertex-mask` writes the `ENV_Weather` color attribute (R puddles, G snow, B walls) for engine shaders.

## lightning.py
- A strike is 3 return strokes ~50 ms apart (at least 2 frames apart, so the flicker reads at 24 fps), each a peak followed by a 2-frame decay. `--strokes`, `--flashes` or `--frames` set the timing. The flash is a cool `ENV_Storm_Flash` sun (12° soft) keyed against the scene's key light (×2.5).
- `ENV_Storm_Bolt` is a branching emissive curve (midpoint displacement plus 4 branches), keyed with the flash. By default it is 300 m away, in frame and off-center. The world background strength flashes too (`--no-sky` to skip).
- Keys use LINEAR interpolation (flashes must snap, not ease).

## Rules
- **Rain is visible only when backlit or side-lit** against a darker background: put a practical or bright sky behind it. Front-lit rain disappears.
- Combine layers: fog (atmosphere) + rain streaks (mid) + splashes/ripples (ground) + wet reflections. Any one alone looks fake.
- Real scale is mandatory: speeds, densities and puddle sizes are in meters (`blender-scene-setup`).
- Check with a render at the final resolution. Rain density and streak visibility don't show in the viewport (10% count, no fog).
- Run `blender-asset-qa` on the snow geometry if the asset will be exported.

## Games and real-time
Weather is an engine system (Unreal Niagara, Unity VFX Graph, Roblox ParticleEmitter). From Blender, export the **masks**: the vertex color attribute (`--vertex-mask`) or baked textures (`blender-texture-baking` self-bake of the wet material), plus snow cover meshes. Details are in [references/realtime-engines.md](references/realtime-engines.md). Physical values and the look library are in [references/weather-values.md](references/weather-values.md).

## Gotchas
- GN particles are instances, so `object.data` stays empty. Read results through the evaluated depsgraph (`depsgraph.object_instances`).
- Background (`-b`) evaluation counts as the viewport for the `Is Viewport` node, so a headless test sees 10% of the count. Renders get 100%.
- Ground objects are linked into the `ENV_Weather_<Type>_Ground` collection (linked, not moved).
- `surface_weather` changes shared materials: every object using that material gets wet. Duplicate materials first to limit it.
- Coat appears in both engines. EEVEE needs raytracing on (`eevee.use_raytracing`) for good puddle reflections.
