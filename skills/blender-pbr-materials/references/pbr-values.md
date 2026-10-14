# Measured PBR values

Linear values plug straight into socket `default_value`. sRGB values are for textures and color pickers.
Sources: Unreal Engine physically-based materials docs, physicallybased.info, DONTNOD charts.

## Metals (base color = F0, metallic 1)
| Metal | Linear RGB | sRGB 8-bit | Typical roughness |
|---|---|---|---|
| Silver | 0.972, 0.960, 0.915 | 252, 250, 245 | 0.1–0.3 |
| Aluminum | 0.913, 0.922, 0.924 | 245, 246, 246 | 0.2–0.5 |
| Gold | 1.000, 0.766, 0.336 | 255, 226, 155 | 0.1–0.35 |
| Copper | 0.955, 0.638, 0.538 | 250, 208, 192 | 0.2–0.45 |
| Brass | 0.910, 0.778, 0.423 | 244, 228, 173 | 0.2–0.4 |
| Iron / steel | 0.560, 0.570, 0.580 | 196, 199, 199 | 0.3–0.6 (brushed 0.25 + anisotropic) |
| Chromium | 0.550, 0.556, 0.554 | 196, 197, 196 | 0.02–0.15 |
| Titanium | 0.542, 0.497, 0.449 | 194, 187, 177 | 0.3–0.5 |
| Nickel | 0.660, 0.609, 0.526 | 211, 203, 190 | 0.2–0.4 |
| Platinum | 0.672, 0.637, 0.585 | 213, 208, 200 | 0.15–0.35 |

## Dielectrics (metallic 0, IOR 1.5 unless noted)
| Material | sRGB albedo (approx) | Roughness |
|---|---|---|
| Charcoal / black rubber | 50, 50, 50 | 0.8–0.95 |
| Asphalt (fresh / worn) | 60 / 90 | 0.8–0.95 |
| Car tire | 40 | 0.85 |
| Black plastic | 30–45 | 0.3–0.6 |
| White plastic | 220–230 | 0.2–0.5 |
| Concrete | 130–150 | 0.8–0.95 |
| Brick (red) | 150, 80, 60 | 0.8–0.9 |
| Wood (oak, unfinished) | 160, 120, 80 | 0.6–0.8; varnished 0.2 + Coat |
| Fabric (cotton) | (color) ≤ 230 | 0.8–1.0 + Sheen 0.3–0.6 |
| Leather | (color) | 0.4–0.7 |
| Skin (light / dark) | 230, 180, 160 / 90, 60, 45 | 0.4–0.6, Subsurface 1, IOR 1.4 |
| Grass | 75, 110, 45 | 0.6–0.8 |
| Sand | 190, 170, 130 | 0.8–0.95 |
| Fresh snow | 240, 240, 240 | 0.6–0.8 |
| Water | 255 + Transmission 1 | 0.0–0.05, IOR 1.33 |
| Glass | 255 + Transmission 1 | 0.0, IOR 1.5 (Thin Wall for windows: 5.2) |
| Car paint | (color) | 0.3–0.5 base, Coat 1 rough 0.03 |
| Ceramic / porcelain | 230–240 | 0.05–0.2 |

## Sanity checks for a texture set
- Average base color luminance for dielectrics: sRGB 50–200 (mean ~120). Pure black (0) or pure white (255) pixels on dielectrics are almost always wrong.
- Metal base color below sRGB 180: the metallic mask or albedo is wrong (it's probably dirt that should be dielectric).
- Roughness map near-uniform (std dev < 0.02): add variation.
- Normal map average ≈ (128, 128, 255). If the average blue is < 200 or the RGB is far off, the color space is wrong, or it's a height map labeled as normal.
- Check with `img.pixels.foreach_get(arr)` + numpy (`arr.reshape(-1,4)[:,:3].mean(0)`).
