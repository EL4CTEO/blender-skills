"""Storm lightning: keyed multi-stroke flashes (a real strike is 3-4 return strokes ~40-60 ms apart),
a cloud-lit flash light, an optional branching emissive bolt and a sky flash on the world.

Everything is ENV_Storm_*; re-running replaces it. Times are in frames of the current scene fps.
Usage:
  blender -b f.blend -P lightning.py -- [--flashes 2] [--frames 30 80] [--strokes 3]
      [--at X Y] [--distance 300] [--height 450] [--strength 1.0] [--no-bolt] [--no-sky]
      [--seed 0] [--save out.blend]
  MCP: import lightning; result = lightning.run(flashes=2, strength=1.5)
"""
import math
import os
import random
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PREFIX = "ENV_Storm_"


def _clear():
    for o in [o for o in bpy.data.objects if o.name.startswith(PREFIX)]:
        data = o.data
        bpy.data.objects.remove(o)
        for coll in (bpy.data.lights, bpy.data.curves):
            if data is not None and data.name in coll and coll[data.name].users == 0:
                coll.remove(coll[data.name])
                break
    m = bpy.data.materials.get(PREFIX + "Bolt")
    if m:
        bpy.data.materials.remove(m)


def _bolt_points(rng, top, bottom, depth=7, jag=0.12):
    """Midpoint displacement between top and bottom; returns a list of Vectors."""
    pts = [top, bottom]
    for lvl in range(depth):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            seg = (b - a).length
            mid = (a + b) / 2 + Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 0.3))) * seg * jag
            out += [mid, b]
        pts = out
    return pts


def _curve(name, polylines, radii, mat, col):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth, cu.bevel_resolution = 1.0, 0
    for pts, r in zip(polylines, radii):
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            taper = 1.0 - 0.6 * i / max(len(pts) - 1, 1)
            sp.points[i].co = (*p, 1.0)
            sp.points[i].radius = r * taper
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    ob.visible_shadow = False
    col.objects.link(ob)
    return ob


def _envelope(rng, starts, strokes, fps):
    """{frame: intensity 0..1}. Each stroke: peak, 20% next frame, gone after ~3 frames."""
    env = {}
    gap = max(2, round(0.05 * fps))  # ~50 ms between strokes; >= 2 frames so the flicker reads
    for s in starts:
        t = s
        for k in range(strokes):
            peak = 1.0 if k == 0 else rng.uniform(0.5, 0.9)
            for dt, v in ((0, peak), (1, peak * 0.2), (2, peak * 0.05)):
                env[t + dt] = max(env.get(t + dt, 0.0), v)
            t += gap + rng.randint(0, gap)
        env.setdefault(s - 1, 0.0)
        env.setdefault(t + 2, 0.0)
    return dict(sorted(env.items()))


def run(flashes=2, frames=None, strokes=3, at=None, distance=300.0, height=450.0, strength=1.0,
        bolt=True, sky=True, seed=0, **_):
    bx.object_mode()
    rng = random.Random(seed)
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base
    if frames:
        starts = [int(f) for f in frames]
    else:
        span = max(sc.frame_end - sc.frame_start - 12, 1)
        starts = sorted(sc.frame_start + 4 + int(span * (i + rng.uniform(0.2, 0.8)) / flashes) for i in range(flashes))
    env = _envelope(rng, starts, strokes, fps)
    _clear()
    col = bpy.data.collections.get("ENV_Weather") or bpy.data.collections.new("ENV_Weather")
    if col.name not in sc.collection.children:
        sc.collection.children.link(col)
    cam = sc.camera
    if at:
        strike = Vector((at[0], at[1], 0.0))
    elif cam:  # in view, far behind the subject, slightly off-center
        fwd = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
        side = cam.matrix_world.to_quaternion() @ Vector((1, 0, 0))
        fwd.z = side.z = 0
        strike = cam.matrix_world.translation + fwd.normalized() * distance + side.normalized() * distance * 0.25
        strike.z = 0.0
    else:
        strike = Vector((0, distance, 0))
    # flash light: diffuse cloud light from the strike direction
    key = next((o for o in bpy.data.objects if o.name in ("ENV_Mood_Sun", "ENV_Mood_Moon")), None)
    base = max(key.data.energy * 2.5 if key else 2.0, 1.0) * strength
    ld = bpy.data.lights.new(PREFIX + "Flash", "SUN")
    ld.color, ld.angle = (0.78, 0.84, 1.0), math.radians(12)
    lo = bpy.data.objects.new(PREFIX + "Flash", ld)
    to_strike = (strike + Vector((0, 0, height * 0.6))).normalized()
    lo.rotation_euler = (-to_strike).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(lo)
    prefs = bpy.context.preferences.edit
    keep = prefs.keyframe_new_interpolation_type
    prefs.keyframe_new_interpolation_type = "LINEAR"
    try:
        for f, v in env.items():
            ld.energy = base * v
            ld.keyframe_insert("energy", frame=f)
        res = {"ok": True, "flash_frames": starts, "keys": len(env), "light": lo.name,
               "peak_strength": round(base, 3), "strike": bx.r(list(strike), 1)}
        if bolt:
            mat = bpy.data.materials.new(PREFIX + "Bolt")
            nt = mat.node_tree
            nt.nodes.clear()
            em = nt.nodes.new("ShaderNodeEmission")
            em.inputs["Color"].default_value = (0.8, 0.86, 1.0, 1)
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(em.outputs[0], out.inputs["Surface"])
            top = strike + Vector((rng.uniform(-0.2, 0.2) * height, rng.uniform(-0.2, 0.2) * height, height))
            main = _bolt_points(rng, top, strike)
            lines, radii = [main], [height * 0.0012]
            for _b in range(4):
                i = rng.randint(len(main) // 8, len(main) // 2)
                a = main[i]
                end = a + Vector((rng.uniform(-1, 1) * height * 0.25, rng.uniform(-1, 1) * height * 0.25,
                                  -rng.uniform(0.15, 0.4) * height))
                lines.append(_bolt_points(rng, a, end, depth=5))
                radii.append(radii[0] * 0.45)
            bo = _curve(PREFIX + "Bolt", lines, radii, mat, col)
            strength_sock = em.inputs["Strength"]
            for f, v in env.items():
                strength_sock.default_value = 400.0 * v * strength
                strength_sock.keyframe_insert("default_value", frame=f)
            res["bolt"] = bo.name
        w = sc.world
        if sky and w and w.node_tree:
            bg = bx.node(w.node_tree, "BACKGROUND")
            if bg is not None and not bg.inputs["Strength"].is_linked:
                s0 = bg.inputs["Strength"].default_value
                for f, v in env.items():
                    bg.inputs["Strength"].default_value = s0 * (1 + 3 * v * strength)
                    bg.inputs["Strength"].keyframe_insert("default_value", frame=f)
                bg.inputs["Strength"].default_value = s0
                res["sky_flash"] = w.name
    finally:
        prefs.keyframe_new_interpolation_type = keep
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--flashes", type=int, default=2)
    p.add_argument("--frames", type=int, nargs="*", default=None)
    p.add_argument("--strokes", type=int, default=3)
    p.add_argument("--at", type=float, nargs=2, default=None)
    p.add_argument("--distance", type=float, default=300.0)
    p.add_argument("--height", type=float, default=450.0)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--no-bolt", dest="bolt", action="store_false")
    p.add_argument("--no-sky", dest="sky", action="store_false")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--save", default=None)
    bx.cli(run, p)
