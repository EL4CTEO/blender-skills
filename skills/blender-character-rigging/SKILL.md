---
name: blender-character-rigging
description: Character rigging in Blender 5.2 - Rigify metarig fit/generate, bone naming/roll/collections, DEF/MCH/control layers, IK/FK, robust skinning (heat + proxy fallback), weight-painting rules, correctives, engine game skeletons (Unity, Unreal, Roblox R15), rig validation and deformation stress tests. Use for armature, skinning or weights tasks.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Character Rigging

The execution model is in `blender-core`. Faces and shape keys are in `blender-facial-shapekeys`, animation in `blender-animation`.

## Pipeline (scripts chain; each returns JSON)
1. **Prepare the mesh**: scale applied, facing **-Y**, feet at Z=0, centered on X=0, symmetric, in T- or A-pose (A-pose 30–45° deforms shoulders better). Run `blender-asset-qa` first.
2. **Metarig**: `scripts/rigify_build.py -- --add basic_human --fit Body` (`human` adds a full face rig; for games use `--no-face` + shape keys).
3. **Place the joints** (the fit only scales). Edit bones in X-ray against the mesh: joints sit at the **pivot of rotation** (inside the volume, not on the surface). The elbow and knee need a slight bend toward their natural direction (elbow back, knee forward) so the IK solves the right way. Symmetrize: `bpy.ops.armature.symmetrize()`. Check with `look` (`shading="xray"`).
4. **Generate**: `--metarig META_Body --generate` gives `RIG_Body` (control rig: FK/IK, IK/FK snapping, tweak bones, bone collections).
5. **Skin**: `scripts/bind_mesh.py -- --armature RIG_Body --meshes Body`. It uses heat weights, switches to the voxel-proxy transfer automatically when heat fails (non-manifold, kitbashed or AI meshes), then cleans to 4 influences and normalizes.
6. **Stress test**: `scripts/stress_poses.py -- --armature RIG_Body`, then `look(mode="frames", frames=[1,10,20,30,40,50])`. Fix collapsing elbows, candy-wrapped forearms, a sunken shoulder or a hip crease (below).
7. **Engine skeleton**: `rigify_build.py -- --rig RIG_Body --game-skeleton` gives `GAME_RIG_Body` = `root` + DEF bones in a clean hierarchy, with `DEF-` stripped, constrained to the control rig and with the meshes re-targeted. Animate with the control rig, then bake to the game skeleton and export it (`blender-animation` → `blender-export-pipelines`).
8. **Validate**: `scripts/rig_check.py -- --armature GAME_RIG_Body --profile unity|unreal|roblox [--fix]`.

## Bone rules
- **Layers of a production rig**: `DEF` (deforming, the only ones exported), `ORG` (original metarig copy), `MCH` (mechanism helpers), controls (what animators touch). Never weight to control/MCH bones.
- **Naming**: `.L`/`.R` suffixes (mirror tools, Rigify and `rig_check` depend on them). Unique, ASCII. Bone collections (`arm.collections.new("FK")`, `bcoll.assign(bone)`) replace the old bone layers.
- **Roll**: consistent local axes. Y points down the bone; recalc with `armature.calculate_roll(type="GLOBAL_POS_Z")` for limbs, or per chain. Mirrored bones must have mirrored roll (`rig_check` flags this).
- **Chains**: connected parent→child for limbs. Spine 3–5 bones, neck 1–2. Twist bones on the forearm and upper arm (Rigify's `.001` segments) prevent candy-wrapping.
- The root bone sits at the origin, Y-forward, carries no weights, and is used for root motion.
- **Scale**: armature object scale 1, rotation 0. Apply before skinning. Non-uniform bone scale animation breaks engines.

## Weight painting rules (what pros check)
- ≤ 4 influences per vertex (mobile/Roblox), ≤ 8 on PC if the engine supports it. Always normalized. Weights below 0.01 removed.
- **Smooth falloff across joints**: a 50/50 blend at the joint line, fading over ~1–2 edge loops. A hard 1/0 cut shows a crease; too wide gives rubbery limbs.
- **Elbows/knees**: weight the outer side to the upper bone longer so the joint keeps volume. Add a helper/corrective bone or corrective shape for sharp bends.
- **Shoulders**: blend the clavicle, upper arm and spine. Test arms raised above the head (stress frame 10).
- **Hips**: the thigh-pelvis blend in front stays tight (crease) and soft at the back (glutes).
- **Head/neck**: rigid head (100% head bone above the jawline), smooth neck blend. Props (helmets, armor plates) get 100% weight to a single bone, so they stay rigid with no stretching.
- **Mirror**: paint one side, then `object.vertex_group_mirror(all_groups=True, flip_group_names=True, use_topology=False)`, or work with X-mirror on.
- **Tools** (live): Weight Paint mode with auto-normalize on, the gradient tool, Smooth (`vertex_group_smooth`), Levels, and `object.data_transfer` from a good mesh (clothing gets its weights from the body).

## Correctives (beyond weights)
Corrective shape keys driven by bone rotation fix elbows, knees and shoulders in hero rigs. Sculpt the fix in the posed state (`modifier_apply_as_shapekey` or the Corrective Shape Keys add-on approach), then drive the key value from the bone's local rotation (driver `TRANSFORMS` var `ROT_X` in `LOCAL_SPACE`, mapped from 0 at rest to 1 at full bend). Games: correctives export as blendshapes. Drive them in the engine (UE Pose Driver / Unity script) or bake them into the animation.

## Engine skeleton specifics
- **Unity Humanoid**: Hips → Spine → Chest → Neck → Head, plus limbs. The game skeleton maps automatically (`rig_check --profile unity` shows the mapping). T-pose bind pose recommended.
- **Unreal**: retarget to the UE5 Mannequin with IK Retargeter. Matching names (`pelvis`, `spine_01`, `thigh_l`...) speeds up chain mapping (`--profile unreal` lists the gaps). No leaf bones.
- **Roblox R15**: a fixed hierarchy and names (`LowerTorso`, `UpperTorso`, `LeftUpperArm`...), `Root > HumanoidRootNode > LowerTorso`, no weights on Root, ≤ 4 influences. Build it manually or from Roblox's Blender template rather than Rigify. Details are in `blender-export-pipelines/references/roblox.md`.

## Gotchas
- `rigify_generate` needs the metarig **selected and active** (`temp_override` isn't enough). The scripts handle this.
- "Bone Heat Weighting: failed to find solution" comes from non-manifold, intersecting parts or tiny scale. `bind_mesh.py` falls back to proxy. Fix the scale first.
- Meshes parented with "Keep Transform" but with unapplied scale get a double transform. Apply the scale before parenting.
- Modifier order: Armature should come **after** shape-key-like deforms and **before** Subdivision/Corrective Smooth (Corrective Smooth after Armature reduces collapsing).
- 5.0: `bone.select` is gone. Use `pose_bone.select` or `edit_bone.select`. `bone.hide` affects edit bones too.
