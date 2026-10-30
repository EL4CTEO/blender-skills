"""Check that a cycle loops: the pose at the last frame equals the first (no pop), and the motion
across the seam keeps its speed (no hitch). --fix keys every F-curve's first-frame value onto the
last frame. Root-motion clips: --root-motion BONE ignores that bone's X/Y travel.

Compares evaluated poses (constraints, drivers included) per bone in armature space; works on
plain objects too (object transform). Engines drop the duplicate last frame on import ("loop pose").
Usage:
  blender -b f.blend -P loop_check.py -- --object GAME_RIG [--action Walk] [--frames 1 25]
      [--tol-deg 0.5] [--tol-m 0.001] [--root-motion root] [--fix] [--save out.blend]
  MCP: import loop_check; print(loop_check.run(object="GAME_RIG", action="Walk", fix=True))
"""
import math
import os
import sys

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _poses(ob, f, root=None):
    bpy.context.scene.frame_set(f)
    if ob.type != "ARMATURE":
        return {"<object>": ob.matrix_world.copy()}
    pose = {pb.name: pb.matrix.copy() for pb in ob.pose.bones}
    if root in pose:  # remove the root's ground travel from it and its children (they inherit it)
        t = pose[root].translation.copy()
        t.z = 0.0
        off = Matrix.Translation(-t)
        moved = {root, *(c.name for c in ob.pose.bones[root].children_recursive)}
        pose = {k: (off @ m if k in moved else m) for k, m in pose.items()}
    return pose


def _diff(a, b):
    rot = math.degrees(a.to_quaternion().rotation_difference(b.to_quaternion()).angle)
    return min(rot, 360.0 - rot), (a.translation - b.translation).length


def _check(ob, f0, f1, tol_deg, tol_m, root):
    p0, p1 = _poses(ob, f0, root), _poses(ob, f1, root)
    n0, n1 = _poses(ob, f0 + 1, root), _poses(ob, f1 - 1, root)
    pops, hitch = [], []
    for k in p0:
        r, t = _diff(p0[k], p1[k])
        if r > tol_deg or t > tol_m:
            pops.append({"bone": k, "rot_deg": round(r, 3), "loc_m": round(t, 5)})
        v_in, v_out = _diff(p1[k], n1[k])[0], _diff(n0[k], p0[k])[0]  # deg/frame arriving vs leaving
        dv = abs(v_in - v_out)
        if dv > tol_deg and dv > 0.25 * max(v_in, v_out):
            hitch.append({"bone": k, "deg_per_frame_in": round(v_in, 3), "deg_per_frame_out": round(v_out, 3)})
    pops.sort(key=lambda x: -x["rot_deg"] - 100 * x["loc_m"])
    hitch.sort(key=lambda x: -abs(x["deg_per_frame_in"] - x["deg_per_frame_out"]))
    return pops, hitch


def run(object=None, action=None, frames=None, tol_deg=0.5, tol_m=0.001, root_motion=None, fix=False, **_):
    if not object:
        raise ValueError("--object is required")
    ob = bpy.data.objects[object]
    ad = ob.animation_data
    if action:
        ob.animation_data_create()
        ob.animation_data.action = bpy.data.actions[action]
        ad = ob.animation_data
        if ad.action_slot is None:
            ad.action_slot = next(iter(ad.action_suitable_slots), None)
    if ad is None or ad.action is None:
        raise ValueError(f"{object} has no action")
    act = ad.action
    f0, f1 = (int(frames[0]), int(frames[1])) if frames else (int(round(v)) for v in act.frame_range)
    pops, hitch = _check(ob, f0, f1, tol_deg, tol_m, root_motion)
    res = {"ok": True, "object": ob.name, "action": act.name, "frames": [f0, f1], "loops": not pops,
           "pops": pops[:10], "hitches": hitch[:10]}
    if fix and pops:
        cb = anim_utils.action_get_channelbag_for_slot(act, ad.action_slot)
        ground = set()
        if root_motion and ob.type == "ARMATURE":  # local location axes that point along the ground
            ml = ob.data.bones[root_motion].matrix_local.to_3x3()
            ground = {i for i in range(3) if abs(ml.col[i].normalized().z) < 0.5}
        n = 0
        for fc in cb.fcurves:
            if fc.data_path == f'pose.bones["{root_motion}"].location' and fc.array_index in ground:
                continue  # root travel is the point of a root-motion clip
            fc.keyframe_points.insert(f1, fc.evaluate(f0), options={"REPLACE", "FAST"})
            fc.update()
            n += 1
        pops2, hitch2 = _check(ob, f0, f1, tol_deg, tol_m, root_motion)
        res.update(fixed_curves=n, loops=not pops2, pops=pops2[:10], hitches=hitch2[:10])
    if res["hitches"]:
        res["note"] = "speed changes across the seam: match the tangents (Graph Editor, auto-clamped/cyclic) or re-pose frame 2/N-1"
    bpy.context.scene.frame_set(f0)
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--object", required=True)
    p.add_argument("--action", default=None)
    p.add_argument("--frames", type=int, nargs=2, default=None)
    p.add_argument("--tol-deg", type=float, default=0.5)
    p.add_argument("--tol-m", type=float, default=0.001)
    p.add_argument("--root-motion", default=None, help="bone whose X/Y travel is ignored")
    p.add_argument("--fix", action="store_true")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
