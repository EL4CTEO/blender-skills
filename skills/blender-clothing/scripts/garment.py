"""Game clothing from a body: extract a region as a garment shell (ease offset + thickness), copy the
body's skin weights so it deforms with the rig, mask the body faces it hides, optionally drape it with
a cloth sim for folds, copy body shape keys as matching garment keys (--morphs), and measure body poke-through in the current pose.

Region: a body vertex group (--group) or a world Z band (--zmin/--zmax). Weights: Data Transfer
(nearest face, interpolated) from the body, limited to --max-influences and normalized, plus the
body's Armature modifier. --hide-body adds a Mask modifier that hides covered body faces (delete them
on export for games). --check measures penetration: body verts in front of the garment's inner
surface, evaluated in the current pose (pose the rig, then check).
Usage:
  blender -b f.blend -P garment.py -- --body Body (--group Torso | --zmin 1.0 --zmax 1.5) [--name Shirt]
      [--offset 0.008] [--thickness 0.003] [--subdiv 0] [--max-influences 4] [--hide-body]
      [--drape 0] [--morphs] [--save out.blend]
  blender -b f.blend -P garment.py -- --check Shirt --body Body
  MCP: import garment; print(garment.run(body="Body", zmin=1.0, zmax=1.5, name="Shirt", hide_body=True))
"""
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _region(body, group, zmin, zmax):
    me = body.data
    if group:
        if group not in body.vertex_groups:
            raise KeyError(f"vertex group {group!r} not on {body.name}")
        gi = body.vertex_groups[group].index
        return {v.index for v in me.vertices if any(g.group == gi and g.weight > 0.5 for g in v.groups)}
    if zmin is None or zmax is None:
        raise ValueError("give --group or both --zmin and --zmax")
    mw = body.matrix_world
    return {v.index for v in me.vertices if zmin <= (mw @ v.co).z <= zmax}


def _shell(body, verts, name, offset):
    """Copy the region's faces in world space and push them out along the vertex normals."""
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.transform(body.matrix_world)
    bm.normal_update()
    drop = [f for f in bm.faces if not all(v.index in verts for v in f.verts)]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    for v in bm.verts:
        v.co += v.normal * offset
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
    else:
        ob.data = me
    ob.matrix_world.identity()
    return ob


def _transfer_weights(garment, body, max_inf):
    for vg in body.vertex_groups:
        if vg.name not in garment.vertex_groups:
            garment.vertex_groups.new(name=vg.name)
    dt = garment.modifiers.new("Weights", "DATA_TRANSFER")
    dt.object, dt.use_object_transform = body, True
    dt.use_vert_data, dt.data_types_verts = True, {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src, dt.layers_vgroup_select_dst = "ALL", "NAME"
    bx.select_only([garment])
    with bpy.context.temp_override(object=garment, active_object=garment):
        bpy.ops.object.modifier_move_to_index(modifier=dt.name, index=0)
        bpy.ops.object.modifier_apply(modifier=dt.name)
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=max_inf)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)
        bpy.ops.object.vertex_group_clean(group_select_mode="ALL", limit=0.001)


def _hide_body(body, verts, name, inset=1):
    """Vertex group of body verts strictly inside the covered region (shrunk `inset` rings) + Mask."""
    me = body.data
    keep = set(verts)
    for _ in range(inset):  # don't hide the border ring: avoids gaps at cuffs/collars
        border = {v for e in me.edges for v in e.vertices if (e.vertices[0] in keep) != (e.vertices[1] in keep)}
        keep -= border
    gname = f"Hidden_{name}"
    vg = body.vertex_groups.get(gname) or body.vertex_groups.new(name=gname)
    vg.remove(range(len(me.vertices)))
    vg.add(sorted(keep), 1.0, "REPLACE")
    md = body.modifiers.get(gname) or body.modifiers.new(gname, "MASK")
    md.vertex_group, md.invert_vertex_group = gname, True
    return gname, len(keep)


def _drape(garment, body, frames, pin_frac=0.08):
    """Classic cloth: pin the top band, collide with the body, settle `frames`, apply the result."""
    me = garment.data
    zs = np.array([(garment.matrix_world @ v.co).z for v in me.vertices])
    top = zs.max() - (zs.max() - zs.min()) * pin_frac
    pin = garment.vertex_groups.get("Pin") or garment.vertex_groups.new(name="Pin")
    pin.add([i for i, z in enumerate(zs) if z >= top], 1.0, "REPLACE")
    cl = garment.modifiers.new("Drape", "CLOTH")
    s = cl.settings
    s.quality, s.mass, s.tension_stiffness, s.bending_stiffness = 8, 0.15, 15.0, 0.5  # cotton-ish
    s.vertex_group_mass = "Pin"
    cl.collision_settings.distance_min = 0.003
    cl.collision_settings.use_self_collision = False
    added = body.collision is None or not any(m.type == "COLLISION" for m in body.modifiers)
    if added:
        body.modifiers.new("Collision", "COLLISION")
    body.collision.thickness_outer = 0.003
    sc = bpy.context.scene
    cl.point_cache.frame_start, cl.point_cache.frame_end = sc.frame_current, sc.frame_current + frames
    f0 = sc.frame_current
    for f in range(f0, f0 + frames + 1):
        sc.frame_set(f)
    bx.select_only([garment])
    with bpy.context.temp_override(object=garment, active_object=garment):
        bpy.ops.object.modifier_apply(modifier=cl.name)
    sc.frame_set(f0)
    if added:
        body.modifiers.remove(body.modifiers["Collision"])
    if "Pin" in garment.vertex_groups:  # re-fetch: modifier_apply invalidates the old reference
        garment.vertex_groups.remove(garment.vertex_groups["Pin"])


def transfer_morphs(garment, body):
    """Same-named garment shape key for every body shape key (Surface Deform bound at rest, applied as
    shape key per morph), so engines drive body and garment morphs together."""
    keys = body.data.shape_keys
    if keys is None or len(keys.key_blocks) < 2:
        return []
    arm = next((m.object for m in body.modifiers if m.type == "ARMATURE" and m.object), None)
    prev_pos = arm.data.pose_position if arm else None
    if arm:
        arm.data.pose_position = "REST"
    vals = {kb.name: kb.value for kb in keys.key_blocks}
    for kb in keys.key_blocks:
        kb.value = 0.0
    sd = garment.modifiers.new("FollowBody", "SURFACE_DEFORM")
    sd.target = body
    bx.select_only([garment])
    done = []
    with bpy.context.temp_override(object=garment, active_object=garment):
        bpy.ops.object.modifier_move_to_index(modifier=sd.name, index=0)
        bpy.context.view_layer.update()
        bpy.ops.object.surfacedeform_bind(modifier=sd.name)
        if garment.data.shape_keys is None:
            garment.shape_key_add(name="Basis", from_mix=False)
        for kb in keys.key_blocks[1:]:
            kb.value = 1.0
            bpy.context.view_layer.update()
            bpy.ops.object.modifier_apply_as_shapekey(modifier=sd.name, keep_modifier=True)
            gk = garment.data.shape_keys.key_blocks[-1]
            gk.name, gk.value = kb.name, 0.0  # applied keys come in at 1
            kb.value = 0.0
            done.append(kb.name)
        bpy.ops.object.modifier_remove(modifier=sd.name)
    for kb in keys.key_blocks:
        kb.value = vals[kb.name]
    if arm:
        arm.data.pose_position = prev_pos
    return done


def penetration(garment, body, tol=0.0005, reach=0.1):
    """Body verts (evaluated pose) poking through: casting along the body normal, the garment is hit
    inward (behind the skin) before outward, or sits closer than tol. Verts that hit nothing within
    reach either way aren't covered by this garment (head, hands, legs) and are ignored."""
    dg = bpy.context.evaluated_depsgraph_get()
    ge, be = garment.evaluated_get(dg), body.evaluated_get(dg)
    bme = be.to_mesh()
    try:
        ginv, bmw = garment.matrix_world.inverted(), body.matrix_world
        gdir, nmat = ginv.to_3x3(), bmw.to_3x3().inverted().transposed()
        n_in, worst, covered = 0, 0.0, 0
        for v in bme.vertices:
            p = ginv @ (bmw @ v.co)
            n = (gdir @ (nmat @ v.normal)).normalized()
            hit_o, loc_o, _n, _i = ge.ray_cast(p, n, distance=reach)
            hit_i, loc_i, _n, _i = ge.ray_cast(p, -n, distance=reach)
            d_o = (loc_o - p).length if hit_o else None
            d_i = (loc_i - p).length if hit_i else None
            if d_o is None and d_i is None:
                continue
            covered += 1
            if d_i is not None and (d_o is None or d_i < d_o):
                n_in += 1
                worst = max(worst, d_i)
            elif d_o < tol:
                n_in += 1
        return {"covered_verts": covered, "poke_verts": n_in, "poke_max_m": round(worst, 5)}
    finally:
        be.to_mesh_clear()


def run(body=None, group=None, zmin=None, zmax=None, name="Garment", offset=0.008, thickness=0.003, subdiv=0,
        max_influences=4, hide_body=False, drape=0, morphs=False, check=None, **_):
    bx.object_mode()
    if not body:
        raise ValueError("--body is required")
    bod = bpy.data.objects[body]
    if check:
        return {"ok": True, "garment": check, **penetration(bpy.data.objects[check], bod)}
    verts = _region(bod, group, zmin, zmax)
    if not verts:
        raise ValueError("region is empty")
    g = _shell(bod, verts, name, offset)
    res = {"ok": True, "garment": g.name, "region_verts": len(verts), "offset_m": offset, "thickness_m": thickness}
    arm = next((m.object for m in bod.modifiers if m.type == "ARMATURE" and m.object), None)
    if bod.vertex_groups:
        _transfer_weights(g, bod, max_influences)
        res["vertex_groups"] = len(g.vertex_groups)
    if subdiv:
        sd = g.modifiers.new("Subdiv", "SUBSURF")
        sd.levels = sd.render_levels = subdiv
    if drape:
        _drape(g, bod, int(drape))
        res["draped_frames"] = int(drape)
    if morphs:
        res["morphs"] = transfer_morphs(g, bod)
    if thickness > 0:
        so = g.modifiers.new("Thickness", "SOLIDIFY")
        so.thickness, so.offset, so.use_even_offset, so.use_quality_normals = thickness, 1.0, True, True
    if arm is not None:
        am = g.modifiers.new("Armature", "ARMATURE")
        am.object = arm
        g.parent = arm
        g.matrix_parent_inverse = arm.matrix_world.inverted()
        res["armature"] = arm.name
    if hide_body:
        res["hidden_group"], res["hidden_verts"] = _hide_body(bod, verts, name)
    bpy.context.view_layer.update()
    res.update(penetration(g, bod))
    if res["poke_verts"]:
        res["warning"] = "body pokes through: raise --offset, smooth the body there, or --hide-body"
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--body", required=True)
    p.add_argument("--group", default=None)
    p.add_argument("--zmin", type=float, default=None)
    p.add_argument("--zmax", type=float, default=None)
    p.add_argument("--name", default="Garment")
    p.add_argument("--offset", type=float, default=0.008, help="ease: gap to the skin (m)")
    p.add_argument("--thickness", type=float, default=0.003, help="cloth thickness (m)")
    p.add_argument("--subdiv", type=int, default=0)
    p.add_argument("--max-influences", type=int, default=4)
    p.add_argument("--hide-body", action="store_true")
    p.add_argument("--drape", type=int, default=0, help="cloth-sim frames to settle folds (0 = off)")
    p.add_argument("--morphs", action="store_true", help="copy body shape keys as garment shape keys")
    p.add_argument("--check", default=None, help="garment to measure against --body")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
