---
name: blender-sculpting
description: Sculpting in Blender 5.2 - base-to-detail workflow, voxel remesh, dyntopo, multires, 5.x brush types, masks/face sets, symmetry, plus headless-safe procedural ops for agents (remesh, symmetrize, multires, inflate, noise detail, smooth) and the sculpt-to-game handoff. Use for organic models, characters, creatures, rocks and bake sources.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Sculpting

The execution model is in `blender-core`. The handoff goes to `blender-retopology-uv` → `blender-texture-baking`.

## Agents: what you can and can't do
- **Sculpt Mode operators crash Blender in background mode** (`-b`), including `mesh_filter`. Never enter Sculpt Mode headless.
- Headless or MCP: use `scripts/sculpt_ops.py` for object-level ops: `remesh=SIZE`, `symmetrize=+X`, `multires=N`, `inflate=D`, `detail=STR,SCALE`, `smooth=N`, `apply`. Combine these with Geometry Nodes (`blender-geometry-nodes`: SDF grid booleans/fillets, noise displacement) and shape modeling for procedural organic forms.
- Live sessions with a UI: brush strokes via `bpy.ops.sculpt.brush_stroke(stroke=[...])` need a 3D View region override and are fragile. Prefer procedural ops, then show the user with `look`. Hand detailed brushwork to the human.

## Professional workflow
1. **Base mesh / blockout**: primitives, metaballs, Skin modifier, or a low-poly base at real scale. Proportions first: compare with references and check against a human 1.75 m.
2. **Unify**: voxel remesh (`remesh=0.02` for a 2 m character, smaller for detail) fuses parts and gives even density. Repeat it while the big forms change.
3. **Primary forms** at low resolution (Grab, Snake Hook, Clay Strips, Inflate, Smooth). **Secondary** (muscle groups, folds) at medium resolution. **Tertiary** (pores, scratches, fabric weave) with Multires levels 4–6, or as normal/displacement maps.
4. **Dynamic topology** (`sculpt.dynamic_topology_toggle`): adds detail where you stroke. Good for concept sculpting, bad for final topology and multires (it destroys UVs/multires). Use voxel remesh + multires for production.
5. **Multires**: subdivide (`multires_subdivide`, Catmull-Clark) on a clean quad base (after retopo) to sculpt high detail that bakes back to the base level (`blender-texture-baking`, multires bake or high→low).
6. **Handoff**: export the high (or keep it in-file), retopo to `_low`, UV, bake normal/AO/curvature, then texture.

## Brushes (5.x: brushes are assets in the Essentials library)
| Purpose | `sculpt_brush_type` |
|---|---|
| Build volume | `CLAY_STRIPS`, `CLAY`, `CLAY_THUMB`, `LAYER`, `INFLATE`, `BLOB` |
| Shape / move | `GRAB`, `SNAKE_HOOK`, `ELASTIC_DEFORM`, `POSE`, `BOUNDARY`, `CLOTH`, `NUDGE`, `ROTATE`, `THUMB` |
| Details / edges | `DRAW`, `DRAW_SHARP`, `CREASE`, `PINCH` |
| Flatten / hard surface | `PLANE` (flatten/fill/scrape), `MULTIPLANE_SCRAPE` |
| Clean up | `SMOOTH`, `SIMPLIFY` (dyntopo), `DISPLACEMENT_ERASER`/`SMEAR` (multires) |
| Masking / grouping | `MASK`, `DRAW_FACE_SETS`; Expand (`sculpt.expand`), mask from cavity |
5.0 renamed `brush.sculpt_tool` → `sculpt_brush_type`. 5.1 folded the stroke options into `brush.stroke_method` (`DOTS`, `DRAG_DOT`, `SPACE`, `AIRBRUSH`, `ANCHORED`, `LINE`, `CURVE`). 5.2 moved automasking to `brush.mesh_automasking_settings` / `paint.mesh_automasking_settings`.

## Rules of thumb
- Sculpt at **real scale**, with scale applied. Brush radius is in screen space but strength and remesh sizes depend on scale.
- Use symmetry (`mesh.use_mirror_x`, radial: `mesh.radial_symmetry`) on characters until the asymmetry pass at the end.
- Face Sets organise parts (head, torso, hands). Hide them and mask by face set to isolate.
- Watch density: a 2 m character at voxel 0.005 is already millions of polys. Keep viewport FPS usable and work up in levels.
- Silhouette first. Check from several angles in flat matcap (`look` shading `solid`) before adding detail.
- Floaters/kitbash for hard-surface details on organic models: separate objects, combined at bake time.
- Before baking, run `blender-asset-qa` on the high (no inverted parts, no huge self-intersections in the bake range).

## Gotchas
- `voxel_remesh` destroys UVs, vertex groups (unless preserve attributes) and multires levels. Do it before UVs/rigging.
- Multires + topology changes don't mix: never edit the base topology after subdividing (apply the base or rebuild).
- `symmetrize` on a non-centered object mirrors across the **object's local axis**. Center the origin on the symmetry plane first.
- Sculpting on shape keys: enable `use_shape_key_edit_mode` and sculpt on the active key (facial work, `blender-facial-shapekeys`).
