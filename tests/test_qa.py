import os

import bmesh
import bpy
import fixtures as fx
from run_all import TMP, requires_gpu, skill_module


def _qa():
    return skill_module("blender-asset-qa", "qa_check")


def test_clean_cube_passes():
    c = fx.cube("SM_Box", location=(0, 0, 1))
    fx.unwrap(c)
    c.data.materials.append(bpy.data.materials.new("M_Box"))
    r = _qa().run(objects=["SM_Box"])
    assert r["pass"], r
    assert r["objects"]["SM_Box"]["tris"] == 12 and r["ground_z"] == 0


def test_detects_zfighting_between_objects_and_within_mesh():
    fx.zfight_pair()
    r = _qa().run(objects=["ZF_A", "ZF_B"], uv=False)
    assert any("ZF_A<->ZF_B" in z["where"] for z in r["zfighting"]), r["zfighting"]
    r = _qa().run(objects=["ZF_Self"], uv=False)
    assert any(z["where"] == "ZF_Self" for z in r["zfighting"]), r
    assert not r["pass"]


def test_slightly_offset_coplanar_is_zfighting_but_far_is_not():
    fx.plane("P1")
    fx.plane("P2", location=(0.3, 0, 0.0004))
    fx.plane("P3", location=(0, 0, 0.05))
    r = _qa().run(objects=["P1", "P2"], uv=False)
    assert r["zfighting"], r
    r = _qa().run(objects=["P1", "P3"], uv=False)
    assert not r["zfighting"], r


def test_detects_floating_parts_and_objects():
    fx.detached_part()
    r = _qa().run(objects=["Body", "Floater"], uv=False)
    objs = sorted(f["object"] for f in r["floating"])
    assert objs == ["Body", "Floater"], r["floating"]


def test_touching_parts_are_not_floating():
    fx.cube("Base", size=2, location=(0, 0, 1))
    fx.cube("Top", size=1, location=(0, 0, 2.5))   # rests exactly on Base
    fx.cube("Pierce", size=0.5, location=(1, 0, 1))  # intersects Base
    r = _qa().run(objects=["Base", "Top", "Pierce"], uv=False)
    assert not r["floating"], r["floating"]


def test_enclosed_part_is_not_floating():
    fx.uv_sphere("Head", radius=1, location=(0, 0, 1))
    fx.uv_sphere("Eye", radius=0.2, location=(0, -0.6, 1.2))
    r = _qa().run(objects=["Head", "Eye"], uv=False)
    assert not r["floating"] and r["enclosed"], r


def test_detects_inverted_and_inconsistent_normals_and_back_to_back():
    c = fx.cube("Inv", location=(0, 0, 1))
    bm = bmesh.new()
    bm.from_mesh(c.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(c.data)
    bm.free()
    r = _qa().run(objects=["Inv"], uv=False)
    assert r["objects"]["Inv"]["inside_out_islands"] == 1
    d = fx.cube("Inc", location=(4, 0, 1))
    bm = bmesh.new()
    bm.from_mesh(d.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:1])
    bm.to_mesh(d.data)
    bm.free()
    r = _qa().run(objects=["Inc"], uv=False)
    assert r["objects"]["Inc"]["inconsistent_normals_edges"] == 4
    fx.cube("BB1", size=1, location=(10, 0, 0.5))
    fx.cube("BB2", size=1, location=(11, 0, 0.5))
    r = _qa().run(objects=["BB1", "BB2"], uv=False)
    assert r["back_to_back"] and not r["zfighting"], r


def test_roblox_profile_flags_open_mesh_and_ngons():
    p = fx.plane("Flat")
    r = _qa().run(objects=["Flat"], profile="roblox", uv=False)
    assert r["objects"]["Flat"]["boundary_edges"] == 4
    assert any("watertight" in w for w in r["warnings"])
    assert p


def test_review_shots_renders_sheet():
    requires_gpu()
    fx.cube("SM_Box", location=(0, 0, 1))
    r = skill_module("blender-asset-qa", "review_shots").run(out=str(TMP / "qa.png"), res=128, mode="wire")
    assert os.path.getsize(r["sheet"]) > 1000 and len(r["views"]) == 4
    assert "QA_Cam" not in bpy.data.objects and len(bpy.data.objects) == 1
