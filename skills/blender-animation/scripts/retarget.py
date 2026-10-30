"""Retarget an animated skeleton (mocap/BVH/Mixamo/any rig) onto another rig, constraint-free.

Each mapped target bone gets the source bone's world-space rotation *change from rest* applied to its
own rest orientation (so different rolls, axes, object rotation/scale don't matter); the hips also
get the source hips' translation scaled by the hips-height ratio. Keys are written straight into a
new slotted action (quaternions, linear) on the target. Rest poses must match in spirit (T vs A pose
matters most): pose the target's rest to the source's first, or use a source rest-pose frame.
Bone map: auto (Mixamo, Rigify DEF-/ORG-, UE/Unity-style names, BVH) or a JSON {target: source}.
Usage:
  blender -b f.blend -P retarget.py -- --source Mocap --target GAME_RIG [--map auto|map.json]
      [--frames 1 120] [--in-place] [--name Walk] [--save out.blend]
  blender -b f.blend -P retarget.py -- --source Mocap --target GAME_RIG --show-map
  MCP: import retarget; print(retarget.run(source="Armature", target="GAME_RIG", name="Walk"))
"""
import json
import math
import os
import re
import sys

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

CANON = {  # normalized core name -> canonical body part
    "hips": "hips", "pelvis": "hips", "root": None, "neck": "neck", "head": "head",
    "shoulder": "shoulder", "clavicle": "shoulder", "collar": "shoulder",
    "upperarm": "upperarm", "arm": "upperarm", "uparm": "upperarm",
    "forearm": "forearm", "lowerarm": "forearm", "elbow": "forearm",
    "hand": "hand", "wrist": "hand",
    "thigh": "thigh", "upleg": "thigh", "upperleg": "thigh", "hip": "thigh",
    "shin": "shin", "leg": "shin", "calf": "shin", "lowerleg": "shin", "knee": "shin",
    "foot": "foot", "ankle": "foot", "toe": "toe", "toebase": "toe", "toes": "toe", "ball": "toe",
}
SPINE = re.compile(r"^(spine\d*|chest|upperchest|torso|abdomen|back)$")


def _split(name):
    """'mixamorig:LeftUpLeg' -> ('upleg', 'L'); 'DEF-upper_arm.L' -> ('upperarm', 'L')."""
    n = re.sub(r"^(mixamorig\d*:|def[-_]|org[-_]|cc_base_|bip0?1[ _]?|b_|bn_)", "", name.lower())
    side = ""
    for pat, s in ((r"(^left|left$|^l[_.]|[_.]l$|\.l\.|_l_)", "L"), (r"(^right|right$|^r[_.]|[_.]r$|\.r\.|_r_)", "R")):
        if re.search(pat, n):
            side = s
            n = re.sub(pat, "", n)
            break
    n = n.replace("left", "").replace("right", "")
    core = re.sub(r"[^a-z0-9]", "", n)
    core = re.sub(r"0+(\d)", r"\1", core)  # spine.001 -> spine1
    return core, side


def _parts(arm):
    """{(part, side): bone}, plus the spine chain (hips -> neck order)."""
    out, spine = {}, []
    for b in arm.data.bones:
        core, side = _split(b.name)
        if SPINE.match(core):
            spine.append(b)
            continue
        part = CANON.get(core) or CANON.get(re.sub(r"\d+$", "", core))
        if part and (part, side) not in out:
            out[(part, side)] = b.name
    spine.sort(key=lambda b: len(b.parent_recursive))
    return out, [b.name for b in spine]


def auto_map(src, tgt):
    sp, ss = _parts(src)
    tp, ts = _parts(tgt)
    m = {tb: sp[k] for k, tb in tp.items() if k in sp}
    for i, tb in enumerate(ts):  # spine chains of different lengths map proportionally
        if ss:
            m[tb] = ss[round(i * (len(ss) - 1) / max(1, len(ts) - 1))]
    sn = {_split(b.name): b.name for b in src.data.bones}
    for b in tgt.data.bones:  # same normalized name (fingers, extras) maps directly
        if b.name not in m and _split(b.name) in sn:
            m[b.name] = sn[_split(b.name)]
    hips = tp.get(("hips", ""))
    return m, hips


def _rot(mat):
    return mat.to_3x3().normalized().to_quaternion()


def run(source=None, target=None, map="auto", frames=None, in_place=False, name=None, show_map=False, **_):
    bx.object_mode()
    if not source or not target:
        raise ValueError("--source and --target are required")
    src, tgt = bpy.data.objects[source], bpy.data.objects[target]
    if map == "auto":
        bmap, hips = auto_map(src, tgt)
    else:
        with open(bpy.path.abspath(map), encoding="utf-8") as f:
            bmap = json.load(f)
        hips = auto_map(src, tgt)[1]
        hips = hips if hips in bmap else None
    bmap = {t: s for t, s in bmap.items() if t in tgt.data.bones and s in src.data.bones}
    key_parts = ("hips", "upperarm", "forearm", "thigh", "shin", "head")
    tparts = _parts(tgt)[0]
    missing = sorted(f"{p}{'.' + sd if sd else ''}" for (p, sd), b in tparts.items() if p in key_parts and b not in bmap)
    if show_map:
        return {"ok": True, "map": bmap, "hips": hips, "unmapped_key_parts": missing}
    if not bmap:
        raise ValueError("no bones mapped: pass --map map.json {target_bone: source_bone}")
    act_src = src.animation_data.action if src.animation_data else None
    if frames:
        f0, f1 = int(frames[0]), int(frames[1])
    elif act_src:
        f0, f1 = (int(round(v)) for v in act_src.frame_range)
    else:
        raise ValueError("source has no action: pass --frames")
    tw_rot = _rot(tgt.matrix_world)
    order = sorted(tgt.data.bones, key=lambda b: len(b.parent_recursive))  # parents first
    rest_rel = {b.name: (b.parent.matrix_local.inverted() @ b.matrix_local if b.parent else b.matrix_local.copy())
                for b in order}
    t_rest_w = {b: _rot(tgt.matrix_world @ tgt.data.bones[b].matrix_local) for b in bmap}
    sc = bpy.context.scene
    sc.frame_set(f0)
    s_rest_w = {s: _rot(src.matrix_world @ src.data.bones[s].matrix_local) for s in bmap.values()}
    ratio = 1.0
    if hips:
        sh = (src.matrix_world @ src.data.bones[bmap[hips]].head_local).z
        th = (tgt.matrix_world @ tgt.data.bones[hips].head_local).z
        ratio = th / sh if abs(sh) > 1e-6 else 1.0
        s_hips_rest = src.matrix_world @ src.data.bones[bmap[hips]].head_local
        t_hips_rest = tgt.matrix_world @ tgt.data.bones[hips].head_local
    keys = {b: [] for b in bmap}
    locs = []
    err = 0.0
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        pose = {}
        for b in order:
            M_parent = pose.get(b.parent.name, Matrix.Identity(4)) if b.parent else Matrix.Identity(4)
            base = M_parent @ rest_rel[b.name]
            if b.name not in bmap:
                pose[b.name] = base
                continue
            s = bmap[b.name]
            sw = _rot(src.matrix_world @ src.pose.bones[s].matrix)
            dw = sw @ s_rest_w[s].inverted() @ t_rest_w[b.name]  # source's change from rest, on our rest
            da = tw_rot.inverted() @ dw
            lq = _rot(base).inverted() @ da
            prev = keys[b.name][-1][1] if keys[b.name] else None
            if prev is not None and lq.dot(prev) < 0:
                lq.negate()  # keep quaternions continuous for linear interpolation
            loc = Vector()
            if b.name == hips and not in_place:
                hs = src.matrix_world @ src.pose.bones[s].head
                want_w = t_hips_rest + (hs - s_hips_rest) * ratio
                want_a = tgt.matrix_world.inverted() @ want_w
                loc = base.to_3x3().inverted() @ (want_a - base.translation)
                locs.append((f, loc.copy()))
            pose[b.name] = base @ Matrix.Translation(loc) @ lq.to_matrix().to_4x4()
            keys[b.name].append((f, lq))
            got = tw_rot @ _rot(pose[b.name])
            a = (got @ t_rest_w[b.name].inverted()).rotation_difference(sw @ s_rest_w[s].inverted()).angle
            err = max(err, math.degrees(min(a, 2 * math.pi - a)))  # q and -q are the same rotation
    name = name or (act_src.name if act_src else "Retarget")
    act = bpy.data.actions.new(f"{tgt.name}|{name}")
    act.use_fake_user = True
    tgt.animation_data_create()
    tgt.animation_data.action = act
    slot = tgt.animation_data.action_slot or act.slots.new(id_type="OBJECT", name=tgt.name)
    tgt.animation_data.action_slot = slot
    cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)

    def write(path, idx, group, pts):
        fc = cb.fcurves.ensure(path, index=idx, group_name=group)
        fc.keyframe_points.add(len(pts))
        fc.keyframe_points.foreach_set("co", [v for p in pts for v in p])
        fc.keyframe_points.foreach_set("interpolation", [bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value] * len(pts))
        fc.update()
    for b, ks in keys.items():
        tgt.pose.bones[b].rotation_mode = "QUATERNION"
        for i in range(4):
            write(f'pose.bones["{b}"].rotation_quaternion', i, b, [(f, q[i]) for f, q in ks])
    if locs:
        for i in range(3):
            write(f'pose.bones["{hips}"].location', i, hips, [(f, v[i]) for f, v in locs])
    sc.frame_set(f0)
    return {"ok": True, "action": act.name, "frames": [f0, f1], "mapped": len(bmap), "hips": hips,
            "hips_scale": round(ratio, 4), "unmapped_key_parts": missing, "max_error_deg": round(err, 3)}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--map", default="auto", help="auto or JSON file {target_bone: source_bone}")
    p.add_argument("--frames", type=int, nargs=2, default=None)
    p.add_argument("--in-place", action="store_true", help="no hips translation")
    p.add_argument("--name", default=None)
    p.add_argument("--show-map", action="store_true")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
