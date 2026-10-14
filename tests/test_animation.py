import bpy
import fixtures as fx
from run_all import TMP, skill_module


def _walk(rig, name, dist):
    """Keyframe the hips ('spine', child of root) moving dist metres toward -Y over 24 frames."""
    from mathutils import Matrix
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    pb = rig.pose.bones["spine"]
    rest = rig.data.bones["spine"].matrix_local.copy()
    for f, d in ((1, 0.0), (24, dist)):
        bpy.context.scene.frame_set(f)
        pb.matrix = Matrix.Translation((0, -d, 0)) @ rest
        bpy.context.view_layer.update()
        pb.keyframe_insert("location", frame=f)
    return act


def test_bake_to_copy_with_root_motion_and_export():
    body, rig = fx.simple_character()  # CharRig: root > spine > chest
    tgt_data = rig.data.copy()
    tgt = bpy.data.objects.new("GAME_CharRig", tgt_data)
    bpy.context.scene.collection.objects.link(tgt)
    bpy.context.view_layer.update()
    for b in tgt.pose.bones:
        c = b.constraints.new("COPY_TRANSFORMS")
        c.target, c.subtarget = rig, b.name
    _walk(rig, "Walk", 1.0)
    _walk(rig, "Run", 2.0)
    ba = skill_module("blender-animation", "bake_action")
    lst = ba.run(list=True)["actions"]
    assert {"Walk", "Run"} <= {a["name"] for a in lst}
    r = ba.run(source="CharRig", target="GAME_CharRig", actions=["Walk", "Run"], root_motion="xy", hips="spine")
    assert [b["action"] for b in r["baked"]] == ["GAME_CharRig|Walk", "GAME_CharRig|Run"], r
    assert all("carries" in b["root_motion"] for b in r["baked"]), r
    tracks = [t.name for t in tgt.animation_data.nla_tracks]
    assert tracks == ["CLIP_Walk", "CLIP_Run"]
    # constraints muted -> target plays its own baked action; root moved, spine world pos preserved
    tgt.animation_data.action = bpy.data.actions["GAME_CharRig|Run"]
    sc = bpy.context.scene
    sc.frame_set(24)
    bpy.context.view_layer.update()
    root_moved = tgt.pose.bones["root"].matrix.translation.length
    rig.animation_data.action = bpy.data.actions["Run"]
    sc.frame_set(24)
    bpy.context.view_layer.update()
    src_spine = rig.pose.bones["spine"].matrix.translation
    assert root_moved > 1.5, root_moved
    assert (tgt.pose.bones["spine"].matrix.translation - src_spine).length < 1e-3
    ex = skill_module("blender-export-pipelines", "export_asset")
    e = ex.run(preset="gltf", objects=["GAME_CharRig"], out=str(TMP / "anim.glb"))
    names = e["files"][0]["summary"]["animation_names"]
    assert len(names) >= 2, e
