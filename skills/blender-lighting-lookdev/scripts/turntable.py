"""Look-dev scene in one call: framed camera, light rig (studio 3-point / HDRI / both), optional
cyclorama backdrop and a looping turntable (camera + lights orbit; the asset is untouched).

Usage:
  blender -b f.blend -P turntable.py -- --objects Hero [--rig studio|hdri|both] [--hdri path.exr]
      [--hdri-strength 1] [--frames 120] [--lens 85] [--backdrop] [--elevation 15] [--save out.blend]
  MCP: import turntable; print(turntable.run(objects=["Hero"], rig="studio", frames=120))
Then render with blender-rendering/render_batch.py (e.g. --frames 1-120 --format MP4).
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PREFIX = "LD_"


def _bounds(obs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _clear():
    for o in [o for o in bpy.data.objects if o.name.startswith(PREFIX)]:
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and data.users == 0:
            for coll in (bpy.data.lights, bpy.data.cameras, bpy.data.meshes):
                if data.name in coll and coll[data.name] == data:
                    coll.remove(data)
                    break


def _area(name, power, size, loc, target, col, color=(1, 1, 1)):
    ld = bpy.data.lights.new(PREFIX + name, "AREA")
    ld.energy, ld.size, ld.color = power, size, color
    ld.shape = "DISK"
    lo = bpy.data.objects.new(PREFIX + name, ld)
    lo.location = loc
    lo.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(lo)
    return lo


def _backdrop(lo, hi, col):
    w = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z) * 6
    bm = bmesh.new()
    a = bm.verts.new((-w / 2, -w / 2, 0))
    b = bm.verts.new((w / 2, -w / 2, 0))
    c = bm.verts.new((w / 2, w / 2, 0))
    d = bm.verts.new((-w / 2, w / 2, 0))
    e = bm.verts.new((w / 2, w / 2, w * 0.6))
    f = bm.verts.new((-w / 2, w / 2, w * 0.6))
    bm.faces.new((a, b, c, d))
    bm.faces.new((d, c, e, f))
    me = bpy.data.meshes.new(PREFIX + "Backdrop")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(PREFIX + "Backdrop", me)
    ob.location = (((lo.x + hi.x) / 2), ((lo.y + hi.y) / 2), lo.z)
    bev = ob.modifiers.new("Curve", "BEVEL")
    bev.width, bev.segments, bev.limit_method = w * 0.25, 16, "ANGLE"
    for p in me.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new(PREFIX + "Backdrop")
    bsdf = bx.node(mat.node_tree, "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.18, 0.18, 0.18, 1)  # 18% grey
    bsdf.inputs["Roughness"].default_value = 0.8
    me.materials.append(mat)
    col.objects.link(ob)
    return ob


def run(objects=None, rig="studio", hdri=None, hdri_strength=1.0, frames=120, lens=85.0,
        backdrop=False, elevation=15.0, **_):
    bx.object_mode()
    obs = bx.objects(objects, types=("MESH", "CURVE", "FONT", "CURVES", "ARMATURE"))
    _clear()
    sc = bpy.context.scene
    col = bpy.data.collections.get(PREFIX + "Lookdev") or bpy.data.collections.new(PREFIX + "Lookdev")
    if col.name not in sc.collection.children:
        sc.collection.children.link(col)
    lo, hi = _bounds(obs)
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1e-3)
    pivot = bpy.data.objects.new(PREFIX + "Pivot", None)
    pivot.location = center
    col.objects.link(pivot)
    cam_d = bpy.data.cameras.new(PREFIX + "Cam")
    cam_d.lens = lens
    fov = 2 * math.atan(cam_d.sensor_width / (2 * lens))  # horizontal (sensor_fit AUTO, landscape)
    aspect = sc.render.resolution_x / sc.render.resolution_y
    fov = min(fov, 2 * math.atan(math.tan(fov / 2) / aspect)) if aspect >= 1 else fov * aspect
    dist = radius / math.sin(fov / 2) * 1.1  # fits the bounding sphere on the narrower axis
    cam_d.clip_start, cam_d.clip_end = dist / 100, dist * 20
    cam = bpy.data.objects.new(PREFIX + "Cam", cam_d)
    el = math.radians(elevation)
    cam.location = center + Vector((0, -math.cos(el), math.sin(el))) * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(cam)
    sc.camera = cam
    rigged = [cam]
    nlights = 0
    if rig in ("studio", "both"):
        d = dist * 0.8
        key_power = 60 * d * d
        for name, az, elv, k, size in (("Key", -45, 35, 1.0, 1.0), ("Fill", 50, 15, 0.35, 1.5),
                                       ("Rim", 160, 40, 0.8, 0.6)):
            a, e = math.radians(az), math.radians(elv)
            loc = center + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * d
            rigged.append(_area(name, key_power * k, radius * size, loc, center, col))
            nlights += 1
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    wt = world.node_tree
    bg = bx.node(wt, "BACKGROUND")
    out_n = bx.node(wt, "OUTPUT_WORLD")
    if rig in ("hdri", "both") and hdri:
        env = next((n for n in wt.nodes if n.type == "TEX_ENVIRONMENT"), None) or wt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(bpy.path.abspath(hdri), check_existing=True)
        wt.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = hdri_strength
        nlights += 1
    else:
        for l in list(bg.inputs["Color"].links):
            wt.links.remove(l)
        bg.inputs["Color"].default_value = (0.05, 0.05, 0.05, 1)
        bg.inputs["Strength"].default_value = 1.0 if rig == "hdri" else 0.5
    if out_n and not out_n.inputs["Surface"].is_linked:
        wt.links.new(bg.outputs["Background"], out_n.inputs["Surface"])
    if backdrop:
        rigged.append(_backdrop(lo, hi, col))
    bpy.context.view_layer.update()  # pivot matrix must be evaluated before parenting
    for o in rigged:  # camera, lights and backdrop orbit together; the asset stays untouched
        o.parent = pivot
        o.matrix_parent_inverse = pivot.matrix_world.inverted()
    if frames and frames > 1:
        sc.frame_start, sc.frame_end = 1, frames
        pivot.rotation_euler = (0, 0, 0)
        pivot.keyframe_insert("rotation_euler", index=2, frame=1)
        pivot.rotation_euler = (0, 0, 2 * math.pi)  # full turn lands on frame N+1
        pivot.keyframe_insert("rotation_euler", index=2, frame=frames + 1)
        for fc in _fcurves(pivot):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
    return {"ok": True, "camera": cam.name, "lens": lens, "distance": round(dist, 3), "lights": nlights,
            "frames": frames, "pivot": pivot.name, "collection": col.name,
            "note": "frame N+1 == frame 1, so 1..N loops seamlessly"}


def _fcurves(ob):
    from bpy_extras import anim_utils
    ad = ob.animation_data
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return list(cb.fcurves) if cb else []


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--rig", default="studio", choices=["studio", "hdri", "both"])
    p.add_argument("--hdri", default=None)
    p.add_argument("--hdri-strength", type=float, default=1.0)
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--lens", type=float, default=85.0)
    p.add_argument("--backdrop", action="store_true")
    p.add_argument("--elevation", type=float, default=15.0)
    bx.cli(run, p)
