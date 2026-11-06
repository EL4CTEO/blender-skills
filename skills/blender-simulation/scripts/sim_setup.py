"""Set up and bake simulations: rigid bodies, classic cloth (presets), 5.2 node-based cloth
(experimental Cloth Dynamics asset + Collider assets), then bake / bake-to-keyframes.

Usage:
  blender -b f.blend -P sim_setup.py -- --rigid --active Crate1 Crate2 --passive Floor [--shape CONVEX_HULL]
      [--density 500] [--frames 1 120] [--bake] [--to-keys] [--save out.blend]
  blender -b f.blend -P sim_setup.py -- --cloth Flag --preset cotton --pin PinGroup --colliders Pole [--bake]
  blender -b f.blend -P sim_setup.py -- --gn-cloth Sheet --colliders Table --set Bendiness=0.5 [--bake]
  MCP: import sim_setup as s; result = s.run(rigid=True, active=["Crate"], passive=["Floor"], bake=True)
Returns per-object settings and, after baking, the final world positions / evaluated bounds.
"""
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

CLOTH = {  # Blender's built-in presets (scripts/presets/cloth)
    "cotton": dict(quality=5, mass=0.3, tension_stiffness=15, compression_stiffness=15, shear_stiffness=15,
                   bending_stiffness=0.5, tension_damping=5, air_damping=1),
    "denim": dict(quality=12, mass=1, tension_stiffness=40, compression_stiffness=40, shear_stiffness=40,
                  bending_stiffness=10, tension_damping=25, air_damping=1),
    "leather": dict(quality=15, mass=0.4, tension_stiffness=80, compression_stiffness=80, shear_stiffness=80,
                    bending_stiffness=150, tension_damping=25, air_damping=1),
    "rubber": dict(quality=7, mass=3, tension_stiffness=15, compression_stiffness=15, shear_stiffness=15,
                   bending_stiffness=25, tension_damping=25, air_damping=1),
    "silk": dict(quality=5, mass=0.15, tension_stiffness=5, compression_stiffness=5, shear_stiffness=5,
                 bending_stiffness=0.05, tension_damping=0, air_damping=1),
}
DYN_BLEND = "geometry_nodes_dynamics_assets.blend"


def _ctx(ob):
    return bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                     selected_editable_objects=[ob])


def _volume(ob):
    bm = bmesh.new()
    bm.from_object(ob, bpy.context.evaluated_depsgraph_get())
    bm.transform(ob.matrix_world)
    v = abs(bm.calc_volume(signed=False))
    bm.free()
    return v


def _asset_group(name_prefix):
    ng = next((g for g in bpy.data.node_groups if g.name.startswith(name_prefix)), None)
    if ng:
        return ng
    path = os.path.join(bpy.utils.system_resource("DATAFILES"), "assets", "nodes", DYN_BLEND)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.node_groups = [n for n in src.node_groups if n.startswith(name_prefix)][:1]
    if not dst.node_groups:
        raise RuntimeError(f"asset '{name_prefix}' not found in {DYN_BLEND} (needs Blender 5.2+)")
    return dst.node_groups[0]


def _set_inputs(mod, values):
    items = {i.name: i.identifier for i in mod.node_group.interface.items_tree if getattr(i, "in_out", "") == "INPUT"}
    for k, v in values.items():
        it = getattr(mod.properties.inputs, items[k])
        if isinstance(v, str) and v.startswith("@"):
            it.type, it.attribute_name = "ATTRIBUTE", v[1:]
        else:
            it.value = v


def _num(s):
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return {"true": True, "false": False}.get(s.lower(), s)


def run(rigid=False, active=None, passive=None, shape="CONVEX_HULL", density=500.0, friction=0.5,
        bounce=0.1, cloth=None, preset="cotton", pin=None, colliders=None, gn_cloth=None, set=None,  # noqa: A002
        frames=None, bake=False, to_keys=False, **_):
    bx.object_mode()
    sc = bpy.context.scene
    if frames:
        sc.frame_start, sc.frame_end = frames
    out = {"ok": True}
    if rigid:
        if sc.rigidbody_world is None:
            with bpy.context.temp_override(scene=sc):
                bpy.ops.rigidbody.world_add()
        rbw = sc.rigidbody_world
        if rbw.collection is None:
            rbw.collection = bpy.data.collections.new("RigidBodyWorld")
        rbw.point_cache.frame_start, rbw.point_cache.frame_end = sc.frame_start, sc.frame_end
        rbw.substeps_per_frame, rbw.solver_iterations = 10, 10
        rec = {}
        for kind, names in (("ACTIVE", active or []), ("PASSIVE", passive or [])):
            for ob in bx.objects(names):
                if ob.rigid_body is None:
                    with _ctx(ob):
                        bpy.ops.rigidbody.object_add(type=kind)
                rb = ob.rigid_body
                rb.type = kind
                rb.collision_shape = "MESH" if kind == "PASSIVE" and shape == "CONVEX_HULL" and len(
                    ob.data.polygons) > 6 else shape
                rb.friction, rb.restitution = friction, bounce
                rb.use_margin, rb.collision_margin = True, 0.001
                if kind == "ACTIVE":
                    rb.mass = max(_volume(ob) * density, 0.01)
                rec[ob.name] = {"type": kind, "shape": rb.collision_shape, "mass": round(rb.mass, 3)}
        out["rigid"] = rec
    if cloth:
        ob = bpy.data.objects[cloth]
        m = next((m for m in ob.modifiers if m.type == "CLOTH"), None) or ob.modifiers.new("Cloth", "CLOTH")
        for k, v in CLOTH[preset].items():
            setattr(m.settings, k, v)
        m.collision_settings.use_collision = True
        m.collision_settings.use_self_collision = True
        m.collision_settings.distance_min = 0.005
        if pin:
            m.settings.vertex_group_mass = pin
        m.point_cache.frame_start, m.point_cache.frame_end = sc.frame_start, sc.frame_end
        out["cloth"] = {"object": ob.name, "preset": preset, "pin": pin}
    if gn_cloth:
        ob = bpy.data.objects[gn_cloth]
        ng = _asset_group("Cloth Dynamics")
        mod = next((m for m in ob.modifiers if m.type == "NODES" and m.node_group == ng), None) \
            or ob.modifiers.new("Cloth Dynamics", "NODES")
        mod.node_group = ng
        vals = {k: _num(v) for k, v in (kv.split("=", 1) for kv in set or [])}
        if pin:
            vals["Pin Group"] = f"@{pin}"
        if colliders:
            col = bpy.data.collections.get("Effectors") or bpy.data.collections.new("Effectors")
            if col.name not in sc.collection.children:
                sc.collection.children.link(col)
            vals["Effectors Collection"] = col
        _set_inputs(mod, vals)
        out["gn_cloth"] = {"object": ob.name, "group": ng.name, "inputs": {k: str(v) for k, v in vals.items()}}
    if colliders:
        cg = _asset_group("Collider") if gn_cloth else None
        for c in bx.objects(colliders):
            if gn_cloth:
                if not any(m.type == "NODES" and m.node_group == cg for m in c.modifiers):
                    c.modifiers.new("Collider", "NODES").node_group = cg
                col = bpy.data.collections["Effectors"]
                if c.name not in col.objects:
                    col.objects.link(c)
            if (cloth or not gn_cloth) and not any(m.type == "COLLISION" for m in c.modifiers):
                c.modifiers.new("Collision", "COLLISION")
        out["colliders"] = colliders
    if bake:
        # step through frames in order: works for point caches AND GN simulation zones headless
        keyed = [bpy.data.objects[n] for n, r in out.get("rigid", {}).items() if r["type"] == "ACTIVE"]             if rigid and to_keys else []
        mats = {o: [] for o in keyed}
        for f in range(sc.frame_start, sc.frame_end + 1):
            sc.frame_set(f)
            for o in keyed:
                mats[o].append((f, o.matrix_world.copy()))
        if keyed:  # rigidbody.bake_to_keyframes needs a UI context; do it by hand
            for o, samples in mats.items():
                with _ctx(o):
                    bpy.ops.rigidbody.object_remove()
                o.rotation_mode = "QUATERNION"
                for f, m in samples:
                    o.matrix_world = m
                    o.keyframe_insert("location", frame=f)
                    o.keyframe_insert("rotation_quaternion", frame=f)
            out["baked_to_keyframes"] = [o.name for o in keyed]
        res = {}
        for n in list(out.get("rigid", {})) + [x for x in (cloth, gn_cloth) if x]:
            ob = bpy.data.objects[n]
            ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
            zs = [(ev.matrix_world @ v.co).z for v in ev.data.vertices] if ev.type == "MESH" else [0]
            res[n] = {"loc": bx.r(tuple(ev.matrix_world.translation), 3), "min_z": round(min(zs), 3)}
        out["final_frame"] = sc.frame_end
        out["result"] = res
    return out


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--rigid", action="store_true")
    p.add_argument("--active", nargs="*", default=None)
    p.add_argument("--passive", nargs="*", default=None)
    p.add_argument("--shape", default="CONVEX_HULL", choices=["CONVEX_HULL", "MESH", "BOX", "SPHERE", "CAPSULE",
                                                             "CYLINDER", "CONE", "COMPOUND"])
    p.add_argument("--density", type=float, default=500.0, help="kg/m3 (wood 500, concrete 2400, steel 7850)")
    p.add_argument("--friction", type=float, default=0.5)
    p.add_argument("--bounce", type=float, default=0.1)
    p.add_argument("--cloth", default=None)
    p.add_argument("--preset", default="cotton", choices=list(CLOTH))
    p.add_argument("--pin", default=None, help="vertex group (pinned = weight 1)")
    p.add_argument("--colliders", nargs="*", default=None)
    p.add_argument("--gn-cloth", default=None)
    p.add_argument("--set", nargs="*", default=None, help="GN cloth inputs Name=value")
    p.add_argument("--frames", nargs=2, type=int, default=None)
    p.add_argument("--bake", action="store_true")
    p.add_argument("--to-keys", action="store_true", help="rigid bodies -> keyframes (for export)")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
