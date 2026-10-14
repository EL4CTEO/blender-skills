"""Create a QA_Stress action with extreme poses to review deformation (elbows, knees, shoulders, hips, spine, neck).

Works on Rigify control rigs (poses FK controls, switches IK->FK) and plain/game skeletons
(Rigify DEF/game names, Mixamo, UE, Roblox R15). Character must face -Y, Z up.
Frames: 1 rest | 10 arms raised | 20 elbows 130 + arms forward | 30 hip flex + knee 120 (L)
        | 40 crouch | 50 spine twist + head turn.
Usage:
  blender -b f.blend -P stress_poses.py -- --armature RIG [--save out.blend]
  then: MCP look(mode="frames", frames=[1,10,20,30,40,50]) or render the frames; remove with --clear.
  MCP: import stress_poses; print(stress_poses.run(armature="RIG"))
"""
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

ROLES = {  # role -> regex (searched in order of preference: fk controls first)
    "upper_arm": r"^(upper_arm_fk|upper_arm|upperarm|arm|leftarm|rightarm|(left|right)upperarm|mixamorig:(left|right)arm)",
    "forearm": r"^(forearm_fk|forearm|lowerarm|(left|right)lowerarm|(left|right)forearm|mixamorig:(left|right)forearm)",
    "thigh": r"^(thigh_fk|thigh|upperleg|upleg|(left|right)upperleg|(left|right)upleg|mixamorig:(left|right)upleg)",
    "shin": r"^(shin_fk|shin|calf|lowerleg|leg|(left|right)lowerleg|(left|right)leg|mixamorig:(left|right)leg)",
    "spine": r"^(torso|spine_fk\.001|spine\.002|spine_02|spine2|uppertorso|mixamorig:spine1)$",
    "head": r"^(head|mixamorig:head)$",
}


def _side(name):
    n = name.lower()
    if re.search(r"(\.l$|_l$|\.l\.|left)", n):
        return "L"
    if re.search(r"(\.r$|_r$|\.r\.|right)", n):
        return "R"
    return None


def _find(arm, role, side=None):
    pat = re.compile(ROLES[role], re.I)
    cands = []
    for pb in arm.pose.bones:
        base = re.sub(r"^(def-|org-|mch-)", "", pb.name, flags=re.I)
        base = re.sub(r"[._]?(l|r)(\.\d+)?$", "", base, flags=re.I) if role not in ("spine", "head") else base
        if pat.match(base) and (side is None or _side(pb.name) == side):
            if pb.name.lower().startswith(("mch-", "org-")):
                continue
            cands.append(pb)
    cands.sort(key=lambda p: (0 if "_fk" in p.name else 1, p.name.lower().startswith("def-"), len(p.name)))
    return cands[0] if cands else None


def _rotate(arm, pb, axis, deg):
    """Rotate a pose bone about a WORLD axis through its head (rig-agnostic: ignores bone roll)."""
    bpy.context.view_layer.update()
    head = pb.head.copy()
    R = Matrix.Rotation(math.radians(deg), 4, Vector(axis))
    pb.matrix = Matrix.Translation(head) @ R @ Matrix.Translation(-head) @ pb.matrix
    bpy.context.view_layer.update()


POSES = {  # frame -> list of (role, side, world axis, degrees); L side is +X when facing -Y
    1: [],
    10: [("upper_arm", "L", (0, 1, 0), -70), ("upper_arm", "R", (0, 1, 0), 70)],
    20: [("upper_arm", "L", (0, 0, 1), -60), ("upper_arm", "R", (0, 0, 1), 60),
         ("forearm", "L", (0, 0, 1), -130), ("forearm", "R", (0, 0, 1), 130)],
    30: [("thigh", "L", (1, 0, 0), -90), ("shin", "L", (1, 0, 0), 120)],
    40: [("thigh", "L", (1, 0, 0), -100), ("thigh", "R", (1, 0, 0), -100),
         ("shin", "L", (1, 0, 0), 130), ("shin", "R", (1, 0, 0), 130)],
    50: [("spine", None, (0, 0, 1), 45), ("head", None, (0, 0, 1), 70)],
}


def run(armature=None, clear=False, **_):
    bx.object_mode()
    arm = bpy.data.objects[armature]
    act = bpy.data.actions.get("QA_Stress")
    if clear:
        if act:
            bpy.data.actions.remove(act)
        for pb in arm.pose.bones:
            pb.matrix_basis = Matrix()
        return {"ok": True, "cleared": True}
    for pb in arm.pose.bones:  # Rigify: switch limbs to FK so FK controls drive the pose
        for k in ("IK_FK",):
            if k in pb.keys():
                pb[k] = 1.0
    if act:
        bpy.data.actions.remove(act)
    arm.animation_data_create()
    act = bpy.data.actions.new("QA_Stress")
    arm.animation_data.action = act
    found = {}
    bx.select_only([arm])
    bpy.ops.object.mode_set(mode="POSE")
    try:
        for frame, ops in POSES.items():
            bpy.context.scene.frame_set(frame)
            for pb in arm.pose.bones:
                pb.matrix_basis = Matrix()
            for role, side, axis, deg in ops:
                pb = _find(arm, role, side)
                key = f"{role}.{side}" if side else role
                found[key] = pb.name if pb else None
                if pb:
                    _rotate(arm, pb, axis, deg)
            for pb in arm.pose.bones:
                for path in ("location", "rotation_quaternion", "rotation_euler", "scale"):
                    pb.keyframe_insert(path, frame=frame)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 50
    missing = [k for k, v in found.items() if v is None]
    return {"ok": True, "action": act.name, "frames": list(POSES), "bones_used": found,
            "missing_roles": missing}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--armature", required=True)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
