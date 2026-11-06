"""Shape-key toolkit for faces: create ARKit-52 / viseme sets, split symmetric keys L/R,
mirror keys, report sculpt status, and wire driver controls.

Usage:
  blender -b f.blend -P shapekeys.py -- --mesh Head --create arkit|visemes
  blender -b f.blend -P shapekeys.py -- --mesh Head --split eyeBlink [--falloff 0.02] [--style arkit|dot]
  blender -b f.blend -P shapekeys.py -- --mesh Head --mirror browDownLeft
  blender -b f.blend -P shapekeys.py -- --mesh Head --report
  blender -b f.blend -P shapekeys.py -- --mesh Head --drivers FaceCtrl   (custom props 0..1 per key)
  MCP: import shapekeys; result = shapekeys.run(mesh="Head", create="arkit")
"""
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

ARKIT = [
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft",
    "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight",
    "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthFunnel", "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft",
    "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower", "mouthRollUpper",
    "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft",
    "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight",
    "tongueOut",
]
VISEMES = ["viseme_sil", "viseme_PP", "viseme_FF", "viseme_TH", "viseme_DD", "viseme_kk", "viseme_CH",
           "viseme_SS", "viseme_nn", "viseme_RR", "viseme_aa", "viseme_E", "viseme_I", "viseme_O", "viseme_U"]


def _keys(ob):
    if ob.data.shape_keys is None:
        ob.shape_key_add(name="Basis", from_mix=False)
    return ob.data.shape_keys.key_blocks


def _co(kb):
    a = np.empty(len(kb.data) * 3, dtype=np.float32)
    kb.data.foreach_get("co", a)
    return a.reshape(-1, 3)


def run(mesh=None, create=None, split=None, mirror=None, report=False, drivers=None, falloff=0.02,
        style="arkit", **_):
    bx.object_mode()
    ob = bpy.data.objects[mesh]
    kbs = _keys(ob)
    out = {"ok": True, "mesh": ob.name}
    if create:
        names = ARKIT if create == "arkit" else VISEMES
        made = [n for n in names if n not in kbs]
        for n in made:
            ob.shape_key_add(name=n, from_mix=False)
        out["created"] = len(made)
    if split:
        src = kbs[split]
        basis = _co(kbs[0])
        delta = _co(src) - basis
        x = basis[:, 0]
        w_left = np.clip(0.5 + x / (2 * max(falloff, 1e-6)), 0, 1)  # character left = +X
        names = ((f"{split}Left", f"{split}Right") if style == "arkit" else (f"{split}.L", f"{split}.R"))
        for nm, w in zip(names, (w_left, 1 - w_left)):
            kb = kbs.get(nm) or ob.shape_key_add(name=nm, from_mix=False)
            kb.data.foreach_set("co", (basis + delta * w[:, None]).ravel())
        out["split"] = list(names)
    if mirror:
        src = kbs[mirror]
        target = mirror.replace("Left", "Right") if "Left" in mirror else mirror.replace("Right", "Left") \
            if "Right" in mirror else mirror.replace(".L", ".R") if ".L" in mirror else mirror.replace(".R", ".L")
        if target == mirror:
            raise ValueError("key name has no Left/Right/.L/.R side")
        old = kbs.get(target)
        if old:
            ob.shape_key_remove(old)
        ob.active_shape_key_index = list(kbs).index(src)
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.shape_key_add(from_mix=False)
        new = ob.active_shape_key
        new.data.foreach_set("co", _co(src).ravel())
        new.name = target
        with bpy.context.temp_override(object=ob, active_object=ob):
            res = bpy.ops.object.shape_key_mirror(use_topology=False)
        out["mirrored"] = {"from": mirror, "to": target, "op": list(res)}
    if drivers:
        ctrl = bpy.data.objects.get(drivers) or bpy.data.objects.new(drivers, None)
        if ctrl.name not in bpy.context.scene.objects:
            bpy.context.scene.collection.objects.link(ctrl)
        n = 0
        for kb in list(kbs)[1:]:
            ctrl[kb.name] = 0.0
            ui = ctrl.id_properties_ui(kb.name)
            ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0)
            kb.driver_remove("value")
            fc = kb.driver_add("value")
            d = fc.driver
            d.type = "AVERAGE"
            v = d.variables.new()
            v.type = "SINGLE_PROP"
            v.targets[0].id = ctrl
            v.targets[0].data_path = f'["{kb.name}"]'
            n += 1
        out["drivers"] = {"controller": ctrl.name, "count": n}
    if report or not any((create, split, mirror, drivers)):
        basis = _co(kbs[0])
        rows = {}
        for kb in list(kbs)[1:]:
            d = np.linalg.norm(_co(kb) - basis, axis=1)
            rows[kb.name] = round(float(d.max()), 5)
        out["keys"] = len(kbs) - 1
        out["unsculpted"] = [k for k, v in rows.items() if v < 1e-6]
        out["max_offset"] = {k: v for k, v in rows.items() if v >= 1e-6}
        if create == "arkit" or any(k in kbs for k in ARKIT):
            out["arkit_missing"] = [n for n in ARKIT if n not in kbs]
    return out


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--mesh", required=True)
    p.add_argument("--create", choices=["arkit", "visemes"], default=None)
    p.add_argument("--split", default=None)
    p.add_argument("--mirror", default=None)
    p.add_argument("--report", action="store_true")
    p.add_argument("--drivers", default=None, help="controller object name")
    p.add_argument("--falloff", type=float, default=0.02, help="blend width across X=0 (m)")
    p.add_argument("--style", choices=["arkit", "dot"], default="arkit")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
