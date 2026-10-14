import bmesh
import bpy
import fixtures as fx
from run_all import skill_module


def _grid(name, size=2.0, cuts=20, z=2.0):
    return fx.mesh_object(name, lambda bm: bmesh.ops.create_grid(bm, x_segments=cuts, y_segments=cuts,
                                                                    size=size / 2), location=(0, 0, z))


def test_rigid_body_drop_and_keys():
    fx.cube("Floor", size=1, location=(0, 0, -0.5)).scale = (10, 10, 1)
    fx.cube("Crate", size=0.5, location=(0, 0, 3))
    s = skill_module("blender-simulation", "sim_setup")
    r = s.run(rigid=True, active=["Crate"], passive=["Floor"], frames=(1, 60), bake=True, to_keys=True)
    assert abs(r["rigid"]["Crate"]["mass"] - 0.125 * 500) < 1, r
    assert abs(r["result"]["Crate"]["min_z"]) < 0.05, r["result"]   # resting on the floor
    assert bpy.data.objects["Crate"].animation_data.action is not None


def test_classic_cloth_drapes_on_collider():
    fx.cube("Table", size=1, location=(0, 0, 0.5))
    _grid("Cloth", z=1.5)
    s = skill_module("blender-simulation", "sim_setup")
    r = s.run(cloth="Cloth", preset="cotton", colliders=["Table"], frames=(1, 40), bake=True)
    z = r["result"]["Cloth"]["min_z"]
    assert z < 1.0, r["result"]   # fell and draped over the edges


def test_gn_cloth_52_asset():
    fx.cube("Table", size=1, location=(0, 0, 0.5))
    _grid("Sheet", z=1.5, cuts=16)
    s = skill_module("blender-simulation", "sim_setup")
    r = s.run(gn_cloth="Sheet", colliders=["Table"], frames=(1, 40), bake=True)
    assert r["gn_cloth"]["group"].startswith("Cloth Dynamics")
    assert r["result"]["Sheet"]["min_z"] < 1.4, r["result"]
