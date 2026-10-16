# Light values (measured in Blender 5.2.2)

## Sun by elevation (Multiple Scattering sky, altitude 100 m, default air/aerosol/ozone)
Sun color = normalized direct-normal irradiance. "Sun W/m²" is the lamp strength `scene_mood.py` uses before exposure balancing (sky strength 0.0285). "Sky share" = sky irradiance on a horizontal plane ÷ direct irradiance on a horizontal plane.

| Elevation | Name | Sun color (RGB) | Sun W/m² | Sky share |
|---|---|---|---|---|
| 60° | noon | 1.00 0.86 0.68 | 4.0 | 0.12 |
| 35° | afternoon | 1.00 0.83 0.61 | 3.7 | 0.16 |
| 20° | morning | 1.00 0.78 0.49 | 3.2 | 0.26 |
| 6° | golden | 1.00 0.55 0.16 | 1.4 | 0.98 |
| 1° | sunrise/sunset | 1.00 0.22 0.00 | 0.19 | 17 |
| −4° | blue hour | (no direct sun) | 0 | sky only, strongly blue |
| < −12° | night | (sky ≈ black) | 0 | use the night dome + moon |

The sky goes from dominating at the horizon to about 12% of the light at noon. This is why golden hour shadows are blue and noon shadows are deep.

## Lamp units (measured: white Lambert plane, Cycles)
| Lamp | Irradiance at distance r |
|---|---|
| Sun, strength S | E = S (W/m²) |
| Point / spot, power P | E = P / (4π r²) |
| Area (small, on axis), power P | E = P / (π r²) |
A grey card reads 0.18 when E ≈ π (≈ 3.14) at exposure 0.

## Color temperature of real sources
| Source | Kelvin |
|---|---|
| Candle / fire | 1800–1900 |
| High-pressure sodium street lamp | 2000–2200 |
| Tungsten bulb | 2700 |
| Warm LED / halogen | 3000 |
| Neutral LED street lamp / fluorescent | 4000–4500 |
| Moonlight (physical) | ~4100 (render it cooler: Purkinje shift) |
| Noon sun | 5500–5800 |
| Overcast sky | 6500–7500 |
| Blue-hour sky | 9000–12000 |
In 5.x: `light.use_temperature = True; light.temperature = 2700`. `light.color` still multiplies the temperature color.

## Practical wattages (exposure 0, the scene_mood balance)
| Source | Blender light |
|---|---|
| Table lamp / 60 W bulb | point 30–60 W, radius 0.05 m |
| Street lamp | spot 200–600 W, 2000–4000 K, spot size 100–140° |
| Window glow (interior lit) | area light in the window or emission 2–10 |
| Neon tube | emission strength 5–30 on a tube mesh + a weak area light for the spill |
| Car headlight | spot 300–800 W, blend 0.3, 5000 K |
With `--use-exposure`, multiply by the returned `practical_scale`.

## Sky texture parameters
- `altitude` (m): higher = darker, bluer sky with less haze. `air_density` scales Rayleigh (blue). `aerosol_density` scales Mie (haze, whiter sky, a bigger glow around the sun). `ozone_density` deepens twilight blue.
- Hazy or polluted day: `aerosol_density` 2–5. Crisp mountain air: `altitude` 2000+, `aerosol_density` 0.3.
- Both scattering models are very bright by default (physical units), so keep them balanced with a sun lamp or exposure. Never crank the strength to 1 and leave it.
