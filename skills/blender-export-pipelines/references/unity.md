# Unity (2022 LTS / Unity 6)

## FBX settings (presets `unity`, `unity_skeletal`)
- Apply Scalings **FBX All**, Forward **-Z**, Up **Y**. Static meshes: **Apply Transform** (`bake_space_transform=True`), which removes the -90° X rotation and the 100 scale on root objects. Never use it with armatures. Skeletal: Apply Transform off, and in Unity enable **Bake Axis Conversion** in the Model importer if the root shows a -90° X rotation.
- Smoothing: Face. Triangulate on (stable tangents). Leaf bones off. Deform bones only.
- Unity importer: Model tab Scale Factor 1, Convert Units on. Normals = Import, Tangents = Import (or Calculate Mikktspace).

## Humanoid (Mecanim) rigs
- Minimum 15 bones: Hips, Spine, Head, Upper/Lower legs, Feet, Upper/Lower arms, Hands. Chest, Neck, Shoulders, Toes, fingers and eyes are optional.
- Bind pose in **T-pose** (Unity can enforce it in Configure Avatar). Hips is the root of the deform hierarchy. An extra `root` bone above Hips is fine for root motion.
- Clean names (`.L/.R` map fine, or Rigify `DEF-*` after export with deform-only). Avoid twist bones parented out of chain; Unity ignores them for retargeting but they still skin.
- Root motion: animate the `root`/Hips; in the clip import settings, set Root Transform Rotation/Position "Based upon" Original/Body Orientation.

## Animation clips
- Export all actions in one FBX (`--set bake_anim_use_all_actions=true`) or one FBX per clip (`Hero@Run.fbx` naming lets Unity share the avatar). Loop: match first/last frames, set Loop Time in Unity.
- Blendshapes export as FBX shape keys (Model tab: Import BlendShapes; Blend Shape Normals: Calculate).

## Materials
- Unity doesn't build PBR materials from FBX usefully. Recreate them in Unity, or use extract + remap.
- URP Lit: BaseMap (sRGB), NormalMap (OpenGL), Metallic map: **R = Metallic, A = Smoothness** (smoothness = 1 − roughness). Occlusion separate.
- HDRP Lit: MaskMap **R = Metallic, G = AO, B = Detail mask, A = Smoothness**.
- Build the packed maps in Blender (`blender-texture-baking` → numpy channel pack) or in Unity with a packing tool.

## Other
- Lightmap UV2: ship one (`uv_pack.py --lightmap`) or tick "Generate Lightmap UVs".
- LOD: name meshes `X_LOD0/1/2`. Unity auto-creates a LOD Group from the suffixes.
- glTF in Unity needs a package (glTFast). FBX remains the default.
