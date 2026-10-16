# Weather values and look library

## Rain
| Quantity | Value |
|---|---|
| Terminal velocity by drop diameter | 0.5 mm ≈ 2 m/s · 1 mm ≈ 4 · 2 mm ≈ 6.5 · 5 mm ≈ 9 m/s (Gunn & Kinzer) |
| Rain rate classes | light < 2.5 mm/h · moderate 2.5–7.6 · heavy > 7.6 (AMS) |
| On camera | a streak = speed × exposure time: 7 m/s × 1/48 s ≈ 15 cm at 24 fps with a 180° shutter |
| Splash | crown 2–4 cm, lives ~50–100 ms; secondary droplets bounce 5–10 cm |
| Water | IOR 1.33, roughness 0–0.05 still, 0.05–0.15 rippled |
- Visible density is far lower than physical density (thousands of tiny drops per m³). `precipitation.py` uses 5–80/m³ of *visible* streaks; storms read better with fog and wind than with more particles.
- Wind tilts the rain: 2–5 m/s for a slant, 10+ for a storm. Gusts: keyframe the modifier's `Wind` input.
- Rain is lit by what's behind it. Rim and backlight it (street lamps, headlights, a bright sky). Against a bright sky it reads dark; against a dark background it reads bright.

## Wet surfaces (after Lagarde, "Water drop" series)
- Porous materials (asphalt, concrete, brick, wood, fabric) darken by 20–50% as water fills the pores. Non-porous ones (metal, glass, plastic, car paint) don't darken, they only gain a water film.
- Wet roughness drops sharply. Puddles are mirrors (water film ≈ 0.02) and hide the underlying normal detail (`surface_weather.py` flattens the base normal under puddles).
- Puddles collect in low, flat areas: up-facing faces and cavities. To place them yourself, paint a vertex color or mask and feed it to the group's `Puddles` input.
- Drying edges: a thin darker rim around puddles (the wet halo) sells it. Widen the mask edge if needed.

## Snow
| Quantity | Value |
|---|---|
| Fall speed | flakes 0.5–1.5 m/s, graupel 1–3 m/s |
| Flake size | 2–10 mm (big wet flakes up to 2–5 cm in calm air) |
| Albedo | fresh 0.8–0.9 · old/settled 0.6–0.8 · melting/dirty 0.4–0.6 |
| Look | strong subsurface (blue-shifted radius), roughness 0.5–0.7, sparkle = tiny glossy flakes |
- Snow settles on surfaces facing up, thins at edges, and is absent under overhangs. The shader handles facing; occlusion needs a painted mask or a raycast/AO bake.
- Real thickness (`--snow-depth`) matters on roofs, ledges and the ground. Thin dustings stay shader-only.

## Dust, ash, embers
- Dust: tiny (0.5–1 mm), slow, floating (sway). Visible only in beams of light, so pair it with fog + god rays.
- Ash: flat flakes, slow tumbling fall, dark grey; post-fire or volcanic mood.
- Embers: emissive orange (strength 10–50), rising and swaying, short-lived. Pair with bloom (`scene_mood.py` grade) and a warm point light near the fire.

## Lightning
- A flash is 3–4 return strokes ~40–60 ms apart, 0.2–0.5 s total; the bolt channel shows a bright core with glow.
- Cloud-to-ground bolts start at the cloud base (1–3 km up). Branches fork downward.
- The flash lights the scene from the strike direction with cool white light (≈ 8000 K), stronger than the moon.
- Use 1–3 flashes per shot. Constant flashing reads as a strobe, not a storm.
