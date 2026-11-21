"""Skin meshes to an armature with robust automatic weights, then clean them for engines.

Methods: auto (bone heat), proxy (voxel-remeshed manifold proxy gets heat weights, transferred
back - use for non-manifold/AI/kitbashed meshes or when heat fails), envelope, empty (groups only).
auto falls back to proxy when heat weighting leaves verts unweighted.
Cleanup: remove weights < --clean, limit to --limit influences, normalize.
Usage:
  blender -b f.blend -P bind_mesh.py -- --armature RIG --meshes Body Head [--method auto|proxy|envelope|empty]
      [--limit 4] [--clean 0.01] [--save out.blend]
  MCP: import bind_mesh; print(bind_mesh.run(armature="rig", meshes=["Body"]))
"""
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _ctx(ob):
    return bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                     selected_editable_objects=[ob])


def unweighted(me_ob, arm):
    deform = {b.name for b in arm.data.bones if b.use_deform}
    gi = {g.index for g in me_ob.vertex_groups if g.name in deform}
    return sum(1 for v in me_ob.data.vertices if not any(g.group in gi and g.weight > 1e-4 for g in v.groups))


def _parent(meshes, arm, kind):
    bx.select_only(meshes + [arm], active=arm)
    return bpy.ops.object.parent_set(type=kind, keep_transform=True)


def _proxy_weights(ob, arm):
    proxy = ob.copy()
    proxy.data = ob.data.copy()
    proxy.modifiers.clear()
    proxy.vertex_groups.clear()
    proxy.parent = None
    proxy.matrix_world = ob.matrix_world
    bpy.context.scene.collection.objects.link(proxy)
    bpy.context.view_layer.update()
    proxy.data.remesh_voxel_size = max(ob.dimensions) / 150
    with _ctx(proxy):
        bpy.ops.object.voxel_remesh()
    _parent([proxy], arm, "ARMATURE_AUTO")
    ob.vertex_groups.clear()
    dt = ob.modifiers.new("WeightTransfer", "DATA_TRANSFER")
    dt.object = proxy
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    with _ctx(ob):
        bpy.ops.object.datalayout_transfer(modifier=dt.name)
        bpy.ops.object.modifier_move_to_index(modifier=dt.name, index=0)
        bpy.ops.object.modifier_apply(modifier=dt.name)
    bpy.data.objects.remove(proxy)


def _height(obs):
    zs = [(ob.matrix_world @ Vector(c)).z for ob in obs for c in ob.bound_box]
    return (max(zs) - min(zs)) if zs else 0.0


def _heat_scale(obs, arm):
    """Factor that brings the rig to ~1.8 m for bone heat; 1.0 when already 0.5-20 m tall."""
    h = _height(obs)
    if h <= 1e-9 or 0.5 <= h <= 20:
        return 1.0
    return 1.8 / h


def cleanup(ob, limit=4, clean=0.01):
    if not ob.vertex_groups:
        return
    with _ctx(ob):
        bpy.ops.object.vertex_group_clean(group_select_mode="ALL", limit=clean, keep_single=True)
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=limit)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)


def run(armature=None, meshes=None, method="auto", limit=4, clean=0.01, **_):
    bx.object_mode()
    arm = bpy.data.objects[armature]
    obs = bx.objects(meshes)
    for ob in obs:  # clean slate: remove previous armature mods / parent
        for m in [m for m in ob.modifiers if m.type == "ARMATURE"]:
            ob.modifiers.remove(m)
    report = {}
    # Bone heat silently fails at small world sizes (FBX/Mixamo rigs at 0.01 scale: every vertex lands
    # 100% on the root). Bind at human size, then put the armature back (meshes follow as children).
    k = _heat_scale(obs, arm) if method in ("auto", "proxy") else 1.0
    arm_mw = arm.matrix_world.copy()
    if k != 1.0:
        S = Matrix.Scale(k, 4)
        mws = [o.matrix_world.copy() for o in obs]
        arm.matrix_world = S @ arm_mw  # parent first, then absolute world matrices (meshes may be children)
        bpy.context.view_layer.update()
        for o, mw in zip(obs, mws):
            o.matrix_world = S @ mw
        bpy.context.view_layer.update()
    if method in ("auto", "envelope", "empty"):
        kind = {"auto": "ARMATURE_AUTO", "envelope": "ARMATURE_ENVELOPE", "empty": "ARMATURE_NAME"}[method]
        _parent(obs, arm, kind)
    for ob in obs:
        used = method
        if method == "proxy" or (method == "auto" and unweighted(ob, arm) > 0.02 * len(ob.data.vertices)):
            used = "proxy"
            _proxy_weights(ob, arm)
            if not any(m.type == "ARMATURE" for m in ob.modifiers):
                _parent([ob], arm, "ARMATURE_NAME")
        if method != "empty":
            cleanup(ob, limit, clean)
        mx = max((sum(1 for g in v.groups if g.weight > 1e-4) for v in ob.data.vertices), default=0)
        report[ob.name] = {"method": used, "groups": len(ob.vertex_groups),
                           "unweighted_verts": unweighted(ob, arm), "max_influences": mx}
    if k != 1.0:
        arm.matrix_world = arm_mw
        bpy.context.view_layer.update()
    bx.select_only([arm])
    out = {"ok": True, "armature": arm.name, "meshes": report}
    if k != 1.0:
        out["note"] = f"bound at {k:g}x world scale (rig is {_height(obs):.3g} m tall; heat weights need ~human size)"
    return out


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--armature", required=True)
    p.add_argument("--meshes", nargs="*", default=None)
    p.add_argument("--method", default="auto", choices=["auto", "proxy", "envelope", "empty"])
    p.add_argument("--limit", type=int, default=4)
    p.add_argument("--clean", type=float, default=0.01)
    p.add_argument("--save", default=None)
    bx.cli(run, p)
