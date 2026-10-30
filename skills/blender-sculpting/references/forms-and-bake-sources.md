# Forms, proportions, hard-surface sculpting, bake sources (operators verified in Blender 5.2.3)

## Human proportions (art canon, real scale in m)
| | Value |
|---|---|
| Height | adult ~1.75 m (male) / ~1.62 m (female). Model at real scale |
| Heads tall | realistic 7.5 · heroic 8–8.5 · stylized 5–7 · anime teen 6.5–7 · chibi 2–4. Head ≈ 0.22–0.23 m |
| Vertical landmarks | half height = pubis/greater trochanter. Nipples ≈ 2 heads from the top, navel ≈ 3, crotch ≈ 4. Knee ≈ halfway hip → sole |
| Arms | span ≈ height. Elbow at the waist, wrist at the crotch, fingertips mid-thigh (arms down) |
| Widths | shoulders ≈ 2 heads (male), 1.75 (female). Hips ≈ 1.5 (male), 1.75–2 (female) |
| Hand / foot | hand ≈ face height (chin → hairline). Foot ≈ forearm length (~0.26 m) |
| Face | eyes at half the head height, one eye-width apart. Nose base halfway brow → chin. Ears from brow to nose base. Mouth corners under the pupils |
Check proportions in an orthographic front/side view against a 1.75 m reference before any detail. Bad primary forms can't be saved by tertiary detail.

## Silhouette and form order
1. **Gesture/primary**: the big masses (ribcage, pelvis, skull as boxes/eggs), tilts and rhythm. They should read at 5% of screen.
2. **Secondary**: muscle groups, fat pads, bony landmarks (clavicle, iliac crest, kneecap, elbow), cloth folds. Work from planes, not blobs: flatten with `PLANE`, then soften.
3. **Tertiary**: skin pores, wrinkles, scratches, weave. Use Multires level 4–6 or (for games) normal/displacement maps from alphas.
Sculpt from reference, check every few minutes in a flat matcap from several angles, and turn the model upside down/mirrored to see errors fresh.

## Hard-surface sculpting (concepts, kitbash, organic-mechanical)
- **Trim gestures** cut or extrude crisp shapes: `sculpt.trim_box_gesture` / `trim_lasso_gesture` / `trim_line_gesture` (`trim_mode` DIFFERENCE/UNION/JOIN, `trim_solver` EXACT/FLOAT/MANIFOLD). `sculpt.project_line_gesture` flattens to a line.
- **Masks to parts**: paint a mask (or `sculpt.mask_from_cavity`), then `mesh.paint_mask_extract` (new shell object with thickness) or `mesh.paint_mask_slice` (split). `sculpt.face_set_extract` does the same per face set. Ideal for armor plates on a body.
- **Panels**: Face Sets (`sculpt.face_sets_init` by loose parts/normals/UV seams) + `sculpt.expand` for clean borders. Then `sculpt.mesh_filter(type="SHARPEN"|"RELAX_FACE_SETS"|"SURFACE_SMOOTH")` to crisp or relax along them.
- **Remesh in between**: `object.voxel_remesh` fuses cuts. 5.2 interpolates color attributes during voxel remesh, which is less scrambling but a bit blurrier.
- For production game props, hard-surface is usually polygon modeling (`blender-hardsurface-modeling`). Sculpt hard-surface for concepts and organic/mechanical blends.

## Multires tricks
- `object.multires_rebuild_subdiv` recovers subdivision levels from an imported dense mesh that came from a subdivided base. `object.multires_unsubdivide` finds a lower base from a dense uniform mesh.
- `object.multires_reshape` moves the detail of one mesh onto another with the same base topology (e.g. after a retopo with identical base).

## Preparing a high-poly bake source (→ `blender-texture-baking`)
- **Watertight where rays land**: no holes, no inverted parts (run `blender-asset-qa` on the high with `--profile render`). Overlapping floaters are fine (they bake as surface detail), interpenetrating thin shells are not (AO and normal leaks).
- **Density**: at least ~1 high-poly face per texel of the target map over the region. A 2k map on a 1 m prop needs about 2–4 M faces at the detail. Decimate the high (`Decimate` collapse 0.2–0.4) before baking to cut memory: normals survive it.
- **Same silhouette**: the low must envelope the high within the cage distance (1–2% of the object size). Bevel or chamfer high-poly edges so normals have something to capture (0.5–2 mm on props).
- **Naming for bake-by-name**: `Crate_high` / `Crate_low`, one pair per exploded part. Explode overlapping parts (move apart) before baking, or use bake groups, so the AO/normal of one part doesn't project onto another.
- Apply symmetry and scale. Keep the high in its own collection, excluded from export.
- External bakers (Marmoset, Substance): export the high as `.ply`/`.fbx` with smooth normals, triangulated low with tangents (`blender-export-pipelines`).
