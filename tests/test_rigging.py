import bmesh
import bpy
import fixtures as fx
from mathutils import Matrix
from run_all import skill_module


def _humanoid_mesh():
    """Crude closed humanoid (torso, head, arms in T, legs) ~1.8 m, union of boxes (non-manifold joins)."""
    def build(bm):
        for size, loc in (((0.4, 0.25, 0.6), (0, 0, 1.2)), ((0.25, 0.25, 0.25), (0, 0, 1.68)),
                          ((0.7, 0.12, 0.12), (0.55, 0, 1.42)), ((0.7, 0.12, 0.12), (-0.55, 0, 1.42)),
                          ((0.15, 0.15, 0.9), (0.11, 0, 0.45)), ((0.15, 0.15, 0.9), (-0.11, 0, 0.45))):
            r = bmesh.ops.create_cube(bm, size=1, matrix=Matrix.Translation(loc) @ Matrix.Diagonal((*size, 1)))
            bmesh.ops.subdivide_edges(bm, edges=list({e for v in r["verts"] for e in v.link_edges}), cuts=4,
                                      use_grid_fill=True)
    return fx.mesh_object("Body", build)


def test_rigify_pipeline_bind_check_stress():
    rb = skill_module("blender-character-rigging", "rigify_build")
    body = _humanoid_mesh()
    r = rb.run(add="basic_human", fit="Body", generate=True)
    assert r["rig"] == "RIG_Body" and r["deform_bones"] > 20, r
    bind = skill_module("blender-character-rigging", "bind_mesh")
    b = bind.run(armature="RIG_Body", meshes=["Body"], method="auto")["meshes"]["Body"]
    assert b["unweighted_verts"] == 0 and b["max_influences"] <= 4, b
    g = rb.run(rig="RIG_Body", game_skel=True)["game_skeleton"]
    gs = bpy.data.objects[g["name"]]
    assert "root" in gs.data.bones and "spine" in gs.data.bones and "thigh.L" in gs.data.bones
    assert gs.data.bones["thigh.L"].parent.name.startswith("spine")
    assert body.modifiers["Armature"].object == gs and "spine" in body.vertex_groups
    chk = skill_module("blender-character-rigging", "rig_check").run(armature=gs.name, profile="unity")
    assert not [e for e in chk["errors"] if "unweighted" in e or "influences" in e], chk
    assert chk["profile"]["humanoid_map"]["LeftUpperLeg"] == "thigh.L", chk["profile"]
    st = skill_module("blender-character-rigging", "stress_poses").run(armature="RIG_Body")
    assert not st["missing_roles"], st
    assert st["bones_used"]["upper_arm.L"] == "upper_arm_fk.L"
    # the posed control rig must move the game skeleton (constraints)
    bpy.context.scene.frame_set(30)
    bpy.context.view_layer.update()
    assert (gs.pose.bones["shin.L"].tail - gs.data.bones["shin.L"].tail_local).length > 0.1


def test_proxy_bind_and_fix():
    body, arm = fx.simple_character()
    bind = skill_module("blender-character-rigging", "bind_mesh")
    r = bind.run(armature="CharRig", meshes=["Char"], method="proxy")["meshes"]["Char"]
    assert r["method"] == "proxy" and r["unweighted_verts"] == 0, r
    chk = skill_module("blender-character-rigging", "rig_check").run(armature="CharRig", fix=True)
    assert chk["skin"]["Char"]["over_4"] == 0
