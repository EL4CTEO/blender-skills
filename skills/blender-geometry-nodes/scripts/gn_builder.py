"""Build node trees (Geometry Nodes, shader, compositor) from a compact JSON spec, apply them as
modifiers with input values (5.2 RNA API), and describe node types' sockets.

Spec (JSON file or dict):
{ "name": "Scatter", "tree": "geometry" | "shader" | "compositor",
  "material": "M_X",                          # shader: build inside this material
  "inputs":  [["Geometry","GEOMETRY"], ["Density","FLOAT",10,{"min":0}]],
  "outputs": [["Geometry","GEOMETRY"]],
  "nodes": { "dist": ["GeometryNodeDistributePointsOnFaces", {"distribute_method":"RANDOM"},
                      {"Density": 5.0}],                  # [type, props, input defaults]
             "rep_in": ["GeometryNodeRepeatInput"], "rep_out": ["GeometryNodeRepeatOutput", {},
                      {}, {"repeat_items": [["GEOMETRY","Geometry"]]}] },  # 4th: item collections
  "pairs": [["rep_in","rep_out"]],            # zones: repeat / simulation / foreach / closure
  "links": [["in.Geometry","dist.Mesh"], ["dist.Points","inst.Points"], ["math.0","x.1"]] }
Socket refs: node.SocketName or node.<index>; "in"/"out" = group input/output.
Usage:
  blender -b f.blend -P gn_builder.py -- --spec tree.json [--apply Plane] [--set Density=20] [--save out.blend]
  blender -b -P gn_builder.py -- --describe GeometryNodeDistributePointsOnFaces [ShaderNodeMix ...]
  MCP: import gn_builder as g; result = g.run(spec={...}, apply="Plane", set=["Density=20"])
"""
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

SOCK = {k: f"NodeSocket{v}" for k, v in {
    "GEOMETRY": "Geometry", "FLOAT": "Float", "INT": "Int", "BOOLEAN": "Bool", "BOOL": "Bool",
    "VECTOR": "Vector", "COLOR": "Color", "RGBA": "Color", "STRING": "String", "OBJECT": "Object",
    "COLLECTION": "Collection", "MATERIAL": "Material", "IMAGE": "Image", "ROTATION": "Rotation",
    "MATRIX": "Matrix", "MENU": "Menu", "SHADER": "Shader", "BUNDLE": "Bundle", "CLOSURE": "Closure"}.items()}
TREE = {"geometry": "GeometryNodeTree", "shader": "ShaderNodeTree", "compositor": "CompositorNodeTree"}


def describe(types):
    """Inputs/outputs (name, type, default) of node types, from a throwaway tree."""
    out = {}
    for t in types:
        kind = ("GeometryNodeTree" if t.startswith("GeometryNode") or t.startswith(("FunctionNode", "Node"))
                else "CompositorNodeTree" if t.startswith("CompositorNode") else "ShaderNodeTree")
        ng = bpy.data.node_groups.new("__describe__", kind)
        try:
            n = ng.nodes.new(t)

            def sock(s):
                d = getattr(s, "default_value", None)
                if d is not None and hasattr(d, "__len__") and not isinstance(d, str):
                    d = [round(x, 4) for x in d]
                elif isinstance(d, float):
                    d = round(d, 4)
                return [s.name, s.type, d] if d is not None and not isinstance(d, bpy.types.ID) else [s.name, s.type]
            props = {p.identifier: [i.identifier for i in p.enum_items] if p.type == "ENUM" else p.type
                     for p in n.bl_rna.properties if not p.is_readonly
                     and p.identifier not in bpy.types.Node.bl_rna.properties}
            out[t] = {"inputs": [sock(s) for s in n.inputs if s.enabled],
                      "outputs": [sock(s) for s in n.outputs if s.enabled], "props": props}
        except RuntimeError as e:
            out[t] = {"error": str(e)}
        finally:
            bpy.data.node_groups.remove(ng)
    return out


def _sock(nodes, ref, outputs):
    name, _, key = ref.partition(".")
    n = nodes[name]
    coll = n.outputs if outputs else n.inputs
    if key.isdigit():
        return coll[int(key)]
    s = next((s for s in coll if s.name == key and s.enabled), None) or coll.get(key)
    if s is None:
        raise KeyError(f"{ref}: no {'output' if outputs else 'input'} '{key}' on {n.bl_idname}; "
                       f"have {[s.name for s in coll if s.enabled]}")
    return s


def build(spec):
    kind = spec.get("tree", "geometry")
    if kind == "shader" and spec.get("material"):
        mat = bpy.data.materials.get(spec["material"]) or bpy.data.materials.new(spec["material"])
        nt = mat.node_tree
        if spec.get("clear", True):
            nt.nodes.clear()
    else:
        nt = bpy.data.node_groups.get(spec["name"])
        if nt is None:
            nt = bpy.data.node_groups.new(spec["name"], TREE[kind])
        nt.nodes.clear()
        nt.interface.clear()
        for io, key in (("INPUT", "inputs"), ("OUTPUT", "outputs")):
            for item in spec.get(key, []):
                s = nt.interface.new_socket(item[0], in_out=io, socket_type=SOCK[item[1].upper()])
                if len(item) > 2 and item[2] is not None and hasattr(s, "default_value"):
                    s.default_value = item[2]
                for k, v in (item[3] if len(item) > 3 else {}).items():
                    setattr(s, {"min": "min_value", "max": "max_value"}.get(k, k), v)
        if kind == "geometry":
            nt.is_modifier = True
    nodes = {}
    if kind != "shader" or not spec.get("material"):
        nodes["in"] = nt.nodes.new("NodeGroupInput")
        nodes["out"] = nt.nodes.new("NodeGroupOutput")
    for key, val in spec.get("nodes", {}).items():
        val = [val] if isinstance(val, str) else val
        n = nt.nodes.new(val[0])
        n.name = n.label = key
        for k, v in (val[1] if len(val) > 1 else {}).items():
            if k == "data_type" and hasattr(n, "data_type"):
                n.data_type = v
            else:
                setattr(n, k, bpy.data.objects.get(v) if k == "object" else v)
        for coll_name, items in (val[3] if len(val) > 3 else {}).items():
            coll = getattr(n, coll_name)
            coll.clear()
            for it in items:
                coll.new(*it)
        nodes[key] = n
    for a, b in spec.get("pairs", []):
        nodes[a].pair_with_output(nodes[b])
    for key, val in spec.get("nodes", {}).items():  # defaults after pairing (zone sockets exist now)
        val = [val] if isinstance(val, str) else val
        for k, v in (val[2] if len(val) > 2 else {}).items():
            s = _sock(nodes, f"{key}.{k}", outputs=False)
            s.default_value = bpy.data.objects.get(v, v) if isinstance(v, str) and s.type == "OBJECT" else v
    for a, b in spec.get("links", []):
        nt.links.new(_sock(nodes, a, True), _sock(nodes, b, False))
    _layout(nt)
    return nt


def _layout(nt):
    """Column layout by longest path from inputs (readable trees for humans)."""
    depth = {n: 0 for n in nt.nodes}
    for _ in range(len(nt.nodes)):
        changed = False
        for l in nt.links:
            d = depth[l.from_node] + 1
            if d > depth[l.to_node]:
                depth[l.to_node], changed = d, True
        if not changed:
            break
    rows = {}
    for n, d in sorted(depth.items(), key=lambda kv: kv[1]):
        r = rows.get(d, 0)
        n.location = (d * 260, -r * 220)
        rows[d] = r + 1


def apply(nt, ob_name, values):
    ob = bpy.data.objects[ob_name]
    mod = next((m for m in ob.modifiers if m.type == "NODES" and m.node_group == nt), None) \
        or ob.modifiers.new(nt.name, "NODES")
    mod.node_group = nt
    ids = {i.name: i.identifier for i in nt.interface.items_tree if getattr(i, "in_out", "") == "INPUT"}
    for k, v in values.items():
        item = getattr(mod.properties.inputs, ids[k])
        if isinstance(v, str) and v.startswith("@"):  # @attr_name -> read from attribute
            item.type, item.attribute_name = "ATTRIBUTE", v[1:]
        else:
            item.value = bpy.data.objects.get(v, v) if isinstance(v, str) else v
    return mod


def _parse_val(s):
    for t in (int, float):
        try:
            return t(s)
        except ValueError:
            pass
    if "," in s:
        return tuple(float(x) for x in s.split(","))
    return {"true": True, "false": False}.get(s.lower(), s)


def run(spec=None, apply_to=None, set=None, describe_types=None, **_):  # noqa: A002
    if describe_types:
        return {"ok": True, "nodes": describe(describe_types)}
    if isinstance(spec, str):
        with open(bpy.path.abspath(spec), encoding="utf-8") as f:
            spec = json.load(f)
    nt = build(spec)
    res = {"ok": True, "tree": nt.name, "nodes": len(nt.nodes), "links": len(nt.links)}
    if apply_to:
        vals = dict(kv.split("=", 1) for kv in set or [])
        mod = apply(nt, apply_to, {k: _parse_val(v) for k, v in vals.items()})
        ob = bpy.data.objects[apply_to]
        eo = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = eo.to_mesh()
        res["evaluated"] = {"verts": len(me.vertices), "faces": len(me.polygons)} if me else None
        eo.to_mesh_clear()
        res["modifier"] = mod.name
        warn = [w.message for w in getattr(mod, "node_warnings", [])]
        if warn:
            res["node_warnings"] = warn[:10]
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--spec", default=None)
    p.add_argument("--apply", dest="apply_to", default=None)
    p.add_argument("--set", nargs="*", default=None)
    p.add_argument("--describe", dest="describe_types", nargs="*", default=None)
    p.add_argument("--save", default=None)
    bx.cli(run, p)
