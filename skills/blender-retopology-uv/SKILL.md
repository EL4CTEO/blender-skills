---
name: blender-retopology-uv
description: Retopology and UVs in Blender 5.2 - auto retopo (Quadriflow, Decimate, planar), deformation edge flow, seams, unwrap (Angle Based, Minimum Stretch, Smart), pixel-margin packing, texel density measure/set, lightmap UV2, UDIMs, mirrored UVs. Use to turn sculpts/scans/AI meshes into game meshes or prep UVs for texturing/baking.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Retopology & UVs

The execution model is in `blender-core`.

## Retopology
**Automatic** (`scripts/auto_retopo.py -- --objects Sculpt --tris 8000 --method ...`) makes `<name>_low` and leaves the source hidden:
| Method | Use for | Notes |
|---|---|---|
| `quadriflow` | organic props, static characters, scans | clean quads. Voxel-remeshes first so the input is manifold; UVs are lost (re-unwrap) |
| `decimate` | background props, LODs, AI-generated meshes | keeps UVs/shape, gives triangles. Fast |
| `planar` | hard-surface CAD/boolean results | dissolves flat areas; keeps seams/sharp/material/UV borders |

**Manual** (hero characters, anything that deforms). Set up a new mesh object with a Shrinkwrap modifier (`PROJECT`, target = sculpt), snapping to `FACE_PROJECT` + `use_snap_project`, and the source in a different viewport color/x-ray. Auto retopo isn't good enough for deforming hero meshes, because the edge flow below matters.

### Edge flow rules for deforming meshes
- Concentric loops around the eyes and mouth (≥3 rings). The nasolabial loop flows from the nose wing to the mouth corner.
- **3 loops** at every bending joint (elbow, knee, finger knuckles), plus a loop on each side to keep volume. The shoulder needs extra loops for raising the arm.
- Keep poles (3/5-edge verts) out of bending areas. Put them on flat, stiff regions (chest, back of skull).
- Distribute quads evenly, with density where deformation and silhouette need it. Use triangles only in hidden, non-deforming spots.
- Character tri budgets in 2026: mobile 5–15k, Roblox body ≤ 10.7k total, console/PC third-person 30–80k, hero/cinematic 100k+. Check the target in `blender-game-optimization`.

## UVs
1. **Seams**: hide them (under arms, inner legs, back of the head, under parts), follow hard edges, cut cylinders on the back side. Rule for game meshes: every hard edge (>~60°, `sharp_edge`) **must** be a UV seam, or the normal map shows artifacts. `scripts/uv_pack.py --seams-from-sharp 60` does this.
2. **Unwrap**: `--method seams` (Angle Based with marked seams), `--method min_stretch` (SLIM, 4.3+, least distortion on organics), `--method smart` (hard-surface/auto, `--angle 66`).
3. **Straighten** rectangular islands (Follow Active Quads, live only) so trims and pixel grids line up.
4. **Average island scale + pack** with margin in pixels: 2k → 8 px, 4k → 16 px, mobile 1k → 4 px. `--shape CONCAVE` gives the tightest pack (slow headless). The default `AABB` is instant.
5. **Texel density** (`scripts/texel_density.py --res 2048`): keep `spread` ≤ 1.3 within an asset. Set it with `--set <px/m>`; if `fits_0_1` is false, change res or density.
6. QA: `blender-asset-qa` reports zero-area UV faces and overlap %.

### Texel density targets (px/m; studio baselines, not laws)
| Context | px/m |
|---|---|
| First-person hero / weapons | 1024–2048 |
| First-person environment | 512–1024 |
| Third-person games | 512 (console/PC), 256 (mobile) |
| Top-down / strategy | 128–256 |
| Roblox | ~256–512 per texture: 5×5 studs → 256², 10×10 → 512², 20×20 → 1024² |
Everything in the same scene should share one density. The exception is hero assets, kept within 2x.

## Special cases
- **Mirrored/stacked UVs** save space but break unique bakes. Move the duplicate islands exactly +1 U (outside 0–1) during baking, then move them back. Their normal maps must be mirror-safe (tangent space handles it in engines with MikkTSpace).
- **Lightmap UV2** (`--lightmap`, gives `UVMap_Lightmap`): no overlaps, every island inside 0–1, generous margin. Unreal/Unity can generate their own; ship one only if the engine pipeline wants it. Keep UV0 active for texturing.
- **UDIMs** (film/hero): islands in tiles 1001+ (U offset 1 per tile). Texture node image `source="TILED"`. Game engines mostly don't support UDIMs.
- **Trim sheets**: unwrap the strips, then scale/move the islands onto the trim rows (V positions from the trim layout). Islands may exceed 0–1 in U for tiling.
- **Roblox**: exactly one UV set, all inside 0–1. Overlaps are allowed.

## Gotchas
- 5.0+: UV selection is shared across UV maps (`.uv_select_*` attributes). Old `BMLoopUV.select` code fails.
- `uv.*` operators run in Edit Mode and act on selected faces. Select everything first (scripts handle this).
- Headless `uv.pack_islands` with `CONCAVE`/`CONVEX` + rotation can take 2–25 s even on tiny meshes. Use `AABB` while iterating.
- Unwrap warning "failed to solve island": the island has no seams (closed shape). Add seams.
- Apply scale before measuring texel density, or the density reads wrong (the scripts use world space and already account for scale).
