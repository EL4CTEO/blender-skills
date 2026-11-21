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


def test_rig_check_dense_mesh():
    """Issue #11: >= 4000 verts makes the symmetry sample step > 1 (bpy collections reject stepped slices)."""
    body = fx.uv_sphere("Dense", segs=96, rings=48)
    assert len(body.data.vertices) >= 4000
    arm = bpy.data.objects.new("DenseRig", bpy.data.armatures.new("DenseRig"))
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    b = arm.data.edit_bones.new("spine")
    b.head, b.tail = (0, 0, -1), (0, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    body.parent = arm
    body.modifiers.new("Armature", "ARMATURE").object = arm
    body.vertex_groups.new(name="spine").add(range(len(body.data.vertices)), 1.0, "REPLACE")
    chk = skill_module("blender-character-rigging", "rig_check").run(armature="DenseRig", profile="game")
    assert chk["skin"]["Dense"]["verts"] == len(body.data.vertices), chk
    assert chk["skin"]["Dense"]["unweighted"] == 0, chk


def test_bind_tiny_and_huge_rigs_get_real_weights():
    """Bone heat fails at mm/km world sizes (all weight on one bone); bind_mesh binds at human size."""
    for s in (0.001, 1000):
        body, arm = fx.simple_character()
        arm.scale = (s,) * 3
        bpy.context.view_layer.update()
        before = arm.matrix_world.copy()
        r = skill_module("blender-character-rigging", "bind_mesh").run(armature="CharRig", meshes=["Char"])
        assert "note" in r and r["meshes"]["Char"]["max_influences"] >= 2, r
        assert (arm.matrix_world - before).to_3x3().to_scale().length < 1e-6 * max(s, 1)
        vg = {g.index: g.name for g in body.vertex_groups}
        v = next(v for v in body.data.vertices if abs(v.co.z - 1.32) < 0.1)
        assert {vg[g.group] for g in v.groups if g.weight > 0.05} == {"spine", "chest"}, [(vg[g.group], g.weight) for g in v.groups]
        bpy.data.objects.remove(body)
        bpy.data.objects.remove(arm)
