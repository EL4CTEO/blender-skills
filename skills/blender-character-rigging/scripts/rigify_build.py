"""Rigify pipeline: add + fit metarig, generate control rig, build an engine-ready game skeleton.

Steps (combine freely):
  --add TYPE      add metarig (basic_human | human | basic_quadruped | horse | wolf | cat | bird | shark)
  --fit MESH      scale/center the metarig to the mesh height (joint placement is still yours)
  --no-face       remove the face rig from 'human' (games: use shape keys or a light face rig)
  --generate      generate the control rig from --metarig (or the one just added)
  --game-skeleton build GAME_<rig>: clean hierarchy of root + DEF bones (prefix stripped),
                  Copy Transforms to the control rig; re-targets skinned meshes to it.
Usage:
  blender -b f.blend -P rigify_build.py -- --add basic_human --fit Body --generate --game-skeleton [--save out.blend]
  MCP: import rigify_build as r; print(r.run(add="basic_human", fit="Body", generate=True))
After --add/--fit: place joints (edit bones) to the mesh, check with look (xray), then --generate.
"""
import os
import sys

import addon_utils
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

ADD_OPS = {"basic_human": "armature_basic_human_metarig_add", "human": "armature_human_metarig_add",
           "basic_quadruped": "armature_basic_quadruped_metarig_add", "horse": "armature_horse_metarig_add",
           "wolf": "armature_wolf_metarig_add", "cat": "armature_cat_metarig_add",
           "bird": "armature_bird_metarig_add", "shark": "armature_shark_metarig_add"}


def _ensure_rigify():
    if "rigify" not in bpy.context.preferences.addons:
        addon_utils.enable("rigify", default_set=True, persistent=False)


def _bounds(ob):
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _fit(meta, mesh):
    lo, hi = _bounds(mesh)
    ml, mh = _bounds(meta)
    s = (hi.z - lo.z) / max(mh.z - ml.z, 1e-6)
    meta.scale = (s, s, s)
    bpy.context.view_layer.update()
    ml, mh = _bounds(meta)
    meta.location += Vector(((lo.x + hi.x) / 2 - (ml.x + mh.x) / 2, (lo.y + hi.y) / 2 - (ml.y + mh.y) / 2,
                             lo.z - ml.z))
    bx.select_only([meta])
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return round(s, 4)


def _remove_face(meta):
    bx.select_only([meta])
    bpy.ops.object.mode_set(mode="EDIT")
    eb = meta.data.edit_bones
    face = eb.get("face")
    n = 0
    if face:
        for b in [face] + list(face.children_recursive):
            eb.remove(b)
            n += 1
    bpy.ops.object.mode_set(mode="OBJECT")
    return n


def _generate(meta):
    _ensure_rigify()
    bx.select_only([meta])
    res = bpy.ops.pose.rigify_generate()
    if res != {"FINISHED"}:
        raise RuntimeError("rigify_generate failed (check metarig bone types / Rigify messages)")
    rig = meta.data.rigify_target_rig
    return rig


def game_skeleton(rig, strip=True):
    """root + DEF bones with DEF-only parenting, constrained to the control rig."""
    name = f"GAME_{rig.name}"
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old)
    arm = bpy.data.armatures.new(name)
    gs = bpy.data.objects.new(name, arm)
    for c in rig.users_collection:
        c.objects.link(gs)
    gs.matrix_world = rig.matrix_world
    defs = [b for b in rig.data.bones if b.use_deform]
    names = {b.name for b in defs}

    def deform_parent(b):
        p = b.parent
        while p:
            if p.name in names and p.name != b.name:
                return p.name
            cand = "DEF-" + p.name[4:] if p.name.startswith(("ORG-", "MCH-")) else None
            if cand in names and cand != b.name:
                return cand
            p = p.parent
        return None

    new = (lambda n: n[4:] if strip and n.startswith("DEF-") else n)
    bx.select_only([gs])
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    root = eb.new("root")
    root.head, root.tail = (0, 0, 0), (0, 0.1 * max(rig.dimensions.z, 0.1), 0)
    root.use_deform = False
    for b in defs:
        e = eb.new(new(b.name))
        e.head, e.tail = b.head_local, b.tail_local
        e.matrix = b.matrix_local
        e.use_deform = True
    for b in defs:
        e = eb[new(b.name)]
        par = deform_parent(b)
        e.parent = eb[new(par)] if par else root
        e.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for b in defs:
        c = gs.pose.bones[new(b.name)].constraints.new("COPY_TRANSFORMS")
        c.target, c.subtarget = rig, b.name
    rc = gs.pose.bones["root"].constraints.new("COPY_TRANSFORMS")
    rc.target, rc.subtarget = rig, "root" if "root" in rig.pose.bones else ""
    # re-target skinned meshes
    moved = []
    for ob in bpy.data.objects:
        for m in ob.modifiers:
            if m.type == "ARMATURE" and m.object == rig:
                m.object = gs
                if strip:
                    for g in ob.vertex_groups:
                        if g.name.startswith("DEF-"):
                            g.name = g.name[4:]
                if ob.parent == rig:
                    mw = ob.matrix_world.copy()
                    ob.parent = gs
                    ob.matrix_world = mw
                moved.append(ob.name)
    return gs, len(defs), moved


def run(add=None, metarig=None, fit=None, no_face=False, generate=False, game_skel=False,
        rig=None, strip_prefix=True, **_):
    bx.object_mode()
    _ensure_rigify()
    out = {"ok": True}
    meta = bpy.data.objects[metarig] if metarig else None
    if add:
        getattr(bpy.ops.object, ADD_OPS[add])()
        meta = bpy.context.view_layer.objects.active
        meta.name = f"META_{fit}" if fit else "metarig"
        out["metarig"] = meta.name
    if fit and meta:
        out["fit_scale"] = _fit(meta, bpy.data.objects[fit])
    if no_face and meta:
        out["face_bones_removed"] = _remove_face(meta)
    if generate:
        if meta is None:
            raise ValueError("--generate needs --metarig or --add")
        r = _generate(meta)
        r.name = f"RIG_{fit}" if fit else r.name
        meta.hide_set(True)
        out["rig"] = r.name
        out["bones"] = len(r.data.bones)
        out["deform_bones"] = sum(b.use_deform for b in r.data.bones)
        rig = r.name
    if game_skel:
        gs, n, moved = game_skeleton(bpy.data.objects[rig], strip_prefix)
        out["game_skeleton"] = {"name": gs.name, "bones": n + 1, "retargeted_meshes": moved}
    return out


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--add", choices=list(ADD_OPS), default=None)
    p.add_argument("--metarig", default=None)
    p.add_argument("--fit", default=None, help="mesh to fit the metarig to")
    p.add_argument("--no-face", action="store_true")
    p.add_argument("--generate", action="store_true")
    p.add_argument("--game-skeleton", dest="game_skel", action="store_true")
    p.add_argument("--rig", default=None, help="existing generated rig (for --game-skeleton)")
    p.add_argument("--keep-prefix", dest="strip_prefix", action="store_false")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
