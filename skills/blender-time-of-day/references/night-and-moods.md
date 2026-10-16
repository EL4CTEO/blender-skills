# Night, blue hour and stylized moods

## Night that reads as night
1. **Contrast, not darkness**: one hard key (moon, high sun lamp angle ≈ 0.5°, crisp shadows) plus pools of warm practicals, with backgrounds falling to silhouette. A uniformly dim, blue image reads as underexposed day.
2. **Color split**: cool ambient/moon (`[0.72, 0.82, 1.0]` or 7000–9000 K) against warm practicals (2000–3000 K). The complementary contrast sells it.
3. **Lower saturation**: compositor Hue/Saturation 0.7–0.85. The eye loses color vision at night (Purkinje shift).
4. **Night sky**: night HDRIs often contain light pollution that ruins rural scenes, so use the procedural dome (`--city-glow 0` for wilderness). The moon disc is not rendered: put a textured plane far away, or use an HDRI with a moon, if it must be visible.
5. **Practicals first in a moonless scene**: windows, street lamps and signs carry the image. Add a little fog (`--fog-visibility 200–500`) so lights bloom and cast visible cones.
6. **Camera**: a real night exposure means a longer shutter (more motion blur), a wider aperture (shallower depth of field) and grain. Keep `render.motion_blur_shutter` at 0.5 or above for moving elements.
7. **Workflow**: turn lights on one at a time. A night scene with ten lights often works with three. Use light groups / light linking (`blender-lighting-lookdev`) to balance them without moving them.

## Blue hour (sun 4–6° below the horizon)
- Sky-only lighting: soft and deep blue, with no shadows. The best moment is when the practicals balance the sky, not overpower it: the script's balance keeps 50 W lamps visible but not blown out.
- Windows and street lights on, a warm/cool split, a long exposure look (smooth water, light trails).

## Golden hour / sunset
- Sun 0–8°: warm key (measured `[1, 0.55, 0.16]` at 6°), long shadows, blue shadow fill from the sky.
- Backlight or rim the subject and let the sun flare (compositor Glare `Fog Glow` or `Streaks`, threshold 1).
- Haze adds depth: `--fog-visibility 2000–5000` with `--fog-color 1 0.85 0.7`.

## Moods (`--mood`)
| Mood | Time and key | Atmosphere | Grade |
|---|---|---|---|
| cyberpunk | moonless; magenta + cyan area rim pair | fog 150 m, 10 m height, magenta city glow | AgX - Punchy, bloom 0.6, saturation 1.1 |
| horror | night; low moon 12°, sickly cyan | fog 35 m hugging the ground (1.5 m) | AgX - High Contrast, saturation 0.55, darker |
| underwater | sun 70° through water | uniform volume 30 m, teal scatter, absorption tint | AgX - Base Contrast, saturation 0.9 |
| desert | sun 45°, hot | warm haze 3000 m | AgX - Medium High Contrast, warm white point |

### Finishing each mood
- **cyberpunk**: wet streets are half the look (`blender-weather-fx` `surface_weather.py --wetness 0.7 --puddles 0.5`). Add emissive neon signs (strength 10–30) with light-linked spill, and rain for drama.
- **horror**: one motivated source (a flickering bulb: keyframe the energy with noise), deep vignettes, fog between the camera and the subject, a desaturated green-cyan cast. Hide the threat in silhouette.
- **underwater**: caustics need either a gobo/projected texture or Cycles caustics, which are slow. The fast fake is an animated Voronoi caustic pattern (W or Mapping driven by `frame`) added as brightness in the ground's shader, or on a gobo plane in front of a spot light. Add floating particles (`precipitation.py --type dust`), god rays from the surface (anisotropy 0.85), and blur the background.
- **desert**: high sun, short shadows, bleached highlights. Add a heat shimmer in comp (`CompositorNodeDisplace` driven by a small animated noise) and dust particles in the air. Use high albedo sand (0.4–0.6 sRGB).

## Grade order (compositor, 5.x API: options are input sockets)
Render Layers → Glare (`Type` "Bloom" / "Fog Glow", `Threshold` 1, `Strength`) → Color Balance (`Type` "White Point", `Input Temperature`) → Hue/Saturation → (Lens Distortion `Dispersion` 0.01–0.03 for a stylized look) → Group Output. `scene.compositing_node_group` holds the tree.
