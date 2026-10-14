# Godot 4.x and Web (glTF 2.0)

## glTF basics (presets `godot`, `web`, `gltf`)
- `.glb` (binary, embedded textures) for delivery, `.gltf` + bin + images for debugging. Y-up, meters, right-handed. The exporter converts Blender Z-up automatically.
- Supported material: Principled BSDF → `pbrMetallicRoughness` (metallicRoughness texture: **G = roughness, B = metallic**; occlusion R via the "glTF Material Output" group → ORM in one texture), normal (OpenGL), emissive (+ `KHR_materials_emissive_strength`), alpha (OPAQUE/MASK/BLEND).
- Extensions the Blender exporter can write: `KHR_materials_transmission`, `_volume`, `_ior`, `_specular`, `_clearcoat`, `_sheen`, `_iridescence`, `_anisotropy`, `_dispersion`, `_emissive_strength`, `KHR_texture_transform`, `KHR_lights_punctual`, `KHR_mesh_quantization`, `EXT_mesh_gpu_instancing`, `EXT_texture_webp`, `KHR_draco_mesh_compression`, `EXT/KHR_meshopt_compression`.
- Custom properties → glTF `extras` (`export_extras=True`), which Godot exposes as metadata.

## Godot 4 import
- Drop `.glb` (or `.blend`, if the Blender path is set in Godot's settings; it converts via glTF) into the project.
- Name suffixes on objects (Godot import hints): `-col` (mesh + static collision), `-colonly` (collision only, mesh removed), `-convcolonly` (convex), `-rigid` (RigidBody), `-navmesh`, `-noimp` (skip), `-loop`/`-cycle` on animation names (loop). Use them on Blender object names, e.g. `Crate-colonly`.
- Animations: each action → AnimationPlayer clip. Godot retargets humanoids via SkeletonProfileHumanoid (Bone Map in import dock).
- LOD: Godot auto-generates mesh LODs on import (`meshes/generate_lods`). No manual LODs needed.
- Lightmaps: enable "Light Baking: Static Lightmaps" on import to auto-unwrap UV2, or provide one.

## Web (three.js, Babylon.js, model-viewer, R3F)
- Preset `web`: GLB + **meshopt** compression (`EXT_meshopt_compression`, or `KHR_meshopt_compression` via `--set export_meshopt_extension=KHR_meshopt_compression`) + **WebP** textures (q85). `--draco` switches to Draco (smaller for static, slower decode; needs the DRACOLoader).
- Budgets: hero model ≤ 2–5 MB GLB, total scene ≤ 10–20 MB, textures 1–2k, ≤ 50–100 draw calls on mobile web.
- Further compression outside Blender (recommended): `gltf-transform optimize in.glb out.glb --texture-compress ktx2` (KTX2/Basis textures: big GPU memory savings), `gltfpack -cc -tc` (the Blender exporter can call gltfpack: `export_use_gltfpack`).
- three.js: `GLTFLoader` + `MeshoptDecoder`/`DRACOLoader`/`KTX2Loader`. Set `renderer.outputColorSpace = SRGBColorSpace` and tone mapping (`AgX`/`Neutral`) to match Blender's view transform (Khronos PBR Neutral ↔ `NeutralToneMapping`).
- Validate with the Khronos glTF Validator and view in https://gltf-viewer.donmccurdy.com or model-viewer.
