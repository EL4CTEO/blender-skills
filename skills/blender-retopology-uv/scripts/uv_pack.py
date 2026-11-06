"""Unwrap + pack UVs with production defaults; optional seams-from-sharp and lightmap UV2.

Methods: smart (auto seams by angle), seams (use marked seams; --seams-from-sharp marks
hard edges first), min_stretch (SLIM, marked seams), lightmap (non-overlapping UV2 only).
Margins are given in pixels at --res so padding survives mip-mapping.
Usage:
  blender -b f.blend -P uv_pack.py -- [--objects A B] [--method smart|seams|min_stretch]
      [--angle 66] [--seams-from-sharp 60] [--res 2048] [--margin-px 8] [--lightmap]
      [--shape AABB|CONVEX|CONCAVE] [--save out.blend]
  MCP: import uv_pack; result = uv_pack.run(objects=["SM_Crate"], method="seams", seams_from_sharp=60)
"""
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _seams_from_sharp(ob, angle):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = 0
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(angle):
            e.seam = True
            n += 1
        elif len(e.link_faces) == 1:
            e.seam = True
    bm.to_mesh(ob.data)
    bm.free()
    return n


def _collapsed_ratio(ob):
    """Fraction of faces whose UV area is ~0 (failed unwrap)."""
    uv = ob.data.uv_layers.active.data
    bad = 0
    for p in ob.data.polygons:
        pts = [uv[i].uv for i in p.loop_indices]
        a = sum(pts[i].x * pts[i - 1].y - pts[i - 1].x * pts[i].y for i in range(len(pts)))
        bad += abs(a) < 1e-10
    return bad / max(len(ob.data.polygons), 1)


def run(objects=None, method="smart", angle=66.0, seams_from_sharp=None, res=2048, margin_px=8,
        lightmap=False, shape="AABB", **_):
    bx.object_mode()
    obs = bx.objects(objects)
    margin = margin_px / res
    rep = {}
    for ob in obs:
        if seams_from_sharp:
            rep.setdefault(ob.name, {})["seams_marked"] = _seams_from_sharp(ob, seams_from_sharp)
        if not ob.data.uv_layers:
            ob.data.uv_layers.new(name="UVMap")
    bx.select_only(obs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    if method == "smart":
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin,
                                 area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    else:
        bpy.ops.uv.unwrap(method="MINIMUM_STRETCH" if method == "min_stretch" else "ANGLE_BASED",
                          fill_holes=True, correct_aspect=True, margin_method="FRACTION", margin=margin)
        bpy.ops.object.mode_set(mode="OBJECT")
        bad = [ob.name for ob in obs if _collapsed_ratio(ob) > 0.2]  # closed island without seams
        bpy.ops.object.mode_set(mode="EDIT")
        if bad:
            bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin,
                                     area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
            for n in bad:
                rep.setdefault(n, {})["fallback"] = "smart (unwrap collapsed: add seams for control)"
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, rotate_method="ANY", scale=True, shape_method=shape,
                            margin_method="FRACTION", margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    if lightmap:
        for ob in obs:
            uvs = ob.data.uv_layers
            lm = uvs.get("UVMap_Lightmap") or uvs.new(name="UVMap_Lightmap")
            uvs.active = lm
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.lightmap_pack(PREF_CONTEXT="ALL_FACES", PREF_PACK_IN_ONE=False,
                                 PREF_MARGIN_DIV=max(0.05, margin_px / 4))
        bpy.ops.object.mode_set(mode="OBJECT")
        for ob in obs:
            ob.data.uv_layers.active = ob.data.uv_layers[0]  # keep UV0 active for texturing
    for ob in obs:
        rep.setdefault(ob.name, {})["uv_maps"] = [u.name for u in ob.data.uv_layers]
    return {"ok": True, "method": method, "margin_fraction": round(margin, 5), "objects": rep}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--method", default="smart", choices=["smart", "seams", "min_stretch"])
    p.add_argument("--angle", type=float, default=66.0)
    p.add_argument("--seams-from-sharp", type=float, default=None)
    p.add_argument("--res", type=int, default=2048)
    p.add_argument("--margin-px", type=int, default=8)
    p.add_argument("--lightmap", action="store_true")
    p.add_argument("--shape", default="AABB", choices=["AABB", "CONVEX", "CONCAVE"],
                   help="AABB fast; CONCAVE tightest but 2-25s headless even on small meshes")
    bx.cli(run, p)
