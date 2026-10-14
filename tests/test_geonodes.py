import bpy
import fixtures as fx
from run_all import skill_module

SCATTER = {
    "name": "GN_Scatter",
    "inputs": [["Geometry", "GEOMETRY"], ["Density", "FLOAT", 10.0, {"min": 0}], ["Scale", "FLOAT", 0.1]],
    "outputs": [["Geometry", "GEOMETRY"]],
    "nodes": {
        "dist": ["GeometryNodeDistributePointsOnFaces", {"distribute_method": "RANDOM"}],
        "cube": ["GeometryNodeMeshCube"],
        "inst": ["GeometryNodeInstanceOnPoints"],
        "real": ["GeometryNodeRealizeInstances"],
        "join": ["GeometryNodeJoinGeometry"],
    },
    "links": [["in.Geometry", "dist.Mesh"], ["in.Density", "dist.Density"], ["dist.Points", "inst.Points"],
              ["cube.Mesh", "inst.Instance"], ["in.Scale", "inst.Scale"], ["inst.Instances", "real.Geometry"],
              ["real.Geometry", "join.Geometry"], ["in.Geometry", "join.Geometry"], ["join.Geometry", "out.Geometry"]],
}

REPEAT = {
    "name": "GN_Repeat",
    "inputs": [["Geometry", "GEOMETRY"], ["Count", "INT", 3]],
    "outputs": [["Geometry", "GEOMETRY"]],
    "nodes": {
        "rin": ["GeometryNodeRepeatInput"],
        "rout": ["GeometryNodeRepeatOutput"],
        "sub": ["GeometryNodeSubdivideMesh", {}, {"Level": 1}],
    },
    "pairs": [["rin", "rout"]],
    "links": [["in.Count", "rin.Iterations"], ["in.Geometry", "rin.Geometry"], ["rin.Geometry", "sub.Mesh"],
              ["sub.Mesh", "rout.Geometry"], ["rout.Geometry", "out.Geometry"]],
}


def test_build_apply_set_inputs():
    g = skill_module("blender-geometry-nodes", "gn_builder")
    fx.plane("Ground", size=4)
    r = g.run(spec=SCATTER, apply_to="Ground", set=["Density=5"])
    assert r["evaluated"]["verts"] > 4 * 8, r
    r2 = g.run(spec=SCATTER, apply_to="Ground", set=["Density=50"])
    assert r2["evaluated"]["verts"] > r["evaluated"]["verts"]
    mod = bpy.data.objects["Ground"].modifiers["GN_Scatter"]
    ident = next(i.identifier for i in mod.node_group.interface.items_tree if getattr(i, "name", "") == "Density")
    assert getattr(mod.properties.inputs, ident).value == 50


def test_repeat_zone():
    g = skill_module("blender-geometry-nodes", "gn_builder")
    fx.plane("P", size=1)
    r = g.run(spec=REPEAT, apply_to="P", set=["Count=2"])
    assert r["evaluated"]["faces"] == 16, r


def test_describe():
    g = skill_module("blender-geometry-nodes", "gn_builder")
    d = g.run(describe_types=["GeometryNodeDistributePointsOnFaces", "ShaderNodeMath", "GeometryNodeMeshBevel"])
    dist = d["nodes"]["GeometryNodeDistributePointsOnFaces"]
    assert any(s[0] == "Density" for s in dist["inputs"]) and "distribute_method" in dist["props"]
    assert "operation" in d["nodes"]["ShaderNodeMath"]["props"]


def test_reference_recipes_build_and_evaluate():
    import json
    import re
    from run_all import ROOT
    g = skill_module("blender-geometry-nodes", "gn_builder")
    text = (ROOT / "skills/blender-geometry-nodes/references/recipes.md").read_text("utf-8")
    specs = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", text, re.S)]
    assert len(specs) == 5
    fx.plane("Ground", size=4)
    fx.cube("Rock", size=0.2, location=(10, 0, 0))
    cu = bpy.data.curves.new("Path", "CURVE")
    sp = cu.splines.new("POLY")
    sp.points.add(2)
    for i, p in enumerate(sp.points):
        p.co = (i, 0, 0, 1)
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("Path", cu))
    targets = {"GN_Scatter": ("Ground", ["Instance=Rock", "Density=3"]), "GN_Pipe": ("Path", []),
               "GN_Repeat": ("Ground", ["Count=1"]), "GN_HeightMask": ("Ground", [])}
    for spec in specs:
        if spec.get("tree") == "shader":
            r = g.run(spec=spec)
            assert r["links"] == 3
            continue
        obj, sets = targets[spec["name"]]
        r = g.run(spec=spec, apply_to=obj, set=sets)
        assert r["evaluated"] and r["evaluated"]["verts"] > 0 and not r.get("node_warnings"), (spec["name"], r)
        bpy.data.objects[obj].modifiers.clear()
