import bpy
import fixtures as fx
from mathutils import Vector
from run_all import skill_module


def test_garment_weights_mask_and_pose():
    body, arm = fx.simple_character()
    gm = skill_module("blender-clothing", "garment")
    r = gm.run(body="Char", zmin=0.7, zmax=1.6, name="Shirt", hide_body=True)
    assert r["ok"] and r["poke_verts"] == 0 and r["armature"] == "CharRig" and r["vertex_groups"] == 3, r
    sh = bpy.data.objects["Shirt"]
    assert [m.type for m in sh.modifiers] == ["SOLIDIFY", "ARMATURE"] and sh.parent == arm
    assert all(len(v.groups) <= 4 and abs(sum(g.weight for g in v.groups) - 1) < 1e-3 for v in sh.data.vertices)
    assert body.modifiers["Hidden_Shirt"].type == "MASK" and 0 < r["hidden_verts"] < r["region_verts"]
    pb = arm.pose.bones["chest"]
    pb.rotation_mode, pb.rotation_euler = "XYZ", (0.5, 0, 0)
    bpy.context.view_layer.update()
    assert gm.run(body="Char", check="Shirt")["poke_verts"] == 0  # weights follow the pose
    rigid = gm.run(body="Char", zmin=0.7, zmax=1.6, name="Rigid")
    bpy.data.objects["Rigid"].modifiers.remove(bpy.data.objects["Rigid"].modifiers["Armature"])
    bpy.context.view_layer.update()
    assert gm.run(body="Char", check="Rigid")["poke_verts"] > 20 and rigid["ok"]  # the check catches poke-through


def test_garment_morphs_and_drape():
    body, _arm = fx.simple_character()
    body.shape_key_add(name="Basis")
    fat = body.shape_key_add(name="Fat")
    fat.value = 0.0  # shape_key_add creates keys at 1.0
    for i, v in enumerate(body.data.vertices):
        fat.data[i].co = v.co * Vector((1.3, 1.3, 1.0))
    gm = skill_module("blender-clothing", "garment")
    r = gm.run(body="Char", zmin=0.7, zmax=1.6, name="Shirt", morphs=True, drape=20)
    assert r["morphs"] == ["Fat"] and r["draped_frames"] == 20 and r["poke_verts"] == 0, r
    sh = bpy.data.objects["Shirt"]
    fat.value = 1.0
    bpy.context.view_layer.update()
    assert gm.run(body="Char", check="Shirt")["poke_verts"] > 50  # body morph alone pokes through
    sh.data.shape_keys.key_blocks["Fat"].value = 1.0
    bpy.context.view_layer.update()
    assert gm.run(body="Char", check="Shirt")["poke_verts"] == 0  # matching garment key fixes it
