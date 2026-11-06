"""Validate a skeleton + its skinned meshes for animation/engine export; optional safe fixes.

Skeleton: applied transforms, single root at origin, zero-length bones, L/R pairs + mirrored
roll, deform count, constraints on deform bones (need baking), profile naming (roblox R15,
unity humanoid, unreal mannequin).
Skin: unweighted verts, >N influences, non-normalized, weights on non-deform/root bones,
groups without bones, L/R weight asymmetry.
Usage:
  blender -b f.blend -P rig_check.py -- --armature RIG [--meshes Body] [--profile game|roblox|unity|unreal]
      [--fix] [--limit 4] [--save out.blend]
  MCP: import rig_check; result = rig_check.run(armature="GAME_rig", profile="unity")
"""
import os
import re
import sys

import bpy
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

R15 = ["LowerTorso", "UpperTorso", "Head", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm",
       "RightLowerArm", "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg",
       "RightLowerLeg", "RightFoot"]
# Unity Humanoid required bones -> name patterns commonly seen (Rigify/Mixamo/UE/Blender)
HUMANOID = {
    "Hips": r"hips|pelvis$|^spine$|root_?hips", "Spine": r"spine(\.001|_01|1)?$|^spine$",
    "Head": r"head$", "LeftUpperLeg": r"(thigh|upleg|upperleg|upper_leg)[._]?l|left.?(up|upper).?leg",
    "LeftLowerLeg": r"(shin|calf|^leg|lowerleg|lower_leg)[._]?l|left.?(lower)?leg$",
    "LeftFoot": r"foot[._]?l|left.?foot", "RightUpperLeg": r"(thigh|upleg|upperleg|upper_leg)[._]?r|right.?(up|upper).?leg",
    "RightLowerLeg": r"(shin|calf|lowerleg|lower_leg)[._]?r|right.?(lower)?leg$",
    "RightFoot": r"foot[._]?r|right.?foot", "LeftUpperArm": r"(upper_?arm|upperarm|^arm)[._]?l|left.?arm",
    "LeftLowerArm": r"(forearm|lowerarm|lower_arm)[._]?l|left.?fore.?arm", "LeftHand": r"hand[._]?l|left.?hand",
    "RightUpperArm": r"(upper_?arm|upperarm|^arm)[._]?r|right.?arm",
    "RightLowerArm": r"(forearm|lowerarm|lower_arm)[._]?r|right.?fore.?arm", "RightHand": r"hand[._]?r|right.?hand",
}
UE = ["root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head", "clavicle_l", "upperarm_l",
      "lowerarm_l", "hand_l", "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r", "thigh_l", "calf_l",
      "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r"]


def _mirror(name):
    for a, b in ((".L", ".R"), ("_L", "_R"), (".l", ".r"), ("_l", "_r"), ("Left", "Right"), ("left", "right")):
        if a in name:
            return name.replace(a, b)
        if b in name:
            return name.replace(b, a)
    return None


def run(armature=None, meshes=None, profile="game", fix=False, limit=4, **_):
    bx.object_mode()
    arm = bpy.data.objects[armature]
    bones = arm.data.bones
    errors, warnings = [], []
    if any(abs(s - 1) > 1e-4 for s in arm.scale) or any(abs(r) > 1e-4 for r in arm.rotation_euler):
        errors.append(f"armature object transform not applied (scale {tuple(arm.scale)}, rot {tuple(arm.rotation_euler)})")
    roots = [b for b in bones if b.parent is None]
    deform = [b for b in bones if b.use_deform]
    if len([b for b in roots if b.use_deform or b.children]) > 1:
        warnings.append(f"{len(roots)} root bones {[b.name for b in roots][:5]} - engines expect one hierarchy root")
    if roots and (arm.matrix_world @ roots[0].head_local).length > 1e-3:
        warnings.append(f"root bone '{roots[0].name}' not at world origin")
    zero = [b.name for b in bones if b.length < 1e-5]
    if zero:
        errors.append(f"zero-length bones: {zero[:10]}")
    unpaired, roll_bad = [], []
    for b in bones:
        m = _mirror(b.name)
        if m and m != b.name:
            if m not in bones:
                unpaired.append(b.name)
    if unpaired:
        warnings.append(f"L/R bones without mirror partner: {unpaired[:10]}")
    # mirrored roll check in edit mode data (z-axis of mirrored bones should mirror)
    for b in bones:
        m = _mirror(b.name)
        if m and m in bones and b.name < m:
            za, zb = b.z_axis, bones[m].z_axis
            if abs(za.x + zb.x) > 0.05 or abs(za.y - zb.y) > 0.05 or abs(za.z - zb.z) > 0.05:
                roll_bad.append(b.name)
    if roll_bad:
        warnings.append(f"asymmetric bone roll vs mirror: {roll_bad[:10]} (recalc roll / symmetrize)")
    constrained = [pb.name for pb in arm.pose.bones if pb.constraints and arm.data.bones[pb.name].use_deform]
    if constrained:
        warnings.append(f"{len(constrained)} deform bones have constraints - bake animation before export")
    names = [b.name for b in deform]
    prof = {}
    if profile == "roblox":
        missing = [n for n in R15 if n not in bones]
        prof["r15_missing"] = missing
        if missing:
            errors.append(f"R15 bones missing: {missing}")
    elif profile == "unity":
        mapped = {k: next((n for n in names if re.search(p, n, re.I)), None) for k, p in HUMANOID.items()}
        prof["humanoid_map"] = mapped
        miss = [k for k, v in mapped.items() if v is None]
        if miss:
            warnings.append(f"Humanoid auto-map may fail for: {miss} (map manually in Unity Avatar)")
    elif profile == "unreal":
        missing = [n for n in UE if n not in bones]
        prof["mannequin_missing"] = missing
        if missing:
            warnings.append(f"{len(missing)} UE mannequin names missing - IK Retargeter needs manual chains")
    if len(deform) > 300:
        warnings.append(f"{len(deform)} deform bones - heavy for games")

    skin = {}
    obs = bx.objects(meshes) if meshes else [o for o in bpy.data.objects if o.type == "MESH" and any(
        m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]
    deform_names = {b.name for b in deform}
    root_names = {b.name for b in roots}
    for ob in obs:
        if fix:
            from bind_mesh import cleanup
            cleanup(ob, limit=limit, clean=0.001)
            for g in [g for g in ob.vertex_groups if g.name not in bones]:
                ob.vertex_groups.remove(g)
        gi = {g.index: g.name for g in ob.vertex_groups}
        unw = over = unnorm = on_root = on_nondeform = 0
        for v in ob.data.vertices:
            ws = [(gi.get(g.group), g.weight) for g in v.groups if g.weight > 1e-4]
            dws = [w for n, w in ws if n in deform_names]
            unw += not dws
            over += len(dws) > limit
            unnorm += bool(dws) and abs(sum(dws) - 1) > 0.01
            on_root += any(n in root_names for n, _ in ws)
            on_nondeform += any(n in bones and n not in deform_names for n, _ in ws)
        orphan_groups = [g.name for g in ob.vertex_groups if g.name not in bones]
        empty_deform = [n for n in deform_names if n not in ob.vertex_groups]
        # symmetry: weight of X at v vs mirrored group at mirrored vertex
        asym = 0
        kd = KDTree(len(ob.data.vertices))
        for v in ob.data.vertices:
            kd.insert(v.co, v.index)
        kd.balance()
        verts = ob.data.vertices
        for v in verts[:: max(1, len(verts) // 2000)]:
            co = v.co.copy()
            co.x = -co.x
            _, j, d = kd.find(co)
            if j is None or d > 1e-3 or v.co.x < 1e-4:
                continue
            a = {gi.get(g.group): g.weight for g in v.groups}
            b = {gi.get(g.group): g.weight for g in verts[j].groups}
            for n, w in a.items():
                m = _mirror(n) if n else None
                if m and abs(w - b.get(m, 0)) > 0.1:
                    asym += 1
                    break
        s = {"verts": len(verts), "unweighted": unw, f"over_{limit}": over, "not_normalized": unnorm,
             "weights_on_root": on_root, "weights_on_nondeform": on_nondeform,
             "groups_without_bone": orphan_groups[:10], "asymmetric_verts_sampled": asym,
             "deform_bones_without_group": len(empty_deform)}
        skin[ob.name] = s
        if unw:
            errors.append(f"{ob.name}: {unw} unweighted verts (they won't move)")
        if over:
            errors.append(f"{ob.name}: {over} verts > {limit} influences")
        if unnorm:
            warnings.append(f"{ob.name}: {unnorm} verts with weights not summing to 1")
        if on_root and profile == "roblox":
            errors.append(f"{ob.name}: {on_root} verts weighted to root (Roblox forbids)")
        if orphan_groups:
            warnings.append(f"{ob.name}: vertex groups without bones {orphan_groups[:5]}")
        if asym:
            warnings.append(f"{ob.name}: ~{asym} sampled verts with asymmetric L/R weights (mirror weights?)")
    return {"ok": True, "pass": not errors, "errors": errors, "warnings": warnings,
            "bones": len(bones), "deform_bones": len(deform), "profile": prof, "skin": skin, "fixed": fix}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--armature", required=True)
    p.add_argument("--meshes", nargs="*", default=None)
    p.add_argument("--profile", default="game", choices=["game", "roblox", "unity", "unreal"])
    p.add_argument("--fix", action="store_true")
    p.add_argument("--limit", type=int, default=4)
    p.add_argument("--save", default=None)
    bx.cli(run, p)
