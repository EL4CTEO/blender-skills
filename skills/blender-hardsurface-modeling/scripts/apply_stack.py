"""Build (and optionally apply) a production hard-surface modifier stack.

Presets:
  midpoly : booleans -> Bevel(angle, harden normals) -> Weighted Normal(keep sharp)  [games]
  subd    : booleans -> Bevel(1 seg, support edge) -> Subdivision(2) + Smooth by Angle  [renders]
  render  : booleans -> Bevel(4 seg, arc miter) -> Weighted Normal                      [renders]
Bevel width defaults to 1% of the object's largest dimension (override with --width, metres).
Usage:
  blender -b f.blend -P apply_stack.py -- --objects Body [--preset midpoly] [--width 0.01]
      [--segments 3] [--angle 30] [--cutters CutA CutB] [--solver EXACT|MANIFOLD|FLOAT]
      [--triangulate] [--apply] [--save out.blend]
  MCP: import apply_stack; result = apply_stack.run(objects=["Body"], cutters=["Hole"])
"""
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PREFIX = "HS_"  # our modifiers; re-running replaces them


def _smooth_faces(me):
    a = me.attributes.get("sharp_face")
    if a:
        me.attributes.remove(a)


def run(objects=None, preset="midpoly", width=None, segments=None, angle=30.0, cutters=None,
        solver="EXACT", operation="DIFFERENCE", triangulate=False, apply=False, **_):
    bx.object_mode()
    obs = bx.objects(objects)
    cut_obs = [bpy.data.objects[n] for n in cutters or []]
    for c in cut_obs:
        c.display_type = "WIRE"
        c.hide_render = True
        c.visible_shadow = False
    report = {}
    for ob in obs:
        if ob in cut_obs:
            continue
        for m in [m for m in ob.modifiers if m.name.startswith(PREFIX)]:
            ob.modifiers.remove(m)
        _smooth_faces(ob.data)  # harden normals / weighted normals need smooth shading
        w = width or max(ob.dimensions) * 0.01 / max(max(ob.scale), 1e-6)
        for c in cut_obs:
            b = ob.modifiers.new(f"{PREFIX}Bool_{c.name}", "BOOLEAN")
            b.object, b.operation = c, operation
            bx.set_enum(b, "solver", solver)
        bev = ob.modifiers.new(f"{PREFIX}Bevel", "BEVEL")
        bev.width = w
        bev.limit_method = "ANGLE"
        bev.angle_limit = math.radians(angle)
        bev.use_clamp_overlap = True
        bev.miter_outer = "MITER_ARC"
        if preset == "subd":
            bev.segments = segments or 1
            sub = ob.modifiers.new(f"{PREFIX}Subd", "SUBSURF")
            sub.levels, sub.render_levels = 2, 2
            with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                           selected_editable_objects=[ob]):
                bpy.ops.object.shade_auto_smooth(angle=math.radians(angle))
            sba = ob.modifiers[-1]
            sba.name = f"{PREFIX}SmoothByAngle"
        else:
            bev.segments = segments or (3 if preset == "midpoly" else 4)
            bev.profile = 0.5
            bev.harden_normals = True
            wn = ob.modifiers.new(f"{PREFIX}WeightedNormal", "WEIGHTED_NORMAL")
            wn.mode, wn.weight, wn.keep_sharp = "FACE_AREA", 50, True
        if triangulate:
            t = ob.modifiers.new(f"{PREFIX}Triangulate", "TRIANGULATE")
            t.keep_custom_normals = True
            t.quad_method, t.ngon_method = "BEAUTY", "BEAUTY"
        before = bx.mesh_tris(ob, evaluated=False)
        after = bx.mesh_tris(ob)
        applied = []
        if apply:
            # names first: a modifier struct is freed once applied (reading it after = garbage/crash)
            for name in [m.name for m in ob.modifiers if m.name.startswith(PREFIX)]:
                with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                               selected_editable_objects=[ob]):
                    res = bpy.ops.object.modifier_apply(modifier=name)
                applied.append(name if res == {"FINISHED"} else f"FAILED:{name}")
        report[ob.name] = {"bevel_width": round(w, 5), "tris_base": before, "tris_final": after,
                           "stack": [m.name for m in ob.modifiers], "applied": applied}
    return {"ok": True, "preset": preset, "objects": report}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--preset", default="midpoly", choices=["midpoly", "subd", "render"])
    p.add_argument("--width", type=float, default=None)
    p.add_argument("--segments", type=int, default=None)
    p.add_argument("--angle", type=float, default=30.0)
    p.add_argument("--cutters", nargs="*", default=None)
    p.add_argument("--solver", default="EXACT", choices=["EXACT", "MANIFOLD", "FLOAT"])
    p.add_argument("--operation", default="DIFFERENCE", choices=["DIFFERENCE", "UNION", "INTERSECT"])
    p.add_argument("--triangulate", action="store_true")
    p.add_argument("--apply", action="store_true")
    bx.cli(run, p)
