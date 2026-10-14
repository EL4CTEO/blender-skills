"""Export objects/collections with engine presets, then verify the file.

Presets: roblox (FBX), roblox_gltf, unity (FBX), unity_skeletal, unreal (FBX), unreal_skeletal,
godot (GLB), web (GLB + meshopt + WebP), gltf (plain GLB), usd (USDZ/USD).
Selection: --objects (children included) or --collection; default = selected/visible meshes+armatures.
--batch exports each top-level object to its own file at the world origin.
Usage:
  blender -b f.blend -P export_asset.py -- --preset unreal --objects SM_Crate --out //export/SM_Crate.fbx
      [--collection Export] [--batch] [--no-anim] [--draco] [--set key=value ...]
  MCP: import export_asset; print(export_asset.run(preset="godot", objects=["Hero"], out="//export/Hero.glb"))
GLB results include a parsed summary (meshes, materials, images, animations, skins, extensions).
"""
import json
import os
import struct
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

FBX_BASE = dict(use_selection=True, object_types={"MESH", "ARMATURE", "EMPTY"}, use_mesh_modifiers=True,
                mesh_smooth_type="FACE", add_leaf_bones=False, use_armature_deform_only=True,
                armature_nodetype="NULL", use_triangles=True, use_tspace=True, use_custom_props=False,
                bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0, path_mode="AUTO")
GLTF_BASE = dict(use_selection=True, export_format="GLB", export_yup=True, export_apply=True,
                 export_texcoords=True, export_normals=True, export_tangents=False,
                 export_materials="EXPORT", export_image_format="AUTO", export_animations=True,
                 export_animation_mode="ACTIONS", export_skins=True, export_morph=True,
                 export_influence_nb=4, export_def_bones=True, export_leaf_bone=False,
                 export_extras=False, export_cameras=False, export_lights=False)

PRESETS = {
    # Roblox: FBX Unit Scale imports at the same scale (Creator Hub); embed textures; no leaf bones
    "roblox": ("fbx", dict(apply_scale_options="FBX_SCALE_UNITS", path_mode="COPY", embed_textures=True,
                           use_tspace=False)),
    "roblox_gltf": ("gltf", dict(export_influence_nb=4)),
    # Unity: FBX All + Apply Transform -> scale 1, no -90 X rotation on import
    "unity": ("fbx", dict(apply_scale_options="FBX_SCALE_ALL", bake_space_transform=True,
                          axis_forward="-Z", axis_up="Y")),
    "unity_skeletal": ("fbx", dict(apply_scale_options="FBX_SCALE_ALL", bake_space_transform=False,
                                   axis_forward="-Z", axis_up="Y")),
    # Unreal: unit scale in the FBX header (no 100x root scale); smoothing groups; deform bones only
    "unreal": ("fbx", dict(apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y")),
    "unreal_skeletal": ("fbx", dict(apply_scale_options="FBX_SCALE_UNITS", axis_forward="-Z", axis_up="Y",
                                    primary_bone_axis="Y", secondary_bone_axis="X")),
    "godot": ("gltf", dict(export_extras=True)),
    "web": ("gltf", dict(export_image_format="WEBP", export_image_quality=85,
                         export_meshopt_compression_enable=True)),
    "gltf": ("gltf", {}),
    "usd": ("usd", dict(selected_objects_only=True, export_materials=True, generate_preview_surface=True,
                        export_armatures=True, only_deform_bones=True, export_shapekeys=True,
                        export_textures_mode="NEW", relative_paths=True, convert_orientation=False)),
}
EXT = {"fbx": ".fbx", "gltf": ".glb", "usd": ".usdz"}


def glb_summary(path):
    """Parse the JSON chunk of a .glb (no import needed)."""
    with open(path, "rb") as f:
        magic, _, _ = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF":
            return {"error": "not a GLB"}
        clen, ctype = struct.unpack("<II", f.read(8))
        doc = json.loads(f.read(clen))
    tris = 0
    for m in doc.get("meshes", []):
        for p in m.get("primitives", []):
            acc = doc["accessors"][p["indices"]] if "indices" in p else None
            tris += (acc["count"] // 3) if acc else 0
    return {k: len(doc.get(k, [])) for k in ("nodes", "meshes", "materials", "images", "animations", "skins")} | {
        "tris": tris, "extensions": doc.get("extensionsUsed", []),
        "animation_names": [a.get("name") for a in doc.get("animations", [])][:20]}


def _gather(objects, collection):
    if collection:
        col = bpy.data.collections[collection]
        return [o for o in col.all_objects if o.type in {"MESH", "ARMATURE", "EMPTY", "CURVE"}]
    obs = bx.objects(objects, types=("MESH", "ARMATURE", "EMPTY"))
    out = []
    for o in obs:
        out.append(o)
        out += [c for c in o.children_recursive if c.type in {"MESH", "ARMATURE", "EMPTY"}]
        if o.parent and o.parent.type == "ARMATURE":
            out.append(o.parent)
    return list(dict.fromkeys(out))


def _export(fmt, path, kw):
    if fmt == "fbx":
        return bpy.ops.export_scene.fbx(filepath=path, **kw)
    if fmt == "gltf":
        return bpy.ops.export_scene.gltf(filepath=path, **kw)
    return bpy.ops.wm.usd_export(filepath=path, **kw)


def _coerce(v):
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(v.lower(), v)


def run(preset="gltf", objects=None, collection=None, out="", batch=False, no_anim=False,
        draco=False, set=None, **_):  # noqa: A002
    bx.object_mode()
    fmt, extra = PRESETS[preset]
    kw = dict(FBX_BASE if fmt == "fbx" else GLTF_BASE if fmt == "gltf" else {})
    kw.update(extra)
    if no_anim:
        kw.update({"bake_anim": False} if fmt == "fbx" else {"export_animations": False} if fmt == "gltf"
                  else {"export_animation": False})
    if draco and fmt == "gltf":
        kw.update(export_draco_mesh_compression_enable=True, export_meshopt_compression_enable=False)
    for item in set or []:
        k, v = item.split("=", 1)
        kw[k] = _coerce(v)
    obs = _gather(objects, collection)
    if not obs:
        raise ValueError("nothing to export")
    warn = [f"{o.name}: unapplied scale {tuple(round(s, 3) for s in o.scale)}" for o in obs
            if o.type == "MESH" and any(abs(s - 1) > 1e-4 for s in o.scale)]
    warn += [f"{o.name}: n-gons present; tangents need tris/quads" for o in obs
             if o.type == "MESH" and fmt == "fbx" and kw.get("use_tspace") and not kw.get("use_triangles")
             and any(len(p.vertices) > 4 for p in o.data.polygons)]
    out = bpy.path.abspath(out) if out else os.path.join(
        os.path.dirname(bpy.data.filepath) or os.getcwd(), "export", f"{obs[0].name}{EXT[fmt]}")
    if fmt == "usd" and not out.endswith((".usd", ".usda", ".usdc", ".usdz")):
        out += ".usdz"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    jobs = []
    if batch:
        roots = [o for o in obs if o.parent is None or o.parent not in obs]
        for r in roots:
            members = [r] + [c for c in r.children_recursive if c in obs]
            jobs.append((os.path.join(os.path.dirname(out), f"{r.name}{EXT[fmt]}"), members, r))
    else:
        jobs.append((out, obs, None))
    files = []
    for path, members, root in jobs:
        bx.select_only(members, active=members[0])
        loc = None
        if root is not None:
            loc = root.location.copy()
            root.location = Vector()
        try:
            res = _export(fmt, path, kw)
        finally:
            if loc is not None:
                root.location = loc
        rec = {"file": path, "ok": res == {"FINISHED"} and os.path.exists(path),
               "kb": round(os.path.getsize(path) / 1024, 1) if os.path.exists(path) else 0,
               "objects": [m.name for m in members]}
        if path.endswith(".glb") and rec["ok"]:
            rec["summary"] = glb_summary(path)
        files.append(rec)
    return {"ok": all(f["ok"] for f in files), "preset": preset, "format": fmt, "files": files,
            "warnings": warn}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__), save=False)
    p.add_argument("--preset", default="gltf", choices=list(PRESETS))
    p.add_argument("--collection", default=None)
    p.add_argument("--out", default="")
    p.add_argument("--batch", action="store_true")
    p.add_argument("--no-anim", action="store_true")
    p.add_argument("--draco", action="store_true")
    p.add_argument("--set", nargs="*", default=None, help="extra exporter kwargs key=value")
    bx.cli(run, p)
