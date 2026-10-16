---
name: blender-geometry-nodes
description: Geometry Nodes in Blender 5.2 - fields, domains, attributes, instancing, zones (simulation/repeat/for-each), closures/bundles, lists, SDF grids, node tools, baking, plus a JSON-to-node-tree builder and socket inspector. Use for scattering, procedural assets/environments, parametric tools and modifier inputs.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Geometry Nodes

The execution model is in `blender-core`. Build trees with `scripts/gn_builder.py`, a compact JSON spec that's far cheaper than raw bpy. Look up exact socket names first, because they change between versions:
```
scripts/gn_builder.py -- --describe GeometryNodeDistributePointsOnFaces GeometryNodeInstanceOnPoints
scripts/gn_builder.py -- --spec scatter.json --apply Ground --set Density=20 Seed=3 Mask=@paint_mask
```
`--set Name=@attr` feeds a modifier input from a named attribute. The result reports evaluated vert/face counts and node warnings. The spec format is in the script docstring; full examples are in [references/recipes.md](references/recipes.md).

## Core concepts (get these right or nothing works)
- **Geometry** flows left→right through sockets with **circle** shapes. **Fields** (diamond sockets) are functions evaluated per element **on the node that consumes them**, in that node's domain/context.
- **Domains**: Point, Edge, Face, Face Corner, Spline, Instance, Layer. `Capture Attribute` freezes a field at a point in the graph (before topology changes), and `Evaluate on Domain` converts between domains.
- **Attributes**: built-ins (`position`, `normal`, `sharp_face`, `material_index`, `UVMap`...) plus named ones via `Store Named Attribute`. Named attributes persist after the modifier. That's how GN data reaches shaders (Attribute node) and exporters (glTF `export_attributes`, which exports names starting with `_`).
- **Instances** are cheap (one mesh, many transforms). **Realize Instances** only when you must edit per-instance geometry or export a single mesh. Realize as late as possible.
- Inputs exposed on the group interface become **modifier inputs** (5.2: `mod.properties.inputs.<identifier>.value`). Panels group them, menu sockets give enums.

## Zones and advanced types
| Feature | Nodes | Use |
|---|---|---|
| Simulation zone | `GeometryNodeSimulationInput/Output` (paired) | per-frame state: growth, particles, erosion; bake to keep |
| Repeat zone | `GeometryNodeRepeatInput/Output` | iterate N times (L-systems, relaxation, recursive subdivision) |
| For Each Element | `GeometryNodeForeachGeometryElementInput/Output` | run a sub-graph per element (per building lot, per island) |
| Closures / Bundles (5.0+) | `NodeClosureInput/Output`, `NodeCombineBundle`/`NodeSeparateBundle`, Evaluate Closure | pass functions/structured data around; reusable "strategy" node groups |
| Lists (5.2) | `GeometryNodeFieldToList`, `ListGetItem`, `ListLength`, `SortList`, `FilterList` | real arrays, not fields |
| Grids/SDF (4.x–5.x) | `MeshToSDFGrid`, `SDFGridBoolean`, `SDFGridFillet`, `SDFGridOffset`, `GridToMesh` | smooth booleans, remeshing, fillets, voxel effects |
| Physics (5.2, experimental) | `GeometryNodeXPBDSolver` + bundles | node-based cloth/hair, see `blender-simulation` |
| Gizmos | `GizmoLinear/Dial/Transform` | viewport handles for inputs |
Zones need `input.pair_with_output(output)` (spec key `pairs`), plus items on the output node (`repeat_items`, `state_items`, ...; spec 4th node field).

## Procedure
1. Sketch the data flow: source geometry → selection/masks (fields) → generate/instance → transform/randomize → realize/merge → set materials/shading → output.
2. `--describe` every node type you'll use, then write the spec and build. Check `node_warnings` and the evaluated counts.
3. Expose only meaningful inputs (density, seed, scale range, materials), with min/max set.
4. Look at it (`look`), check `blender-asset-qa` if the result will be exported (realized geometry), and check `blender-game-optimization` for instance counts and tris.
5. Ship: either keep it procedural (the .blend/asset library), or apply the modifier / `visual_geometry_to_objects` for exporters.

## Rules
- Randomness: always expose a `Seed`, and use `Random Value` with the ID/Index field so results stay stable when counts change.
- Scale-independent setups use `Object Info` (Relative) and real units. Apply the object scale or read it explicitly.
- Materials: `Set Material` inside the tree. The material must exist in the file, and instances keep their own materials.
- Shading: GN output loses auto-smooth unless you add `Set Shade Smooth` + (5.x) the `Smooth by Angle` essentials group, or store `sharp_edge`.
- UVs: primitives output `UVMap` via their UV output. Store it with `Store Named Attribute` (Face Corner, 2D Vector, name `UVMap`) or it's dropped.
- Performance: avoid realizing millions of instances, prefer Points + instances for scatter, use `Merge by Distance` sparingly, and simulation zones need baking for playback/export (`object.geometry_node_bake_single` or modifier `bakes`).
- Node tools (`ng.is_tool = True`, `is_mode_edit` etc.) turn a group into an operator in the 3D View menus, for editing workflows.

## Gotchas
- 5.2: `mod["Socket_2"]` no longer works. Use `getattr(mod.properties.inputs, ident).value`, and `.type = "ATTRIBUTE"` + `.attribute_name` for attribute inputs. Compare and Random Value **sockets changed**: Random Value now has single dynamic `Min`/`Max`/`Value` sockets typed by `data_type`. Link by name, and `--describe` when unsure.
- Sockets that are disabled for the current mode/data type are still in `node.inputs` with the same name. The builder picks the **enabled** one. Set `data_type`/`mode` props first (the builder sets props before links).
- `nt.interface.new_socket(...)` is the 4.0+ API (`ng.inputs.new` is gone).
- Exporters see the **evaluated** mesh. Instances become glTF instancing (`export_gpu_instances`) or are realized on export.
