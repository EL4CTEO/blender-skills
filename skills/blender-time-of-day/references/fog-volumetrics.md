# Fog and volumetrics (5.2)

## Density from visibility
Meteorological visibility V (m) is where contrast drops to 2%. Extinction σ = 3.912 / V (Koschmieder), in units of 1/m (Blender units = meters). For Principled Volume with a white `Color`, `Density` ≈ σ.

| V (m) | σ (Density) | Look |
|---|---|---|
| 10000 | 0.0004 | clear air, distant mountains fade |
| 2000 | 0.002 | haze |
| 500 | 0.008 | mist |
| 150 | 0.026 | fog |
| 40 | 0.098 | dense fog |
| 15 | 0.26 | can't see across the street |

**Height fog**: `density(z) = σ · exp(−(z − ground) / H)`, H = 1–3 m (ground fog) or 5–20 m (valley/city). `scene_mood.py --fog-height H` builds it with Geometry Position → Math nodes.

## Phase function (forward scattering = glow around lights and god rays)
- Principled Volume `Anisotropy` 0.5–0.7 for fog and haze, 0.85 for water. 0 = isotropic, a flat look.
- Volume Scatter in 5.x has `phase`: `HENYEY_GREENSTEIN`, `FOURNIER_FORAND`, `DRAINE`, `RAYLEIGH`, `MIE`. `MIE` + `Diameter` (µm; fog droplets ~10–20) is the most physical choice for fog in Cycles. `RAYLEIGH` suits clear-air blue scattering. Principled Volume `Anisotropy` is the safe choice when a file must render in both engines.

## Cycles
- 5.0+: **null scattering** is the default (unbiased, handles mixed dense/thin volumes, no step size). `cycles.volume_biased = True` restores ray marching (`volume_step_rate`, `volume_max_steps`), which is sometimes faster for simple homogeneous fog.
- `cycles.volume_bounces` 0 = single scattering (fast, darker). 1–2 for dense, bright fog.
- Noise: volumes converge slowly. Use 256+ spp with adaptive sampling, the OIDN denoiser, and a **separate fog pass**: put the fog box in its own view layer, set the other objects to holdout, and composite. Fog denoises much better alone.
- `use_volume_guiding` (path guiding, CPU) helps dense lit fog.

## EEVEE (5.x)
- Froxel grid: `eevee.volumetric_tile_size` "2"/"4"/"8", `volumetric_samples` 64–128, and `volumetric_start/end`: the range must enclose the fog, and a tight range gives more precision.
- `use_volumetric_shadows` (+ `volumetric_shadow_samples`) is required for god rays.
- `volumetric_ray_depth` (accurate volume intersection) raises the count of overlapping volume surfaces you can stack before artifacts appear.
- World volumes are infinite in EEVEE; use a box for local fog. Thin slabs and very dense fog band, so use cards or Cycles for those.

## God rays checklist
Strong directional key → occluder with gaps (window frame, trees, slatted blinds) → fog σ 0.01–0.05 with anisotropy 0.6–0.8 → camera looking toward the light. Cycles gives crisp shafts. In EEVEE, enable volumetric shadows and use tile size 2.

## Cheap alternatives
- **Mist pass**: `view_layer.use_pass_mist`, `world.mist_settings` (`start`, `depth`, `falloff`). Mix the fog color in the compositor using the mist as the factor. No volume cost, but no light shafts.
- **Fog cards**: camera-facing planes with a soft alpha-noise emission/transparent material, for background layers. They intersect geometry visibly, so keep them clear of objects.
