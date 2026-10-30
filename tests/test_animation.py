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


HUMANOID = {  # canonical -> (head, tail, parent) in world meters, Z-up, facing -Y
    "hips": ((0, 0, 1.0), (0, 0, 1.12), None), "spine": ((0, 0, 1.12), (0, 0, 1.3), "hips"),
    "chest": ((0, 0, 1.3), (0, 0, 1.5), "spine"), "neck": ((0, 0, 1.5), (0, 0, 1.6), "chest"),
    "head": ((0, 0, 1.6), (0, 0, 1.8), "neck"),
    "upperarm.L": ((0.18, 0, 1.45), (0.45, 0, 1.45), "chest"), "forearm.L": ((0.45, 0, 1.45), (0.7, 0, 1.45), "upperarm.L"),
    "hand.L": ((0.7, 0, 1.45), (0.8, 0, 1.45), "forearm.L"),
    "upperarm.R": ((-0.18, 0, 1.45), (-0.45, 0, 1.45), "chest"), "forearm.R": ((-0.45, 0, 1.45), (-0.7, 0, 1.45), "upperarm.R"),
    "hand.R": ((-0.7, 0, 1.45), (-0.8, 0, 1.45), "forearm.R"),
    "thigh.L": ((0.1, 0, 1.0), (0.1, 0, 0.55), "hips"), "shin.L": ((0.1, 0, 0.55), (0.1, 0, 0.1), "thigh.L"),
    "foot.L": ((0.1, 0, 0.1), (0.1, -0.15, 0.0), "shin.L"),
    "thigh.R": ((-0.1, 0, 1.0), (-0.1, 0, 0.55), "hips"), "shin.R": ((-0.1, 0, 0.55), (-0.1, 0, 0.1), "thigh.R"),
    "foot.R": ((-0.1, 0, 0.1), (-0.1, -0.15, 0.0), "shin.R"),
}
MIXAMO = {"hips": "Hips", "spine": "Spine", "chest": "Spine1", "neck": "Neck", "head": "Head",
          "upperarm.L": "LeftArm", "forearm.L": "LeftForeArm", "hand.L": "LeftHand",
          "upperarm.R": "RightArm", "forearm.R": "RightForeArm", "hand.R": "RightHand",
          "thigh.L": "LeftUpLeg", "shin.L": "LeftLeg", "foot.L": "LeftFoot",
          "thigh.R": "RightUpLeg", "shin.R": "RightLeg", "foot.R": "RightFoot"}


def _rig(name, names, obj_matrix, legs=1.0, roll=0.0):
    from mathutils import Matrix, Vector
    arm = bpy.data.objects.new(name, bpy.data.armatures.new(name))
    bpy.context.scene.collection.objects.link(arm)
    arm.matrix_world = obj_matrix
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    inv = obj_matrix.inverted()

    def w(p):  # stretch legs below the hips to test proportions
        p = Vector(p)
        return Vector((p.x, p.y, p.z * legs if p.z <= 1.0 else p.z - 1.0 + legs))
    for canon, (h, t, par) in HUMANOID.items():
        eb = arm.data.edit_bones.new(names[canon])
        eb.head, eb.tail = inv @ w(h), inv @ w(t)
        eb.roll = roll
        if par:
            eb.parent = arm.data.edit_bones[names[par]]
            eb.use_connect = canon not in ("upperarm.L", "upperarm.R", "thigh.L", "thigh.R")
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def test_retarget_mixamo_to_rigify_names():
    import math as m
    from mathutils import Euler, Matrix
    src = _rig("Mocap", {k: "mixamorig:" + v for k, v in MIXAMO.items()},
               Matrix.Rotation(m.pi / 2, 4, "X") @ Matrix.Scale(0.01, 4), roll=0.7)  # Mixamo FBX: Y-up bones, cm
    tgt = _rig("GAME_RIG", {k: ("DEF-" + k.replace("upperarm", "upper_arm")) for k in HUMANOID},
               Matrix.Identity(4), legs=1.15)
    sc = bpy.context.scene
    for f, sp, la, th, hx in ((1, (0, 0, 0), (0, 0, 0), (0, 0, 0), 0.0), (10, (0.4, 0.2, 0), (0, 0.9, 0.5), (-0.8, 0, 0), 5.0),
                              (20, (-0.3, 0, 0.3), (0.6, -0.4, 0), (0.5, 0.1, 0), 12.0)):
        for bn, e in (("mixamorig:Spine", sp), ("mixamorig:LeftArm", la), ("mixamorig:RightUpLeg", th)):
            pb = src.pose.bones[bn]
            pb.rotation_mode, pb.rotation_euler = "XYZ", Euler(e)
            pb.keyframe_insert("rotation_euler", frame=f)
        hp = src.pose.bones["mixamorig:Hips"]
        hp.location = (hx, 0, 0)  # local units are cm-scaled
        hp.keyframe_insert("location", frame=f)
    rt = skill_module("blender-animation", "retarget")
    shown = rt.run(source="Mocap", target="GAME_RIG", show_map=True)
    assert shown["map"]["DEF-upper_arm.L"] == "mixamorig:LeftArm" and shown["map"]["DEF-shin.R"] == "mixamorig:RightLeg"
    assert shown["hips"] == "DEF-hips" and not shown["unmapped_key_parts"], shown
    r = rt.run(source="Mocap", target="GAME_RIG", name="Walk")
    assert r["mapped"] == 17 and r["frames"] == [1, 20] and abs(r["hips_scale"] - 1.15) < 1e-3, r
    assert r["max_error_deg"] < 0.1, r
    def delta(ob, pb):  # world rotation change from rest
        q = lambda mt: mt.to_3x3().normalized().to_quaternion()  # noqa: E731
        return q(ob.matrix_world @ pb.matrix) @ q(ob.matrix_world @ pb.bone.matrix_local).inverted()
    moved = 0
    for f in (1, 7, 10, 15, 20):  # every bone turns by the same world rotation as its source
        sc.frame_set(f)
        for canon, mx in MIXAMO.items():
            sb, tb = src.pose.bones["mixamorig:" + mx], tgt.pose.bones["DEF-" + canon.replace("upperarm", "upper_arm")]
            ds, dt = delta(src, sb), delta(tgt, tb)
            a = ds.rotation_difference(dt).angle
            a = min(a, 2 * m.pi - a)  # q and -q are the same rotation
            assert m.degrees(a) < 0.5, (f, canon, m.degrees(a))
            moved += ds.angle > 0.1
    assert moved > 20  # the clip actually moves several bones (incl. children of rotated parents)
    sh = src.matrix_world @ src.pose.bones["mixamorig:Hips"].head
    th = tgt.matrix_world @ tgt.pose.bones["DEF-hips"].head
    assert abs(th.x - sh.x * 1.15) < 1e-3  # hips travel scaled by the hips-height ratio
    assert tgt.animation_data.action.name == "GAME_RIG|Walk" and tgt.animation_data.action.use_fake_user


def test_loop_check_pops_fix_and_root_motion():
    _body, arm = fx.simple_character()
    sc = bpy.context.scene
    chest, spine = arm.pose.bones["chest"], arm.pose.bones["spine"]
    chest.rotation_mode = "XYZ"
    for f, rx, y in ((1, 0.0, 0.0), (12, 0.5, 0.5), (24, 0.1, 1.0)):  # ends 0.1 rad off; hips travel 1 m
        chest.rotation_euler = (rx, 0, 0)
        chest.keyframe_insert("rotation_euler", frame=f)
        spine.location = (y, 0, 0)  # the upright spine's local X lies along the ground
        spine.keyframe_insert("location", frame=f)
    lc = skill_module("blender-animation", "loop_check")
    r = lc.run(object="CharRig")
    assert not r["loops"] and {p["bone"] for p in r["pops"]} >= {"chest", "spine"}, r
    r = lc.run(object="CharRig", root_motion="spine")
    assert not r["loops"] and r["pops"][0]["bone"] == "chest" and abs(r["pops"][0]["rot_deg"] - 5.73) < 0.05, r
    r = lc.run(object="CharRig", root_motion="spine", fix=True)
    assert r["loops"] and r["fixed_curves"] >= 3, r
    sc.frame_set(24)
    assert abs(spine.location.x - 1.0) < 1e-6  # root travel kept
