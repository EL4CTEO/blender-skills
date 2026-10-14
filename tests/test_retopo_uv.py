import bpy
import fixtures as fx
from run_all import skill_module


def test_uv_pack_and_texel_density_set():
    fx.cube("SM_Crate", size=1)
    up = skill_module("blender-retopology-uv", "uv_pack")
    r = up.run(objects=["SM_Crate"], method="seams", seams_from_sharp=60, lightmap=True)
    assert r["objects"]["SM_Crate"]["seams_marked"] == 12
    assert r["objects"]["SM_Crate"]["uv_maps"] == ["UVMap", "UVMap_Lightmap"]
    td = skill_module("blender-retopology-uv", "texel_density")
    m = td.run(objects=["SM_Crate"], res=1024)["objects"]["SM_Crate"]
    assert m["px_per_m"] > 0 and m["spread"] < 1.3, m
    s = td.run(objects=["SM_Crate"], res=1024, set=200)["objects"]["SM_Crate"]
    assert abs(s["after"]["px_per_m"] - 200) < 5 and s["after"]["fits_0_1"], s
    s = td.run(objects=["SM_Crate"], res=1024, set=5000)["objects"]["SM_Crate"]
    assert not s["after"]["fits_0_1"]


def test_auto_retopo_methods():
    rt = skill_module("blender-retopology-uv", "auto_retopo")
    fx.uv_sphere("Dense", segs=96, rings=48)
    r = rt.run(objects=["Dense"], method="decimate", tris=1600)
    o = r["objects"]["Dense"]
    assert o["tris_after"] <= 1700 and "Dense_low" in bpy.data.objects
    bpy.data.objects.remove(bpy.data.objects["Dense_low"])
    bpy.data.objects["Dense"].hide_set(False)
    r = rt.run(objects=["Dense"], method="quadriflow", tris=1200)
    o = r["objects"]["Dense"]
    assert 300 < o["faces_after"] < 1200, o
