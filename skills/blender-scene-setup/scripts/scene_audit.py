"""Audit scene hygiene: units, transforms, naming, collections, materials, images, orphans.

Optional safe fixes: purge orphans, apply rot/scale on single-user meshes, make paths relative.
Usage:
  blender -b f.blend -P scene_audit.py -- [--objects A B] [--fix purge scale paths] [--save out.blend]
  MCP: import scene_audit; result = scene_audit.run(fix=["purge"])
"""
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

DEFAULT_NAME = re.compile(r"^(Cube|Plane|Sphere|Cylinder|Cone|Torus|Suzanne|Circle|Icosphere|"
                          r"Mesh|Empty|Armature|Camera|Light|Material|Object|BezierCurve|Text)"
                          r"(\.\d{3})?$")
EPS = 1e-4


def _apply_rot_scale(ob):
    if ob.type != "MESH" or ob.data.users > 1:
        return False
    loc, rot, sca = ob.matrix_basis.decompose()
    ob.data.transform(Matrix.LocRotScale(None, rot, sca))
    ob.matrix_basis = Matrix.Translation(loc)
    for c in ob.children:  # keep children in place
        c.matrix_parent_inverse = Matrix.LocRotScale(None, rot, sca) @ c.matrix_parent_inverse
    return True


def run(objects=None, fix=None, **_):
    bx.object_mode()
    fix = set(fix or [])
    sc = bpy.context.scene
    us = sc.unit_settings
    obs = bx.objects(objects, types=None)
    issues = {k: [] for k in ("unapplied_scale", "negative_scale", "rotated", "default_names",
                              "duplicate_suffix", "in_scene_root", "no_material",
                              "empty_material_slots", "multi_user_mesh", "origin_far")}
    for ob in obs:
        if ob.type in {"MESH", "CURVE", "ARMATURE", "FONT", "SURFACE"}:
            s = ob.scale
            if any(abs(v - 1) > EPS for v in s):
                issues["unapplied_scale"].append(ob.name)
            if s.x * s.y * s.z < 0:
                issues["negative_scale"].append(ob.name)
            if ob.type == "MESH" and any(abs(v) > EPS for v in ob.rotation_euler):
                issues["rotated"].append(ob.name)
        if DEFAULT_NAME.match(ob.name):
            issues["default_names"].append(ob.name)
        elif re.search(r"\.\d{3}$", ob.name):
            issues["duplicate_suffix"].append(ob.name)
        if ob.name in sc.collection.objects and ob.type not in {"CAMERA", "LIGHT"}:
            issues["in_scene_root"].append(ob.name)
        if ob.type == "MESH":
            if not ob.material_slots:
                issues["no_material"].append(ob.name)
            elif any(s.material is None for s in ob.material_slots):
                issues["empty_material_slots"].append(ob.name)
            if ob.data.users > 1:
                issues["multi_user_mesh"].append(ob.name)
            if ob.data.vertices:
                # origin farther from the bbox centre than 2x the object's size -> pivot problems
                local_c = sum((Vector(c) for c in ob.bound_box), Vector()) / 8
                if local_c.length * max(ob.scale) > 2 * (max(ob.dimensions) or 1):
                    issues["origin_far"].append(ob.name)

    images = {"missing": [], "packed": 0, "absolute_paths": []}
    for im in bpy.data.images:
        if im.source != "FILE":
            continue
        if im.packed_file:
            images["packed"] += 1
            continue
        if not os.path.exists(bpy.path.abspath(im.filepath)):
            images["missing"].append(im.name)
        elif not im.filepath.startswith("//") and bpy.data.filepath:
            images["absolute_paths"].append(im.name)

    orphans = sum(1 for c in ("meshes", "materials", "images", "node_groups", "actions", "textures")
                  for d in getattr(bpy.data, c) if d.users == 0)
    done = []
    if "purge" in fix:
        n = bpy.data.orphans_purge(do_recursive=True)
        done.append(f"purged {n} orphan blocks")
    if "scale" in fix:
        applied = [ob.name for ob in obs if (ob.name in issues["unapplied_scale"] or
                   ob.name in issues["rotated"]) and _apply_rot_scale(ob)]
        bpy.context.view_layer.update()
        done.append(f"applied rot/scale on {len(applied)} meshes")
    if "paths" in fix and bpy.data.filepath:
        bpy.ops.file.make_paths_relative()
        done.append("paths made relative")

    issues = {k: v for k, v in issues.items() if v}
    return {
        "ok": True,
        "units": {"system": us.system, "scale_length": us.scale_length, "length": us.length_unit,
                  "warn": None if (us.system == "METRIC" and abs(us.scale_length - 1) < EPS)
                  else "non-default units: confirm target engine expects this"},
        "objects": len(obs),
        "issues": issues,
        "images": images,
        "orphans": orphans,
        "linked_libraries": [lib.filepath for lib in bpy.data.libraries],
        "fixed": done,
    }


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--fix", nargs="*", choices=["purge", "scale", "paths"], default=[])
    bx.cli(run, p)
