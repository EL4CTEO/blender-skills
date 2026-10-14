# Unreal Engine 5.x

## FBX settings (presets `unreal`, `unreal_skeletal`)
- Scene unit scale 1.0 (meters). Apply Scalings **FBX Units Scale**: the unit goes into the FBX header, so UE converts to cm **without** a 100× scale on the armature/root bone. A root bone that imports with scale 100 means the wrong apply-scale mode was used.
- Forward -Z / Up Y (UE converts the axis system). Smoothing **Face** (avoids the "no smoothing groups" warning). Triangulate on. Tangents on.
- Skeletal: **Add Leaf Bones off**, **Only Deform Bones on**, armature node type Null. If the armature object is named `Armature`, UE drops it and the first bone becomes the root. Otherwise the object becomes an extra root bone, so name the object `root` if you want that explicitly.
- UE 5.4+ also imports glTF/USD through Interchange. FBX remains the most battle-tested path for skeletal meshes.

## Skeleton conventions
- Mannequin (UE5 Manny/Quinn) hierarchy: `root > pelvis > spine_01..05 > neck_01..02 > head`, `clavicle_l/r > upperarm > lowerarm > hand`, `thigh > calf > foot > ball`, plus twist/IK bones. Matching the names and bone orientation lets the IK Retargeter auto-map them.
- The UE Mannequin's skeletal mesh faces **+Y** in its asset space (the Character Blueprint rotates the mesh -90° to face +X). After the first import, compare your mesh with the Mannequin in the Skeletal Mesh editor. If they differ, rotate the armature ±90° around Z in Blender, apply, and re-export, so retargeting and root motion line up.
- Bone orientation: Blender bones are Y-along. If you need UE-style X-along bones for engine-side tools, set `primary_bone_axis="X"`, `secondary_bone_axis="-Y"` with `--set`.

## Static meshes
- Collision: `UCX_<MeshName>_00` (convex, ≤ 255 verts, not overlapping), `UBX_` boxes, `USP_` spheres, `UCP_` capsules, exported in the same FBX as the mesh.
- LODs: `<Mesh>_LOD0..N` in one FBX, with "Import Mesh LODs" enabled, or let UE auto-generate them.
- Lightmap UV: UE can generate one (Generate Lightmap UVs). Ship UV2 only for hand-made lightmaps.
- Sockets: empties named `SOCKET_<Name>` parented to the mesh.

## Nanite (static, UE 5.0+; skinned meshes experimental in 5.5+)
- Ship dense geometry directly (millions of tris). No LODs, no normal-map bake needed for geometric detail. Keep UV seams sensible (Nanite's error metric respects them).
- Opaque and masked materials are supported. Translucency isn't. Small/thin meshes (foliage) need care (Preserve Area option).
- Enable on import ("Build Nanite") or per asset.

## Materials and textures
- BaseColor (sRGB), Normal (**DirectX**: bake with `--directx`, or tick "Flip Green Channel" on the texture), **ORM** (R=AO, G=Roughness, B=Metallic; uncheck sRGB, compression Masks).
- Name textures `T_<Asset>_BC/_N/_ORM`. Materials become `M_` and instances `MI_`.

## Animation
- One action per clip. FBX exports the active action, NLA strips, or all actions (`bake_anim_use_all_actions`). Import the animation FBX against the existing Skeleton asset.
- Root motion: animate the `root` bone (not the armature object). Enable Root Motion on the anim sequence.
- Morph targets come from shape keys. Enable "Import Morph Targets".
