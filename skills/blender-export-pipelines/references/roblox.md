# Roblox (Creator Hub specs, verified 2026-10)

## Units and export
- 1 stud ≈ 0.28 m. Default R15 character ≈ 5 studs tall.
- Blender FBX: **Apply Scalings = FBX Unit Scale**, every other scale 1.0, Path Mode **Copy** + **Embed Textures**, **Add Leaf Bones off**, Bake Animation **off** unless exporting a clip. That's preset `roblox`.
- Alternatives from the docs: Transform Scale 0.01, or scene Unit Scale 0.01 (the docs warn this causes Blender issues).
- glTF (`.gltf/.glb`) is supported and needs no scale tricks: preset `roblox_gltf`.
- The Roblox docs recommend Unit System None + Rotation Degrees in Blender to "match studs". Optional; keep Metric if you rely on the presets.
- **One animation per exported file.** Export each clip separately.

## Mesh rules (all MeshParts)
- ≤ **20,000 triangles per mesh**. Watertight, no holes/backfaces, no zero thickness, quads preferred, no n-gons.
- **One UV set**, all UVs inside 0–1 (overlaps allowed).
- Use `blender-asset-qa --profile roblox`.
- `RenderFidelity=Automatic` creates LODs, so don't ship LOD meshes. Set `CollisionFidelity` (Box/Hull/Default/PreciseConvexDecomposition) on simple parts.

## Textures / SurfaceAppearance
- Maps: `ColorMap` (RGB + alpha), `NormalMap` (**OpenGL, tangent space**, flat = 127,127,255), `MetalnessMap` (8-bit gray), `RoughnessMap` (8-bit gray), `EmissiveMaskContent` (8-bit gray) + `EmissiveTint`/`EmissiveStrength`. No packed ORM, so export separate grayscale maps.
- Max 4096²; PBR maps are commonly limited to 1024². Size guidance: 5×5 studs → 256², 10×10 → 512², 20×20 → 1024². Marketplace max 2048².
- `AlphaMode`: Overlay (default; alpha shows the part color), Transparency (cutout/blend), TintMask (alpha = where `Color` tints), Opaque.
- Files: PNG/JPG/TGA/BMP. Upload via Studio (`AssetService:CreateAssetAsync` for batch).

## Rigging (any skinned mesh)
- Freeze bones: scale 1, rotation 0. Root bone at 0,0,0. ≤ **4 influences per vertex**, **no weights on Root**, symmetric weights.
- `blender-character-rigging` → `rig_check.py --profile roblox`.

## Avatar character bodies (R15)
- 15 meshes named `<Part>_Geo`: Head, UpperTorso, LowerTorso, Left/Right UpperArm, LowerArm, Hand, UpperLeg, LowerLeg, Foot. Each is watertight and capped at the joints.
- Facing **+Z, up +Y** in Roblox space (Blender preset conversion: front = -Y in Blender). Pose: I/A/T. Pivots at 0,0,0.
- Tri budgets: DynamicHead 4,000, Torso 1,750, each Arm/Leg 1,248, total **10,742**.
- Body scale (studs, X/Y/Z): min 1.35/3.6/0.7. Max Normal 8.6/9.5/2.25, Slender 6/9.5/2, Classic 8/9.1/2.
- Skeleton: `Root > HumanoidRootNode > LowerTorso > UpperTorso > (Head, arms)`, legs from LowerTorso. Root and LowerTorso at the origin. Up to 37 optional bones (Spine, Chest, Clavicles, fingers...) need `HumanoidRigDescription`.
- Attachments (empties) with `_Att` suffix: FaceCenter, FaceFront, Hat, Hair (head); Left/RightCollar, Neck, BodyBack, BodyFront (UpperTorso); Root (0,0,0), WaistFront/Back/Center (LowerTorso); Left/RightShoulder, Left/RightGrip; Left/RightFoot.
- Each body part needs an **outer cage** `<Part>_OuterCage`. Don't delete cage verts or change cage UVs.
- Marketplace: opaque body parts, ≥50% bounding-box fill, Material Plastic, VertexColor 1,1,1. Skin-tone areas transparent in the ColorMap.
- Dynamic heads: FACS poses as animation/shape data (see the Creator Hub "dynamic heads" page). Map ARKit-style shapes with `blender-facial-shapekeys`.

## Accessories and layered clothing
- Rigid accessories: ~4,000 tris max. Layered clothing: 4,000 tris max. Texture ≤ 1024² recommended.
- Layered clothing needs `<Name>_InnerCage` + `<Name>_OuterCage`, built from the Roblox template cages (same vert count/order/UVs as the template). The inner cage hugs the body, the outer cage hugs the clothing surface.
- Skin the clothing to the R15 rig (same bone names). Cages stay unskinned or follow the rig per template.
- Validate in Studio with the Accessory Fitting Tool.
