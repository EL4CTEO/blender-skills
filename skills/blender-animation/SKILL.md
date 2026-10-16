---
name: blender-animation
description: Animation in Blender 5.2 - slotted/layered actions and the channelbag API, Python keyframing, F-curves, game loops, NLA clips, pose library, mocap/BVH retargeting via constraints, baking control rigs to export skeletons, root motion, per-clip export. Use for any keyframe, action, NLA, mocap, or animation-export task.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Animation

The execution model is in `blender-core` (its `references/bpy-patterns.md` has verified keyframe/driver snippets). Rigs are in `blender-character-rigging`.

## 5.x data model (what changed)
- An **Action** holds **slots** (one per animated ID) and **layers → strips → channelbags → F-curves**. A single action can animate several objects (e.g. a rig and its camera) through different slots.
- Assign: `ob.animation_data.action = act`, then make sure `ob.animation_data.action_slot` is set (picked automatically when a suitable slot exists; otherwise `act.slots.new(id_type="OBJECT", name=ob.name)`).
- F-curves: `cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)`, then `cb.fcurves.ensure(path, index=i, group_name=...)`. `action.fcurves` **no longer exists**.
- The simplest route is still `pb.keyframe_insert("rotation_quaternion", frame=f)`, which creates the action, slot and channelbag.

## Workflow (keyframe animation, studio style)
1. **Blocking**: key poses on every channel (`CONSTANT` interpolation, `bpy.context.preferences.edit.keyframe_new_interpolation_type`) on golden frames (contact, down, passing, up for walks).
2. **Breakdowns**: add in-betweens that define arcs and spacing.
3. **Spline**: switch to `BEZIER`, fix spacing in the Graph Editor, and clean overshoot. Auto-clamped handles avoid overshoot.
4. **Polish**: offsets/overlap (follow-through on hair, tails, cloth bones), arcs, moving holds (never a perfectly frozen character), and contact stability (feet locked with IK).
5. **Review**: MCP `look(mode="frames", frame_count=8)` or a Workbench playblast (`blender-rendering`).

## Game animation rules
- **One action per clip**, named `<Rig>_<Clip>` or just `<Clip>`, with a fake user so it survives saving.
- **Loops**: first and last frames identical. Export frames 1..N and let the engine drop the duplicate, or exclude the last frame (UE/Unity "loop pose" options). An F-curve `CYCLES` modifier helps preview but **doesn't export**, so bake it.
- **FPS**: author at 30 (or 24) and let engines resample. Set `scene.render.fps` before importing mocap.
- **Root motion**: the root bone carries the translation (and yaw). The hips keep the bob/sway. `scripts/bake_action.py --root-motion xy` moves the hips' ground motion to the root. In-place clips: the root stays at the origin.
- **Additive/overlay** clips (aim offsets, breathing) are exported as normal clips and marked additive in the engine.
- Keep the bone transform channels the engine expects. **Don't animate bone scale** unless the engine supports it (Roblox and many mobile pipelines don't).

## Bake control rig → export skeleton
```
scripts/bake_action.py -- --list
scripts/bake_action.py -- --source RIG_Body --target GAME_RIG_Body [--actions Walk Run] [--root-motion xy --hips spine]
```
This gives one baked action per clip (`GAME_RIG_Body|Walk`), cleaned, with fake users, plus one muted NLA track per clip (`CLIP_Walk`) so FBX (`bake_anim_use_nla_strips`/all actions) and glTF (`ACTIONS` mode) export every clip. The target's constraints are muted afterward so it plays the baked data; run `--follow` to drive it live again. Self-bake (IK/constraints → keys on the same rig): `--source X --target X`.

## Mocap and retargeting
- Import: `bpy.ops.import_anim.bvh(filepath=..., global_scale=0.01 if cm else 1, rotate_mode="NATIVE", update_scene_fps=True)`, `import_scene.fbx` (Mixamo, `automatic_bone_orientation=True`).
- Retarget without add-ons: put the target rig in the **same rest pose** (T vs A matters most), add `COPY_ROTATION` constraints (world or local-with-parent space) from each target bone to the matching source bone, plus `COPY_LOCATION` on the hips/root (scaled by the leg-length ratio). Then self-bake with `bake_action.py --source TARGET --target TARGET`, and delete the constraints.
- Clean mocap: decimate keys (`graph.decimate`, ratio 0.3–0.5), use an F-curve `SMOOTH` modifier or the Butterworth filter (`graph.butterworth_smooth`), and fix foot sliding with IK pins and then bake.
- Production retarget tools: Auto-Rig Pro (paid), Rokoko (free), and the engine-side retargeters (UE IK Retargeter, Unity Humanoid).

## NLA and pose library
- NLA: push actions down as strips (`track.strips.new(name, start, action)`) to layer/blend clips (blend type `REPLACE`/`ADD`/`COMBINE`), and use Tweak mode to edit. Strips need an action slot set when the action has several slots (`strip.action_slot`).
- The pose library (bundled `pose_library`) stores poses as **assets**: `poselib.create_pose_asset(pose_name=...)`, `poselib.apply_pose_asset` / `blend_pose_asset`. Use it for hand shapes, face poses, and a T/A rest pose.

## Shape keys and other properties
Any property can be keyed: `kb.keyframe_insert("value", frame=f)` (shape key), `mat.node_tree.nodes[...].inputs[...].keyframe_insert("default_value")` (materials, which engines usually ignore), custom props `ob.keyframe_insert('["prop"]')`.

## Gotchas
- `pb.matrix = ...` followed by `keyframe_insert` needs the right `scene.frame_set(f)` **first**, or an evaluation overwrites the pose.
- Connected bones (`use_connect`) can't translate. Hips/pelvis must be unconnected from the root.
- `bake_action` with visual keying reads **evaluated** poses, so constraints, IK and drivers are all captured. Mute the target's own constraints afterward (the script does), or they keep overriding the keys.
- Quaternion vs Euler: game bones should use `QUATERNION` (no gimbal lock, smooth slerp). Euler is fine for single-axis controls. Don't mix modes between keys.
- glTF sampling: `export_force_sampling` bakes every frame (the safe default). Non-linear F-curve modifiers and drivers only export when sampled.
