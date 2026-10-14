import bpy
import fixtures as fx
from run_all import skill_module


def test_lods_halve_and_cleanup():
    fx.uv_sphere("SM_Rock", segs=64, rings=32)
    r = skill_module("blender-game-optimization", "make_lods").run(objects=["SM_Rock"], do_cleanup=True, rename=True)
    lods = r["lods"]["SM_Rock_LOD0"]
    assert lods["LOD1"] < lods["LOD0"] * 0.6 and lods["LOD3"] < lods["LOD0"] * 0.2, lods
    assert {"SM_Rock_LOD1", "SM_Rock_LOD2", "SM_Rock_LOD3"} <= set(bpy.data.objects.keys())


def test_mesh_stats_budget():
    ob = fx.uv_sphere("SM_Ball", segs=128, rings=64)
    for i in range(3):
        ob.data.materials.append(bpy.data.materials.new(f"M{i}"))
    r = skill_module("blender-game-optimization", "mesh_stats").run(objects=["SM_Ball"], budget="mobile")
    assert not r["budget"]["pass"] and any("tris" in o for o in r["budget"]["over"])
    assert any("materials" in o for o in r["budget"]["over"])
