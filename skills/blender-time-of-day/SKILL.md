---
name: blender-time-of-day
description: Time of day and atmosphere in Blender 5.2 - measured sky + sun for dawn, morning, noon, golden hour, sunset, blue hour, overcast, night/moonlight with stars and city glow, exposure balance, height fog from visibility, god rays, Cycles vs EEVEE volumes, compositor grade, stylized moods (cyberpunk neon, horror, underwater, desert). Use for any day/night, sunset, foggy or mood lighting scene.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Time of Day & Atmosphere

The execution model is in `blender-core`. Studio and product lighting are in `blender-lighting-lookdev`, render settings in `blender-rendering`, and rain, snow, wetness and lightning in `blender-weather-fx`.

## One call
```
scripts/scene_mood.py -- --time golden                       # sun 6 deg, warm, long shadows
scripts/scene_mood.py -- --time night --fog-visibility 250   # moonlight + stars + haze
scripts/scene_mood.py -- --time noon --overcast 0.8          # soft grey day
scripts/scene_mood.py -- --mood cyberpunk                    # moonless, neon rim pair, fog, bloom
scripts/scene_mood.py -- --time morning --fog-visibility 120 --fog-height 4   # valley fog
```
Times: `noon morning afternoon golden sunrise sunset blue_hour night moonless`. Moods: `cyberpunk horror underwater desert` (each sets defaults that explicit flags override). Override the sun with `--elevation DEG` (negative = below the horizon) and `--heading DEG` (0 = +Y, 90 = +X). If you leave out `--heading`, the sun sits 135° from the camera's view direction, which gives side/back light that shows form. Front light looks flat.

The script builds `ENV_World`, the `ENV_Mood` collection (sun or moon, fog box, accent lights) and, for moods, `ENV_Grade` (a compositor tree). Your objects are untouched, and re-running replaces everything it made. It returns the key light's strength, color and elevation, the exposure, and any warnings.

## How it stays physically right
- **Sky**: `ShaderNodeTexSky` `MULTIPLE_SCATTERING` (5.0+; `SINGLE_SCATTERING` is the legacy "Nishita") with `sun_disc=False`. A **Sun lamp** is the sun, because it gives sharp shadows in both engines. The lamp's color and its strength relative to the sky come from a table **measured from Blender 5.2's own sky model** at each elevation (sunset sun ≈ `[1.0, 0.22, 0]`, noon ≈ `[1.0, 0.86, 0.68]`). That keeps the sky and the sun consistent.
- **Scale**: noon gives a sun of ≈ 4 W/m² with a grey card at 0.18 under AgX at exposure 0.
- **Exposure balance**: each preset meters a grey card between the ground and a wall facing the sun, then scales the *environment* lights so the card lands at the preset's brightness (noon 1.0, golden 0.85, sunset 0.7, blue hour 0.35, night 0.2, moonless 0.1). Your practical lights keep their usual wattage and read correctly against it.
- **Physical alternative**: `--use-exposure` puts the difference in `view_settings.exposure` instead. The result returns `practical_scale`: multiply your lamp wattages by it to keep the same look.
- **Night**: the moon is a Sun lamp at 0.3 W/m² before scaling (35°, cool `[0.72, 0.82, 1.0]`; moonlight is physically ~4100 K, and it reads blue because of the Purkinje shift). The night dome is a zenith gradient, a city glow at the horizon (sodium orange; magenta for cyberpunk), and stars visible to camera rays only.
- **Fog**: a box volume around the scene and the camera. Density = **3.912 / visibility** (Koschmieder: visibility in meters → extinction per meter). Add `--fog-height` for an exponential ground fog. Exposure compensates for light lost in fog by up to 4 EV, so fog stays dense instead of just dark. The background seen by the camera is blended toward the fog color.

## Fog and volumetrics
| Look | `--fog-visibility` (m) |
|---|---|
| Clear air / distant haze | 5000–20000 |
| Haze, desert dust | 1000–3000 |
| Mist | 500–1000 |
| Fog | 100–500 |
| Dense fog, horror | 20–60 |
| Underwater (clear → murky) | 30 → 8 |
- **God rays** need four things: a strong key (sun/spot), occluders (windows, trees, a gobo), forward scattering (`--fog-anisotropy 0.6–0.85`), and EEVEE `use_volumetric_shadows` (the script turns it on).
- **Cycles 5.x** renders volumes with **null scattering** by default (unbiased, no step size). `scene.cycles.volume_biased=True` brings back ray marching (`volume_step_rate`). Height fog is a heterogeneous volume and is noisier, so give it more samples or denoise.
- **EEVEE** volumes are froxels: `volumetric_tile_size` 4 → 2 for detail, and `volumetric_end` must cover the fog (the script sets it). Very dense fog close to the camera bands, so prefer Cycles for it.
- Cheap distant haze without volumes: the Mist pass (`view_layer.use_pass_mist`, `world.mist_settings.start/depth`) mixed in the compositor.
- Deeper detail is in [references/fog-volumetrics.md](references/fog-volumetrics.md).

## Rules
- Decide the light direction first (side/back), then the time. Low sun (golden, sunset) = long shadows and warm key against a cool sky fill, which is the most flattering combination.
- Night is not "a blue tint": keep **contrast** (hard moon shadows, pools of warm practicals, dark silhouettes), lower saturation, and add practical sources. See [references/night-and-moods.md](references/night-and-moods.md).
- Practicals use real color temperatures (`light.use_temperature=True`, `light.temperature`): sodium 2000 K, tungsten 2700 K, warm LED 3000 K, neutral LED 4000 K, neon as emissive tubes. Watts and conversions are in [references/light-values.md](references/light-values.md).
- Keep the view transform AgX (the script sets it, along with a mood look like `AgX - Punchy`). `--keep-view` preserves yours.
- Verify every mood with a render, not the viewport: fog, stars and bloom only show in rendered output. Use `blender-rendering` `render_batch.py --preset preview`.

## Gotchas
- Below the horizon the sky texture shows a dark "ground". Extend the ground plane or terrain to the horizon, or keep the horizon out of frame.
- The bloom/glare threshold is **scene-linear, before** the view exposure. With `--use-exposure` the script scales the threshold for you.
- The script won't overwrite a compositor tree that isn't `ENV_Grade`; it reports that instead.
- `SunLight.use_nodes` and light node trees are deprecated in 5.x (removal planned for 6.0). Use light color and `temperature` instead.
- The sky texture's `sun_direction` only applies to the legacy Preetham/Hosek models. `sun_rotation` 0 places the sun toward +Y and 90° toward +X (measured).
- Changing the render engine doesn't need a re-run. The script sets both the EEVEE and Cycles volume settings.
