import bpy
import fixtures as fx
from run_all import skill_module


def test_midpoly_stack_with_boolean_and_apply():
    m = skill_module("blender-hardsurface-modeling", "apply_stack")
    fx.cube("Body", size=2, location=(0, 0, 1))
    fx.cube("Cut", size=0.6, location=(0, -1, 1.2))
    r = m.run(objects=["Body"], cutters=["Cut"], preset="midpoly")
    o = r["objects"]["Body"]
    assert o["tris_final"] > o["tris_base"] and o["stack"][:3] == ["HS_Bool_Cut", "HS_Bevel", "HS_WeightedNormal"]
    assert bpy.data.objects["Cut"].hide_render
    r = m.run(objects=["Body"], cutters=["Cut"], preset="midpoly", triangulate=True, apply=True)
    assert not bpy.data.objects["Body"].modifiers and all("FAILED" not in a for a in r["objects"]["Body"]["applied"])
    assert bpy.data.objects["Body"].data.has_custom_normals


def test_subd_preset_adds_smooth_by_angle():
    m = skill_module("blender-hardsurface-modeling", "apply_stack")
    fx.cube("Box")
    r = m.run(objects=["Box"], preset="subd", solver="MANIFOLD")
    assert "HS_SmoothByAngle" in r["objects"]["Box"]["stack"]


def test_hardsurface_snippet_attributes():
    ob = fx.cube("Attr")
    me = ob.data
    bw = me.attributes.get("bevel_weight_edge") or me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
    sh = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    bw.data[0].value = 1.0
    sh.data[0].value = True
    mod = ob.modifiers.new("B", "BEVEL")
    mod.limit_method = "WEIGHT"
    assert bpy.context.evaluated_depsgraph_get() and len(me.edges) == 12
