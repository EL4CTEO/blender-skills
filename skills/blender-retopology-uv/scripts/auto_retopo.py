"""Make a low-poly retopo copy of a dense mesh (sculpt/scan/AI-generated) at a triangle budget.

Methods: quadriflow (clean quads; needs manifold input - auto voxel-remesh first),
decimate (fast, keeps UVs/shape; triangles), planar (hard-surface: dissolve flat areas).
The result is shrinkwrapped back onto the source and named <source>_low.
Usage:
  blender -b f.blend -P auto_retopo.py -- --objects Sculpt [--method quadriflow|decimate|planar]
      [--tris 10000] [--voxel 0] [--symmetry] [--save out.blend]
  MCP: import auto_retopo; print(auto_retopo.run(objects=["Sculpt"], tris=8000))
--tris is the triangle budget (quadriflow targets tris/2 quads).
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _ctx(ob):
    return bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                     selected_editable_objects=[ob])


def _apply_all(ob):
    for name in [m.name for m in ob.modifiers]:  # names: applied modifiers are freed
        with _ctx(ob):
            bpy.ops.object.modifier_apply(modifier=name)


def run(objects=None, method="quadriflow", tris=10000, voxel=0.0, symmetry=False, **_):
    bx.object_mode()
    out = {}
    for src in bx.objects(objects):
        low = src.copy()
        low.data = src.data.copy()
        low.name = low.data.name = f"{src.name}_low"
        for c in src.users_collection:
            c.objects.link(low)
        _apply_all(low)
        before = len(low.data.polygons)
        tris_before = bx.mesh_tris(low, evaluated=False)
        faces = max(tris // 2, 4)
        if method == "quadriflow":
            # Quadriflow needs a closed manifold: voxel remesh first (size from target density)
            area = sum(p.area for p in low.data.polygons) * max(low.scale) ** 2
            low.data.remesh_voxel_size = voxel or max(math.sqrt(area / max(faces * 4, 1)), 1e-4)
            with _ctx(low):
                bpy.ops.object.voxel_remesh()
                res = bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=faces,
                                                       use_mesh_symmetry=symmetry,
                                                       use_preserve_sharp=True, seed=0)
            if res != {"FINISHED"}:
                raise RuntimeError("quadriflow failed (non-manifold after voxel remesh?)")
        elif method == "decimate":
            d = low.modifiers.new("Decimate", "DECIMATE")
            d.decimate_type = "COLLAPSE"
            d.ratio = min(1.0, tris / max(tris_before, 1))
            d.use_symmetry = symmetry
            d.use_collapse_triangulate = False
            _apply_all(low)
        elif method == "planar":
            d = low.modifiers.new("Decimate", "DECIMATE")
            d.decimate_type = "DISSOLVE"
            d.angle_limit = math.radians(5)
            d.delimit = {"SEAM", "SHARP", "MATERIAL", "UV"}
            _apply_all(low)
        if method != "planar":
            sw = low.modifiers.new("Shrinkwrap", "SHRINKWRAP")
            sw.target, sw.wrap_method, sw.wrap_mode = src, "PROJECT", "ON_SURFACE"
            sw.use_negative_direction = sw.use_positive_direction = True
            _apply_all(low)
        src.hide_set(True)
        src.hide_render = True
        out[src.name] = {"low": low.name, "faces_before": before, "faces_after": len(low.data.polygons),
                         "tris_after": bx.mesh_tris(low, evaluated=False),
                         "uvs_kept": bool(low.data.uv_layers) and method != "quadriflow"}
    return {"ok": True, "method": method, "objects": out,
            "next": "check edge flow (look wireframe), unwrap (uv_pack.py), bake (blender-texture-baking)"}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--method", default="quadriflow", choices=["quadriflow", "decimate", "planar"])
    p.add_argument("--tris", type=int, default=10000)
    p.add_argument("--voxel", type=float, default=0.0)
    p.add_argument("--symmetry", action="store_true")
    bx.cli(run, p)
