"""Bake animation clips from a control rig onto an export skeleton (visual keying), one action per
clip, optional root motion, clean curves, NLA strips for exporters; or list clips.

Typical: Rigify RIG_Body (animated) -> GAME_RIG_Body (from rigify_build --game-skeleton).
After baking, the target's constraints are MUTED so exporters play the baked actions
(--follow unmutes them to drive the target from the control rig again).
Usage:
  blender -b f.blend -P bake_action.py -- --list
  blender -b f.blend -P bake_action.py -- --source RIG_Body --target GAME_RIG_Body
      [--actions Walk Run] [--root-motion xy|xyz] [--hips spine] [--step 1] [--no-clean] [--save out.blend]
  blender -b f.blend -P bake_action.py -- --target GAME_RIG_Body --follow
  MCP: import bake_action; result = bake_action.run(source="RIG_Body", target="GAME_RIG_Body", root_motion="xy")
Self-bake (constraints/IK/drivers -> keys on the same rig): --source X --target X.
"""
import os
import sys

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def list_actions():
    out = []
    for a in bpy.data.actions:
        cbs = [cb for layer in a.layers for strip in layer.strips for cb in strip.channelbags]
        out.append({"name": a.name, "range": [round(a.frame_range[0], 2), round(a.frame_range[1], 2)],
                    "slots": [f"{s.target_id_type}:{s.name_display}" for s in a.slots],
                    "fcurves": sum(len(cb.fcurves) for cb in cbs), "users": a.users,
                    "fake_user": a.use_fake_user, "cyclic": a.use_cyclic})
    return out


def _assign(ob, act):
    ob.animation_data_create()
    ob.animation_data.action = act
    if ob.animation_data.action_slot is None:
        slot = next(iter(ob.animation_data.action_suitable_slots), None) or act.slots.new(
            id_type="OBJECT", name=ob.name)
        ob.animation_data.action_slot = slot


def _mute(ob, state):
    for pb in ob.pose.bones:
        for c in pb.constraints:
            c.mute = state


def _root_motion(tgt, act, frames, hips, axes):
    root = next((b for b in tgt.pose.bones if b.parent is None), None)
    hp = tgt.pose.bones.get(hips) if hips else None
    if hp is None:  # first child chain bone under root
        hp = next((b for b in root.children), None) if root else None
    if root is None or hp is None or root == hp:
        return "skipped (need root bone with a hips child)"
    _assign(tgt, act)
    sc = bpy.context.scene
    start = None
    samples = []
    for f in frames:
        sc.frame_set(f)
        samples.append((f, hp.matrix.copy()))
    for f, m_h in samples:
        sc.frame_set(f)
        p = m_h.translation.copy()
        start = start or p.copy()
        d = p - start
        delta = Vector((d.x, d.y, d.z if axes == "xyz" else 0.0))
        root.matrix = Matrix.Translation(delta) @ root.bone.matrix_local  # keep rest orientation
        bpy.context.view_layer.update()
        hp.matrix = m_h  # keep hips where they were in armature space
        bpy.context.view_layer.update()
        root.keyframe_insert("location", frame=f)
        hp.keyframe_insert("location", frame=f)
    return f"{root.name} carries {axes} motion from {hp.name}"


def run(source=None, target=None, actions=None, root_motion=None, hips=None, step=1, clean=True,
        follow=False, list=False, **_):  # noqa: A002
    bx.object_mode()
    if list:
        return {"ok": True, "actions": list_actions()}
    tgt = bpy.data.objects[target]
    if follow:
        _mute(tgt, False)
        if tgt.animation_data:
            tgt.animation_data.action = None
        return {"ok": True, "following": True}
    src = bpy.data.objects[source]
    same = src == tgt
    acts = [bpy.data.actions[a] for a in actions] if actions else [
        a for a in bpy.data.actions if any(s.target_id_type == "OBJECT" for s in a.slots)
        and not a.name.startswith(("QA_", f"{tgt.name}|")) and (src.animation_data and (
            a == src.animation_data.action or a.use_fake_user or a.users))]
    if not acts:
        raise ValueError("no actions to bake (assign/fake-user them, or pass --actions)")
    opts = anim_utils.BakeOptions(only_selected=False, do_pose=True, do_object=False, do_visual_keying=True,
                                  do_constraint_clear=same, do_parents_clear=False, do_clean=clean,
                                  do_location=True, do_rotation=True, do_scale=True, do_bbone=False,
                                  do_custom_props=False)
    prev = src.animation_data.action if src.animation_data else None
    baked = []
    tgt.animation_data_create()
    for a in acts:
        _assign(src, a)
        f0, f1 = int(round(a.frame_range[0])), int(round(a.frame_range[1]))
        frames = range(f0, f1 + 1, step)
        _mute(tgt, False) if not same else None
        name = a.name if same else f"{tgt.name}|{a.name}"
        old = bpy.data.actions.get(name)
        if old and old != a:
            bpy.data.actions.remove(old)
        new = a if same else bpy.data.actions.new(name)
        new.use_fake_user = True
        if not same:
            _assign(tgt, new)
        anim_utils.bake_action(tgt, action=new, frames=frames, bake_options=opts)
        rec = {"clip": a.name, "action": new.name, "frames": [f0, f1]}
        if root_motion and not same:
            _mute(tgt, True)
            rec["root_motion"] = _root_motion(tgt, new, frames, hips, root_motion)
        new.use_cyclic = a.use_cyclic
        baked.append(rec)
    if not same:
        _mute(tgt, True)
        # one NLA track per clip (muted) so exporters can find every clip
        ad = tgt.animation_data
        for t in [t for t in ad.nla_tracks if t.name.startswith("CLIP_")]:
            ad.nla_tracks.remove(t)
        for rec in baked:
            act = bpy.data.actions[rec["action"]]
            tr = ad.nla_tracks.new()
            tr.name = f"CLIP_{rec['clip']}"
            st = tr.strips.new(rec["clip"], int(act.frame_range[0]), act)
            tr.mute = True
            st.name = rec["clip"]
        ad.action = bpy.data.actions[baked[0]["action"]]
    if prev is not None:
        _assign(src, prev)
    return {"ok": True, "baked": baked, "target_constraints_muted": not same}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--list", action="store_true")
    p.add_argument("--source", default=None)
    p.add_argument("--target", default=None)
    p.add_argument("--actions", nargs="*", default=None)
    p.add_argument("--root-motion", choices=["xy", "xyz"], default=None)
    p.add_argument("--hips", default=None)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--no-clean", dest="clean", action="store_false")
    p.add_argument("--follow", action="store_true")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
