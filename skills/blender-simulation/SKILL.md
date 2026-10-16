---
name: blender-simulation
description: Physics in Blender 5.2 - rigid bodies (density mass, shapes, bake to keys), classic cloth presets and pinning, new node-based Cloth/Hair Dynamics (XPBD, Collider, effectors), Mantaflow fluids, hair curves, GN simulation zones, headless baking. Use for destruction, drapes, flags, falling objects, liquids, smoke, hair motion.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Simulation

The execution model is in `blender-core`. Procedural sim zones are in `blender-geometry-nodes`.

## One call
```
scripts/sim_setup.py -- --rigid --active Crate1 Crate2 --passive Floor --density 500 --frames 1 120 --bake --to-keys
scripts/sim_setup.py -- --cloth Flag --preset cotton --pin Pin --colliders Pole --bake
scripts/sim_setup.py -- --gn-cloth Sheet --colliders Table --set Bendiness=0.5 Stretchiness=0.1 --bake
```
`--bake` steps through every frame in order (this works headless for point caches **and** GN simulation zones) and reports final positions and `min_z`, so you can verify contact. `--to-keys` turns rigid-body motion into keyframes for engines.

## Choose the solver
| Need | Use |
|---|---|
| Falling/stacking/destruction | Rigid Body (Bullet). Pre-fracture with Cell Fracture (extension) or GN Voronoi |
| Clothing, flags, drapes (production-proven) | Classic **Cloth** modifier + Collision modifiers |
| New node-based cloth/hair, custom forces, procedural setups | **Cloth Dynamics (Experimental)** / **Hair Dynamics** assets (5.2, XPBD) |
| Liquids, smoke, fire | Mantaflow fluid domain + flow/effector (`fluid.bake_all`) |
| Hair grooms | Curves objects + hair node assets (`procedural_hair_node_assets`), Hair Dynamics for motion |
| Growth, trails, custom per-frame logic | GN Simulation zone |
| Soft jiggle for games | bones with spring/jiggle in-engine, or Wiggle-style constraints baked to keys |

## Rigid bodies
- Real scale and real mass matter: mass = volume × density (wood 500–700, concrete 2400, steel 7850, plastic 950 kg/m³). The script computes it.
- Collision shape: `CONVEX_HULL` for dynamic objects (fast, stable), `MESH` only for **passive** concave colliders, and primitives (`BOX`, `SPHERE`, `CAPSULE`) when they fit.
- Stability: substeps 10 and iterations 10 (set by the script). Use a small collision margin (1 mm). Avoid objects starting interpenetrated.
- Export: bake to keyframes (`--to-keys`; the built-in `rigidbody.bake_to_keyframes` needs a UI, so the script samples `matrix_world` itself), then export the actions (`blender-export-pipelines`).

## Classic cloth
- Presets (from Blender's): cotton, denim, leather, rubber, silk. The mesh needs even quad density (2–5 cm edges for clothing). Use a subdivided plane or retopologized garment, never ngons.
- **Pinning**: vertex group with weight 1 = pinned (`settings.vertex_group_mass`). Animate pinned verts with hooks/armature.
- Collisions: colliders get a `COLLISION` modifier (thickness 1–5 mm), plus self-collision for folds. Raise `quality` (steps) for fast motion.
- Apply cloth as a shape (`modifier_apply_as_shapekey`) or bake to an Alembic/point cache for render. Games: bake to bones, or apply a static drape.

## Node-based dynamics (5.2, experimental)
- Assets live in `datafiles/assets/nodes/geometry_nodes_dynamics_assets.blend`: `Cloth Dynamics (Experimental)`, `Hair Dynamics`, `Collider`, `Set Effector`, `Custom Force`, `Custom Effector`. The script appends them.
- Cloth inputs include `Pin Group` (attribute), `Stretchiness`, `Bendiness`, `Substeps` (5), `Constraint Steps` (15), `Mass`, `Friction`, `Collision Radius`, `Linear Damping`, `Gravity`, `Tearing` (+ mode/threshold), `Effectors Collection`, `Effectors` (bundle).
- Colliders: put a `Collider` modifier on each collider object and add those objects to the collection fed into `Effectors Collection` (the script does both).
- Hair: Add → Empty Hair sets up the surface + `Capture Rest Geometry`. Hair Dynamics reads the rest/deformed surface through geometry bundles.
- Limits (5.2): no self-collision yet, no built-in wind/turbulence (build a `Custom Force`). Interfaces may change, so pin the Blender version in production.
- The solver itself (`GeometryNodeXPBDSolver`) takes a `World` bundle, `Delta Time`, `Substeps`, `Constraint Iterations`. Building directly on it is advanced; start from the assets.

## Fluids (Mantaflow) quick setup
Domain object (`FLUID` modifier `fluid_type="DOMAIN"`, `domain_type="LIQUID"|"GAS"`), resolution 64 preview / 128–256 final, cache directory set and `cache_type="ALL"` for headless; flow objects `fluid_type="FLOW"` (`flow_type` LIQUID/SMOKE/FIRE, `flow_behavior` INFLOW/GEOMETRY); obstacles `EFFECTOR`. Bake with `bpy.ops.fluid.bake_all()` under a context override with the domain active. This is slow. Test at low resolution first.

## Rules
- Simulations are frame-rate and scale dependent. Set `scene.render.fps` and the scale before tuning.
- Always bake before rendering/exporting, and never rely on viewport playback order.
- GN simulation zones: bake per modifier (`mod.bakes`, `object.geometry_node_bake_single`), or step frames sequentially (script) in background.
- Point caches in background: stepping frames from `frame_start` fills the cache. `ptcache.bake_all(bake=True)` needs a valid context.
- Verify with `look(mode="frames")` plus the numbers (`min_z` ≈ the collider top = contact, no tunnelling).

## Gotchas
- Objects tunnelling through colliders: thin colliders, too few substeps, or too-fast motion. Thicken, raise substeps/quality, or use a bigger collision distance.
- Exploding cloth at frame 1: starting interpenetration or a zero-area face. Run `blender-asset-qa`, offset the start.
- Rigid body world cache ranges are separate from the scene range (the script syncs them).
- Changing anything (frame range, settings) invalidates caches. Re-bake.
