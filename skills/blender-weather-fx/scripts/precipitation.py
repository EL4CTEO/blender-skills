"""Rain, snow, dust, ash or embers as a seamlessly looping Geometry Nodes system (no simulation:
deterministic, headless-safe, any frame renders on its own).

Particles live in a world-fixed box that covers what the camera sees (sampled over the frame
range), fall at real speeds along the wind, stop on --ground objects (raycast) and, for rain,
spawn splash crowns at the impact point. All values stay editable on the ENV_Weather_<type>
object's modifier.
Usage:
  blender -b f.blend -P precipitation.py -- --type rain|snow|dust|ash|embers
      [--intensity light|moderate|heavy|storm] [--density N_per_m3] [--wind X Y]
      [--ground Street Roof ...] [--distance 18] [--loop-frames 96] [--seed 0] [--no-splash]
      [--max-count 400000] [--save out.blend]
  MCP: import precipitation; result = precipitation.run(type="rain", intensity="heavy", ground=["Street"])
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PREFIX = "ENV_Weather_"
# per type: fall speed m/s (terminal velocity), particle size m, sway m, gravity sign,
# target lifetime s, visible density per m3 by intensity (light, moderate, heavy, storm)
TYPES = {
    "rain": dict(speed=7.0, size=0.0012, sway=0.0, sign=-1, life=1.0, density=(5, 15, 40, 80)),
    "snow": dict(speed=1.0, size=0.006, sway=0.25, sign=-1, life=4.0, density=(10, 30, 80, 160)),
    "dust": dict(speed=0.15, size=0.0008, sway=0.6, sign=-1, life=6.0, density=(10, 30, 80, 150)),
    "ash": dict(speed=0.6, size=0.004, sway=0.4, sign=-1, life=4.0, density=(5, 15, 40, 80)),
    "embers": dict(speed=1.5, size=0.004, sway=0.5, sign=1, life=3.0, density=(1, 3, 8, 15)),
}
INTENSITY = {"light": 0, "moderate": 1, "heavy": 2, "storm": 3}


class _T:
    """Minimal node-graph helper: n(type, inputs..., **props) -> node; sockets by enabled name."""

    def __init__(self, nt):
        self.nt = nt

    @staticmethod
    def sock(coll, key):
        if isinstance(key, int):
            return [s for s in coll if s.enabled][key]
        s = next((s for s in coll if s.enabled and (s.name == key or s.identifier == key)), None)
        if s is None:
            raise KeyError(f"{key} not in {[s.name for s in coll if s.enabled]}")
        return s

    def n(self, type_, ins=None, **props):
        node = self.nt.nodes.new(type_)
        for k, v in props.items():
            setattr(node, k, v)
        for k, v in (ins or {}).items():
            s = self.sock(node.inputs, k)
            if isinstance(v, bpy.types.NodeSocket):
                self.nt.links.new(v, s)
            else:
                s.default_value = v
        return node

    def out(self, node, key=0):
        return self.sock(node.outputs, key)

    def math(self, op, a, b=0.0, c=None):
        ins = {0: a, 1: b} if c is None else {0: a, 1: b, 2: c}
        node = self.nt.nodes.new("ShaderNodeMath")
        node.operation = op
        for i, v in ins.items():
            s = node.inputs[i]
            if isinstance(v, bpy.types.NodeSocket):
                self.nt.links.new(v, s)
            else:
                s.default_value = v
        return node.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        node = self.nt.nodes.new("ShaderNodeVectorMath")
        node.operation = op
        for s, v in ((node.inputs[0], a), (node.inputs[1], b), (node.inputs[3], scale)):
            if v is None:
                continue
            if isinstance(v, bpy.types.NodeSocket):
                self.nt.links.new(v, s)
            else:
                s.default_value = v
        return node.outputs["Value" if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else "Vector"]


def _iface(nt, name, kind, default=None, io="INPUT", **kw):
    s = nt.interface.new_socket(name, in_out=io, socket_type=f"NodeSocket{kind}")
    if default is not None:
        s.default_value = default
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def build_tree(name, kind):
    nt = bpy.data.node_groups.get(name) or bpy.data.node_groups.new(name, "GeometryNodeTree")
    nt.nodes.clear()
    nt.interface.clear()
    nt.is_modifier = True
    _iface(nt, "Geometry", "Geometry")
    for nm, k, d, extra in (
            ("Count", "Int", 10000, {"min_value": 0}), ("Size", "Vector", (20, 20, 10), {}),
            ("Speed", "Float", 7.0, {"min_value": 0.001}), ("Wind", "Vector", (0, 0, 0), {}),
            ("Gravity Sign", "Float", -1.0, {}), ("Lives", "Int", 2, {"min_value": 1, "max_value": 64}),
            ("Loop Frames", "Int", 96, {"min_value": 1}), ("Start Frame", "Int", 1, {}),
            ("FPS", "Float", 24.0, {}), ("Particle Size", "Float", 0.001, {}),
            ("Streak Length", "Float", 0.15, {}), ("Sway", "Float", 0.0, {}), ("Seed", "Int", 0, {}),
            ("Ground", "Collection", None, {}), ("Splash", "Bool", True, {}),
            ("Splash Time", "Float", 0.08, {}), ("Material", "Material", None, {}),
            ("Camera", "Object", None, {}), ("Near Clear", "Float", 1.5, {}),
            ("Viewport Fraction", "Float", 0.1, {"min_value": 0.0, "max_value": 1.0})):
        _iface(nt, nm, k, d, **extra)
    _iface(nt, "Geometry", "Geometry", io="OUTPUT")
    t = _T(nt)
    gi = t.n("NodeGroupInput")
    go = t.n("NodeGroupOutput")
    I = lambda k: t.out(gi, k)  # noqa: E731
    idx = t.out(t.n("GeometryNodeInputIndex"))
    two_pi = 2 * math.pi

    # Lifetime loop: each particle lives `Lives` times per loop. Life k of a loop always reuses the
    # same random start, so frame Start+Loop == frame Start exactly, at the true speed.
    tm = t.n("GeometryNodeInputSceneTime")
    loop_t = t.math("DIVIDE", t.math("SUBTRACT", t.out(tm, "Frame"), I("Start Frame")), I("Loop Frames"))
    phase0 = t.out(t.n("FunctionNodeRandomValue", {"Min": 0.0, "Max": 1.0, "ID": idx, "Seed": I("Seed")},
                       data_type="FLOAT"))
    tl = t.math("MULTIPLY_ADD", loop_t, I("Lives"), phase0)
    life = t.math("FLOORED_MODULO", t.math("FLOOR", tl), I("Lives"))
    f = t.math("FRACT", tl)
    lid = t.math("MULTIPLY_ADD", idx, 64.0, life)  # per-life random stream

    def rnd(off, lo=0.0, hi=1.0):
        seed = t.math("ADD", I("Seed"), float(off))
        return t.out(t.n("FunctionNodeRandomValue", {"Min": lo, "Max": hi, "ID": lid, "Seed": seed},
                         data_type="FLOAT"))

    size = t.n("ShaderNodeSeparateXYZ", {0: I("Size")})
    sx, sy, sz = t.out(size, "X"), t.out(size, "Y"), t.out(size, "Z")
    sign = I("Gravity Sign")
    # direction of travel: wind/speed horizontally, gravity sign vertically
    wdir = t.vmath("SCALE", I("Wind"), scale=t.math("DIVIDE", 1.0, I("Speed")))
    direc = t.vmath("NORMALIZE", t.vmath("ADD", wdir, t.out(t.n("ShaderNodeCombineXYZ", {"Z": sign}))))
    speed = t.vmath("LENGTH", t.vmath("ADD", I("Wind"), t.out(t.n("ShaderNodeCombineXYZ", {"Z": I("Speed")}))))
    life_s = t.math("DIVIDE", t.math("DIVIDE", I("Loop Frames"), I("FPS")), I("Lives"))
    length = t.math("MULTIPLY", speed, life_s)  # distance covered in one life
    start = t.out(t.n("ShaderNodeCombineXYZ", {
        "X": t.math("MULTIPLY", t.math("SUBTRACT", rnd(1), 0.5), sx),
        "Y": t.math("MULTIPLY", t.math("SUBTRACT", rnd(2), 0.5), sy),
        "Z": t.math("MULTIPLY", rnd(3), sz)}))
    # ground: first hit along this life's path (collection geometry relative to this object)
    coll = t.n("GeometryNodeCollectionInfo", {"Collection": I("Ground")}, transform_space="RELATIVE")
    real = t.n("GeometryNodeRealizeInstances", {"Geometry": t.out(coll)})
    ray = t.n("GeometryNodeRaycast", {"Target Geometry": t.out(real), "Source Position": start,
                                      "Ray Direction": direc, "Ray Length": length}, data_type="FLOAT")
    hit = t.math("MULTIPLY", t.out(ray, "Is Hit"), t.math("LESS_THAN", sign, 0.0))
    hit_d = t.out(t.n("GeometryNodeSwitch", {"Switch": t.math("GREATER_THAN", hit, 0.5),
                                             "False": length, "True": t.out(ray, "Hit Distance")},
                      input_type="FLOAT"))
    travel = t.math("MULTIPLY", f, length)
    pos = t.vmath("ADD", start, t.vmath("SCALE", direc, scale=travel))
    # sway (snow/dust/ash/embers): two sines per life
    swx = t.math("SINE", t.math("MULTIPLY", t.math("MULTIPLY_ADD", f, 2.0, rnd(5)), two_pi))
    swy = t.math("COSINE", t.math("MULTIPLY", t.math("MULTIPLY_ADD", f, 1.5, rnd(6)), two_pi))
    sway = t.vmath("SCALE", t.out(t.n("ShaderNodeCombineXYZ", {"X": swx, "Y": swy})), scale=I("Sway"))
    pos = t.vmath("ADD", pos, sway)
    alive = t.math("LESS_THAN", travel, hit_d)
    # keep a clear zone around the camera: particles closer than ~1.5 m render as huge blobs
    cam = t.n("GeometryNodeObjectInfo", {"Object": I("Camera")}, transform_space="RELATIVE")
    near = t.math("GREATER_THAN", t.vmath("DISTANCE", pos, t.out(cam, "Location")), I("Near Clear"))
    alive = t.math("MULTIPLY", alive, near)
    # fade in/out over the first/last 10% of a life: no popping
    fade = t.math("MINIMUM", t.math("MINIMUM", t.math("MULTIPLY", f, 10.0),
                                    t.math("MULTIPLY", t.math("SUBTRACT", 1.0, f), 10.0)), 1.0)

    # full count in renders, a fraction in the viewport (keeps scenes interactive)
    vp_count = t.math("MULTIPLY", I("Count"), I("Viewport Fraction"))
    count = t.out(t.n("GeometryNodeSwitch", {"Switch": t.out(t.n("GeometryNodeIsViewport")),
                                             "False": I("Count"), "True": vp_count}, input_type="INT"))
    pts = t.n("GeometryNodePoints", {"Count": count, "Position": pos})
    # particle mesh: rain = thin 3-sided streak along travel, others = small blobs/flakes
    if kind == "rain":
        drop = t.n("GeometryNodeMeshCone", {"Vertices": 3, "Radius Top": 0.0,
                                            "Radius Bottom": I("Particle Size"), "Depth": I("Streak Length")},
                   fill_type="NONE")
        rot = t.out(t.n("FunctionNodeAlignRotationToVector", {"Vector": direc}, axis="Z"))
        scale = t.out(t.n("ShaderNodeCombineXYZ", {"X": fade, "Y": fade, "Z": t.math("MULTIPLY", fade, rnd(7, 0.7, 1.3))}))
    else:
        if kind == "ash":
            drop = t.n("GeometryNodeMeshGrid", {"Size X": I("Particle Size"), "Size Y": I("Particle Size"),
                                                "Vertices X": 2, "Vertices Y": 2})
        else:
            drop = t.n("GeometryNodeMeshIcoSphere", {"Radius": I("Particle Size"), "Subdivisions": 1})
        eul = t.n("FunctionNodeRandomValue", {"ID": idx, "Seed": I("Seed"), "Min": (0, 0, 0),
                                              "Max": (6.283, 6.283, 6.283)}, data_type="FLOAT_VECTOR")
        rot = t.out(t.n("FunctionNodeEulerToRotation", {"Euler": t.out(eul)}))
        s = t.math("MULTIPLY", fade, rnd(7, 0.5, 1.5))
        scale = t.out(t.n("ShaderNodeCombineXYZ", {"X": s, "Y": s, "Z": s}))
    mat_drop = t.n("GeometryNodeSetMaterial", {"Geometry": t.out(drop), "Material": I("Material")})
    inst = t.n("GeometryNodeInstanceOnPoints", {"Points": t.out(pts), "Selection": alive,
                                                "Instance": t.out(mat_drop), "Rotation": rot, "Scale": scale})
    result = t.out(inst)
    if kind == "rain":  # splash crown at the impact point right after the hit
        win = t.math("DIVIDE", I("Splash Time"), life_s)  # splash duration as a fraction of a life
        since = t.math("SUBTRACT", f, t.math("DIVIDE", hit_d, length))
        on = t.math("MULTIPLY", t.math("MULTIPLY", hit, t.math("LESS_THAN", since, win)),
                    t.math("MULTIPLY", t.math("GREATER_THAN", since, 0.0), I("Splash")))
        grow = t.math("DIVIDE", since, win)
        hit_pos = t.out(ray, "Hit Position")
        spts = t.n("GeometryNodePoints", {"Count": count, "Position": hit_pos})
        crown = t.n("GeometryNodeMeshCone", {"Vertices": 8, "Radius Top": 0.03, "Radius Bottom": 0.006,
                                             "Depth": 0.02}, fill_type="NONE")
        cmat = t.n("GeometryNodeSetMaterial", {"Geometry": t.out(crown), "Material": I("Material")})
        up = t.out(t.n("FunctionNodeAlignRotationToVector", {"Vector": t.out(ray, "Hit Normal")}, axis="Z"))
        g = t.math("MULTIPLY_ADD", grow, 0.8, 0.2)
        cs = t.out(t.n("ShaderNodeCombineXYZ", {"X": g, "Y": g, "Z": t.math("SUBTRACT", 1.0, grow)}))
        sinst = t.n("GeometryNodeInstanceOnPoints", {"Points": t.out(spts), "Selection": on,
                                                     "Instance": t.out(cmat), "Rotation": up, "Scale": cs})
        join = t.n("GeometryNodeJoinGeometry")
        nt.links.new(t.out(sinst), join.inputs[0])
        nt.links.new(result, join.inputs[0])
        result = t.out(join)
    nt.links.new(result, go.inputs[0])
    return nt


def _material(kind):
    name = PREFIX + "M_" + kind.capitalize()
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    b = bx.node(mat.node_tree, "BSDF_PRINCIPLED")
    vals = {
        "rain": {"Base Color": (0.8, 0.85, 0.9, 1), "Roughness": 0.05, "IOR": 1.33,
                 "Transmission Weight": 0.8, "Alpha": 0.35},
        "snow": {"Base Color": (0.9, 0.92, 0.95, 1), "Roughness": 0.6, "Subsurface Weight": 0.3},
        "dust": {"Base Color": (0.55, 0.47, 0.38, 1), "Roughness": 1.0, "Alpha": 0.6},
        "ash": {"Base Color": (0.08, 0.08, 0.08, 1), "Roughness": 1.0},
        "embers": {"Base Color": (0.05, 0.02, 0.0, 1), "Emission Color": (1.0, 0.32, 0.04, 1),
                   "Emission Strength": 25.0},
    }[kind]
    for k, v in vals.items():
        b.inputs[k].default_value = v
    return mat


def _camera_box(cam, distance, lo_z, frames):
    """World AABB of the camera's near frustum (0..distance) over the frame range."""
    sc = bpy.context.scene
    keep = sc.frame_current
    pts = []
    step = max(1, (frames[1] - frames[0]) // 8)
    half = math.atan(cam.data.sensor_width / 2 / cam.data.lens)  # sensor fit AUTO: larger axis
    for fr in range(frames[0], frames[1] + 1, step):
        sc.frame_set(fr)
        m = cam.matrix_world
        for d in (0.0, distance * 0.5, distance):
            w = d * math.tan(min(half, math.radians(60)))
            for sx in (-1, 1):
                for sy in (-1, 1):
                    pts.append(m @ Vector((sx * w, sy * w, -d)))
    sc.frame_set(keep)
    a = Vector((min(p.x for p in pts), min(p.y for p in pts), lo_z))
    top = min(max(max(p.z for p in pts) + 2.0, lo_z + 6), lo_z + 15)  # rain above ~15 m reads as haze
    b = Vector((max(p.x for p in pts), max(p.y for p in pts), top))
    return a, b


def run(type="rain", intensity="moderate", density=None, wind=(0.0, 0.0), ground=None, distance=18.0,  # noqa: A002
        loop_frames=None, seed=0, splash=True, max_count=400000, **_):
    if type not in TYPES:
        raise ValueError(f"type must be one of {sorted(TYPES)}")
    bx.object_mode()
    spec = TYPES[type]
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base
    frames = (sc.frame_start, sc.frame_end)
    loop = int(loop_frames or (frames[1] - frames[0] + 1))
    grounds = bx.objects(ground) if ground else []
    # box floor = the lowest ground *top*, so particles missing the ground stop at its level
    lo_z = min((max((o.matrix_world @ Vector(c)).z for c in o.bound_box) for o in grounds), default=0.0)
    cam = sc.camera
    if cam:
        a, b = _camera_box(cam, distance, lo_z, frames)
    else:
        a, b = Vector((-distance / 2, -distance / 2, lo_z)), Vector((distance / 2, distance / 2, lo_z + 10))
    size = b - a
    dens = density if density is not None else spec["density"][INTENSITY[intensity]]
    count = int(size.x * size.y * size.z * dens)
    res = {"ok": True, "type": type}
    if count > max_count:
        res["warning"] = f"count {count} capped to {max_count}: reduce --distance or --density"
        count = max_count
    speed = spec["speed"] * (1.25 if intensity in ("heavy", "storm") and type == "rain" else 1.0)
    w = Vector((*wind, 0.0))
    lives = max(1, min(64, round(loop / fps / spec["life"])))
    eff_speed = math.hypot(speed, w.length)
    shutter = 0.5 / fps  # 180-degree shutter: what a camera smears a drop into
    name = PREFIX + type.capitalize()
    nt = build_tree(name, "rain" if type == "rain" else type)
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        col = bpy.data.collections.get("ENV_Weather") or bpy.data.collections.new("ENV_Weather")
        if col.name not in sc.collection.children:
            sc.collection.children.link(col)
        col.objects.link(ob)
    ob.location = (a.x + size.x / 2, a.y + size.y / 2, a.z)
    for m in [m for m in ob.modifiers if m.type == "NODES"]:
        ob.modifiers.remove(m)
    mod = ob.modifiers.new(name, "NODES")
    mod.node_group = nt
    gcol = None
    if grounds:
        gcol = bpy.data.collections.get(name + "_Ground") or bpy.data.collections.new(name + "_Ground")
        for o in list(gcol.objects):
            gcol.objects.unlink(o)
        for o in grounds:
            gcol.objects.link(o)
    vals = {"Count": count, "Size": tuple(size), "Speed": speed, "Wind": tuple(w),
            "Gravity Sign": float(spec["sign"]), "Lives": lives, "Loop Frames": loop,
            "Start Frame": frames[0], "FPS": fps, "Particle Size": spec["size"],
            "Streak Length": max(eff_speed * shutter, 0.02), "Sway": spec["sway"], "Seed": seed,
            "Ground": gcol, "Splash": bool(splash and type == "rain"),
            "Splash Time": 0.08, "Material": _material(type), "Camera": cam}
    ids = {i.name: i.identifier for i in nt.interface.items_tree if getattr(i, "in_out", "") == "INPUT"}
    for k, v in vals.items():
        getattr(mod.properties.inputs, ids[k]).value = v
    res.update({"object": ob.name, "count": count, "box_m": bx.r(list(size), 2),
                "speed_ms": round(eff_speed, 2), "life_s": round(loop / fps / lives, 2), "loop_frames": loop,
                "ground": [o.name for o in grounds]})
    if type == "rain":
        res["streak_m"] = round(vals["Streak Length"], 3)
        res["note"] = "rain reads only when backlit: put a light or bright sky behind it"
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--type", default="rain", choices=sorted(TYPES))
    p.add_argument("--intensity", default="moderate", choices=list(INTENSITY))
    p.add_argument("--density", type=float, default=None)
    p.add_argument("--wind", type=float, nargs=2, default=(0.0, 0.0))
    p.add_argument("--ground", nargs="*", default=None)
    p.add_argument("--distance", type=float, default=18.0)
    p.add_argument("--loop-frames", type=int, default=None)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-splash", dest="splash", action="store_false")
    p.add_argument("--max-count", type=int, default=400000)
    p.add_argument("--save", default=None)
    bx.cli(run, p)
