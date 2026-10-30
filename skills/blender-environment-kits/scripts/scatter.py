"""Biome scatter with Geometry Nodes: Poisson-disk instances of a collection on a surface, filtered by
max slope, height band and an optional density mask, with random yaw/scale and partial normal
alignment. Instances stay instances (cheap, GPU-instanced in glTF) unless --realize.

One modifier per layer (--name), e.g. trees on gentle slopes, rocks on steep ones, grass in a mask.
Height is in the target's object space. The result counts the instances and checks every one
against the slope and height limits.
Usage:
  blender -b f.blend -P scatter.py -- --target Terrain --collection Trees [--density 0.02]
      [--min-distance 4] [--max-slope 25] [--height-min -1e9] [--height-max 1e9] [--mask VG|ATTR]
      [--scale 0.8 1.2] [--align 0.0] [--seed 0] [--realize] [--name ENV_Trees]
      [--export-points //trees.json] [--save out.blend]
  MCP: import scatter; print(scatter.run(target="Terrain", collection="Rocks", density=0.1, max_slope=60))
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector, geometry

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

TREE = "ENV_Scatter"


def _on(socks, name):
    """Enabled socket by name: Random Value keeps one hidden Min/Max/Value per data type (5.2 renamed ids)."""
    return next(s for s in socks if s.enabled and s.name == name)


def build_tree():
    ng = bpy.data.node_groups.get(TREE)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(TREE, "GeometryNodeTree")
    ng.is_modifier = True
    for nm, kind, d in (("Geometry", "Geometry", None), ("Collection", "Collection", None),
                        ("Density", "Float", 0.1), ("Distance Min", "Float", 1.0), ("Max Slope", "Float", 30.0),
                        ("Height Min", "Float", -1e9), ("Height Max", "Float", 1e9), ("Mask", "Float", 1.0),
                        ("Scale Min", "Float", 0.8), ("Scale Max", "Float", 1.2), ("Align", "Float", 0.0),
                        ("Seed", "Int", 0), ("Realize", "Bool", False)):
        s = ng.interface.new_socket(nm, in_out="INPUT", socket_type=f"NodeSocket{kind}")
        if d is not None:
            s.default_value = d
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    L = ng.links.new

    def N(type_, **props):
        node = ng.nodes.new(type_)
        for k, v in props.items():
            setattr(node, k, v)
        return node
    gi, go = N("NodeGroupInput"), N("NodeGroupOutput")
    I = gi.outputs  # noqa: E741
    dist = N("GeometryNodeDistributePointsOnFaces", distribute_method="POISSON")
    L(I["Geometry"], dist.inputs["Mesh"])
    L(I["Density"], dist.inputs["Density Max"])
    L(I["Distance Min"], dist.inputs["Distance Min"])
    L(I["Mask"], dist.inputs["Density Factor"])
    L(I["Seed"], dist.inputs["Seed"])
    # keep points whose surface normal is within Max Slope of up and whose height is inside the band
    sep_n = N("ShaderNodeSeparateXYZ")
    L(dist.outputs["Normal"], sep_n.inputs[0])
    cosmax = N("ShaderNodeMath", operation="COSINE")
    rad = N("ShaderNodeMath", operation="RADIANS")
    L(I["Max Slope"], rad.inputs[0])
    L(rad.outputs[0], cosmax.inputs[0])
    flat = N("FunctionNodeCompare", data_type="FLOAT", operation="GREATER_EQUAL")
    L(sep_n.outputs["Z"], _on(flat.inputs, "A"))
    L(cosmax.outputs[0], _on(flat.inputs, "B"))
    sep_p = N("ShaderNodeSeparateXYZ")
    L(N("GeometryNodeInputPosition").outputs[0], sep_p.inputs[0])
    above = N("FunctionNodeCompare", data_type="FLOAT", operation="GREATER_EQUAL")
    L(sep_p.outputs["Z"], _on(above.inputs, "A"))
    L(I["Height Min"], _on(above.inputs, "B"))
    below = N("FunctionNodeCompare", data_type="FLOAT", operation="LESS_EQUAL")
    L(sep_p.outputs["Z"], _on(below.inputs, "A"))
    L(I["Height Max"], _on(below.inputs, "B"))
    a1 = N("FunctionNodeBooleanMath", operation="AND")
    L(flat.outputs[0], a1.inputs[0])
    L(above.outputs[0], a1.inputs[1])
    keep = N("FunctionNodeBooleanMath", operation="AND")
    L(a1.outputs[0], keep.inputs[0])
    L(below.outputs[0], keep.inputs[1])
    # rotation: lean Z toward the surface normal by Align, then a random yaw about the local Z
    yaw = N("FunctionNodeRandomValue", data_type="FLOAT")
    _on(yaw.inputs, "Max").default_value = 2 * math.pi
    L(I["Seed"], _on(yaw.inputs, "Seed"))
    eul = N("ShaderNodeCombineXYZ")
    L(_on(yaw.outputs, "Value"), eul.inputs["Z"])
    e2r = N("FunctionNodeEulerToRotation")
    L(eul.outputs[0], e2r.inputs[0])
    align = N("FunctionNodeAlignRotationToVector")
    align.axis = "Z"
    L(I["Align"], align.inputs["Factor"])
    L(dist.outputs["Normal"], align.inputs["Vector"])
    rot = N("FunctionNodeRotateRotation")
    rot.rotation_space = "LOCAL"
    L(align.outputs[0], rot.inputs["Rotation"])
    L(e2r.outputs[0], rot.inputs["Rotate By"])
    scl = N("FunctionNodeRandomValue", data_type="FLOAT")
    L(I["Scale Min"], _on(scl.inputs, "Min"))
    L(I["Scale Max"], _on(scl.inputs, "Max"))
    sd = N("ShaderNodeMath", operation="ADD")
    L(I["Seed"], sd.inputs[0])
    sd.inputs[1].default_value = 7
    L(sd.outputs[0], _on(scl.inputs, "Seed"))
    col = N("GeometryNodeCollectionInfo")
    col.transform_space = "ORIGINAL"
    L(I["Collection"], col.inputs["Collection"])
    col.inputs["Separate Children"].default_value = True
    col.inputs["Reset Children"].default_value = True  # each child instanced at its own origin
    inst = N("GeometryNodeInstanceOnPoints")
    L(dist.outputs["Points"], inst.inputs["Points"])
    L(keep.outputs[0], inst.inputs["Selection"])
    L(col.outputs[0], inst.inputs["Instance"])
    inst.inputs["Pick Instance"].default_value = True
    pick = N("FunctionNodeRandomValue", data_type="INT")
    _on(pick.inputs, "Min").default_value, _on(pick.inputs, "Max").default_value = 0, 1 << 20
    L(I["Seed"], _on(pick.inputs, "Seed"))
    L(_on(pick.outputs, "Value"), inst.inputs["Instance Index"])
    L(rot.outputs[0], inst.inputs["Rotation"])
    L(_on(scl.outputs, "Value"), inst.inputs["Scale"])
    real = N("GeometryNodeRealizeInstances")
    L(inst.outputs[0], real.inputs["Geometry"])
    sw = N("GeometryNodeSwitch", input_type="GEOMETRY")
    L(I["Realize"], sw.inputs["Switch"])
    L(inst.outputs[0], sw.inputs["False"])
    L(real.outputs[0], sw.inputs["True"])
    join = N("GeometryNodeJoinGeometry")
    L(sw.outputs[0], join.inputs[0])
    L(I["Geometry"], join.inputs[0])
    L(join.outputs[0], go.inputs[0])
    return ng


def _instances(target):
    dg = bpy.context.evaluated_depsgraph_get()
    return [(i.matrix_world.copy(), i.object.original.name) for i in dg.object_instances
            if i.is_instance and i.parent and i.parent.original == target]


def run(target=None, collection=None, density=0.1, min_distance=1.0, max_slope=30.0, height_min=-1e9,
        height_max=1e9, mask=None, scale=(0.8, 1.2), align=0.0, seed=0, realize=False, name=None,
        export_points=None, **_):
    bx.object_mode()
    if not target or not collection:
        raise ValueError("--target and --collection are required")
    tgt, coll = bpy.data.objects[target], bpy.data.collections[collection]
    if not coll.all_objects:
        raise ValueError(f"collection {collection!r} is empty")
    name = name or f"ENV_{collection}"
    ng = build_tree()
    md = tgt.modifiers.get(name) or tgt.modifiers.new(name, "NODES")
    md.node_group = ng
    ids = {i.name: i.identifier for i in ng.interface.items_tree if getattr(i, "in_out", "") == "INPUT"}
    ins = md.properties.inputs
    for k, v in (("Collection", coll), ("Density", density), ("Distance Min", min_distance), ("Max Slope", max_slope),
                 ("Height Min", height_min), ("Height Max", height_max), ("Scale Min", scale[0]),
                 ("Scale Max", scale[1]), ("Align", align), ("Seed", seed), ("Realize", realize)):
        getattr(ins, ids[k]).value = v
    m = getattr(ins, ids["Mask"])
    if mask:
        m.type, m.attribute_name = "ATTRIBUTE", mask
    else:
        m.type, m.value = "VALUE", 1.0
    for c in (coll,):  # the source collection shouldn't render at the origin
        lc = _layer_coll(bpy.context.view_layer.layer_collection, c.name)
        if lc is not None:
            lc.exclude = True
    res = {"ok": True, "target": target, "modifier": name, "collection": collection}
    if realize:
        me = tgt.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        res["tris_total"] = sum(len(p.vertices) - 2 for p in me.polygons)
        tgt.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
        return res
    inst = _instances(tgt)
    res["instances"] = len(inst)
    res["by_source"] = {}
    for _m, src in inst:
        res["by_source"][src] = res["by_source"].get(src, 0) + 1
    if inst:  # verify the filters on the surface under each instance, with GN's interpolated normal
        surf = tgt.evaluated_get(bpy.context.evaluated_depsgraph_get())  # instances aren't in its mesh
        me = surf.to_mesh()
        me.calc_loop_triangles()
        cn = me.corner_normals
        by_poly = {}
        for t in me.loop_triangles:
            by_poly.setdefault(t.polygon_index, []).append(t)
        tinv = tgt.matrix_world.inverted()
        worst, zs = 0.0, []
        for mw, _src in inst[:: max(1, len(inst) // 500)]:
            p = tinv @ mw.translation
            ok, loc, _n, fi = surf.closest_point_on_mesh(p)
            if not ok:
                continue
            best = None
            for t in by_poly.get(fi, []):
                a, b, c = (me.vertices[v].co for v in t.vertices)
                w = geometry.barycentric_transform(loc, a, b, c, Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
                if best is None or min(w) > min(best[1]):
                    best = (t, w)
            t, w = best
            n = sum((cn[li].vector * wi for li, wi in zip(t.loops, w)), Vector()).normalized()
            worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, n.z)))))
            zs.append(p.z)
        surf.to_mesh_clear()
        res["slope_max_deg"] = round(worst, 2)
        res["height_range"] = [round(min(zs), 3), round(max(zs), 3)]
        area = sum(pl.area for pl in tgt.data.polygons) * abs(tgt.matrix_world.determinant()) ** (2 / 3)
        res["per_m2"] = round(len(inst) / max(area, 1e-9), 5)
    else:
        res["warning"] = "no instances: density too low, or slope/height/mask filters exclude everything"
    if export_points and inst:  # world transforms for engine foliage/instancing tools (Z-up, meters)
        path = bpy.path.abspath(export_points)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        rows = []
        for mw, src in inst:
            loc, rot, scl = mw.decompose()
            rows.append({"source": src, "location": [round(v, 4) for v in loc],
                         "rotation_quat_wxyz": [round(v, 5) for v in rot], "scale": [round(v, 4) for v in scl]})
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"up": "Z", "units": "m", "instances": rows}, f)
        res["points_file"] = path
    return res


def _layer_coll(lc, name):
    if lc.collection.name == name:
        return lc
    for ch in lc.children:
        f = _layer_coll(ch, name)
        if f is not None:
            return f
    return None


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--target", required=True)
    p.add_argument("--collection", required=True)
    for k, d in (("density", 0.1), ("min-distance", 1.0), ("max-slope", 30.0), ("height-min", -1e9),
                 ("height-max", 1e9), ("align", 0.0)):
        p.add_argument(f"--{k}", type=float, default=d)
    p.add_argument("--mask", default=None, help="vertex group / float attribute = density factor")
    p.add_argument("--scale", type=float, nargs=2, default=(0.8, 1.2))
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--realize", action="store_true")
    p.add_argument("--name", default=None)
    p.add_argument("--export-points", default=None, help="JSON of instance world transforms")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
