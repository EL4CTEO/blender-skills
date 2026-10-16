---
name: blender-export-pipelines
description: Export from Blender 5.2 with verified presets - Roblox (FBX/glTF, cages, R15, SurfaceAppearance), Unity (FBX, Humanoid), Unreal (FBX skeletal, Nanite, UCX), Godot/web (GLB, meshopt/Draco, WebP), USD. Scale/axes, smoothing, tangents, leaf bones, clips, batch export, post-export verification. Use whenever an asset leaves Blender.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Export Pipelines

The execution model is in `blender-core`. Run `blender-asset-qa` (and `blender-game-optimization` for budgets) **before** exporting.

## One call
```
scripts/export_asset.py -- --preset unreal_skeletal --objects SK_Hero --out //export/SK_Hero.fbx
scripts/export_asset.py -- --preset web --collection Export --out //export/scene.glb
scripts/export_asset.py -- --preset unity --objects SM_A SM_B SM_C --batch --out //export/x.fbx   # one file each, at origin
```
Presets: `roblox`, `roblox_gltf`, `unity`, `unity_skeletal`, `unreal`, `unreal_skeletal`, `godot`, `web`, `gltf`, `usd`. Pass any exporter kwarg with `--set key=value`. Every preset is tested with a round-trip that keeps scale and avoids a 100× armature scale.

## Engine reference (load only the one you need)
- [references/roblox.md](references/roblox.md): MeshParts, avatar bodies (R15), accessories, layered clothing cages, SurfaceAppearance, limits
- [references/unity.md](references/unity.md): FBX settings, Humanoid rigs, URP/HDRP maps, animation clips
- [references/unreal.md](references/unreal.md): static/skeletal FBX, root bone, collision UCX, LODs, Nanite, ORM/DirectX
- [references/godot-web.md](references/godot-web.md): glTF/GLB, import suffixes, three.js/Babylon, compression, KHR extensions

## Universal pre-export checklist
1. **Scale**: scene unit scale 1.0, objects at scale 1, rotation applied (except intentional object transforms). The presets handle unit conversion.
2. **Pivot/origin** where the engine expects it: props at the bottom-center, characters at the world origin between the feet, facing **-Y** (Blender front). Every preset converts that to the engine's forward.
3. **Modifiers**: the presets export the evaluated mesh. Mirror, bevel and weighted normals are kept; booleans become real geometry.
4. **Normals**: custom/weighted normals export. Smooth shading, plus hard edges marked sharp.
5. **Triangulation**: FBX presets triangulate (`use_triangles`) so the bake and engine tangents match. glTF always triangulates.
6. **Materials**: image-texture → Principled chains only, with names `M_*` and textures `T_*`. Procedural nodes don't export, so bake them first.
7. **Armature**: deform bones only, no leaf bones, rest pose = bind pose, 4 weights per vertex max, and the root at the origin.
8. **Animation**: one action per clip, named `Rig_Clip`. Bake constraints/IK to keys (`blender-animation`). FBX exports the active/NLA action per preset settings; glTF `ACTIONS` mode exports every action that has a slot for the armature.
9. **Naming**: unique, ASCII, no spaces. Engines key materials/meshes by name across reimports.

## Format choice
| Need | Format |
|---|---|
| Unity, Unreal (most stable for skeletal) | FBX |
| Godot, web, Roblox (supported), Unreal 5.x Interchange, Blender↔Blender | glTF 2.0 (`.glb`) |
| Film/VFX, Omniverse, Apple AR (`.usdz`), layout interchange | USD |
| Static geometry for printing/CAD | OBJ / STL (`wm.obj_export`, `wm.stl_export`) |
| Point caches / deforming sims | Alembic (`wm.alembic_export`) |

## Verify after export (required)
- The script returns `ok`, the file size, and for `.glb` a parsed summary (meshes, materials, images, animations, skins, tris, extensions). Compare it with what you expected.
- For FBX/USD: re-import into an empty scene (`import_scene.fbx` / `wm.usd_import`) and check `dimensions`, the armature scale (must be 1, not 100) and the action count.
- In the engine: scale against a reference (UE mannequin 180 cm, Unity capsule 2 m, Roblox character 5 studs), normals/smoothing, the normal map's green channel, and animation root motion.

## Collection exporters (re-export in one click, 4.2+)
See `blender-scene-setup`: `collection.exporters` stores the format + settings per collection, and `bpy.ops.wm.collection_export_all()` re-exports everything.

## Gotchas
- FBX `use_tspace` fails silently on n-gons. Triangulate first (the presets do).
- `bake_space_transform` (Apply Transform) is experimental. Use it for Unity static meshes only, never with armatures.
- glTF exports **actions** linked through slots/NLA. An action with no user on the armature is skipped (`export_animation_mode` options: `ACTIONS`, `ACTIVE_ACTIONS`, `NLA_TRACKS`, `SCENE`, `BROADCAST`).
- glTF needs image textures in PNG/JPEG/WebP. EXR/TIFF get converted (`export_image_format`).
- Linked library data exports fine, but make it local or override it if you need to modify it first.
- Shape keys: FBX exports them as blendshapes, glTF as morph targets (`export_morph`). Modifiers before the Armature modifier can block shape-key export in FBX (apply them first).
