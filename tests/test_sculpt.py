import fixtures as fx
from run_all import skill_module


def test_sculpt_ops_chain():
    fx.cube("Blob", size=1)
    s = skill_module("blender-sculpting", "sculpt_ops")
    r = s.run(objects=["Blob"], ops=["remesh=0.05", "symmetrize=+X", "inflate=0.02", "detail=0.01,0.2",
                                     "smooth=3", "apply", "multires=2"])
    o = r["objects"]["Blob"]
    assert o["multires_levels"] == 2 and o["evaluated_tris"] > o["base_faces"] * 2 * 10, o
    assert o["stack"] == ["Multires"]
