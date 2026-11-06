"""Time-of-day / mood environment in one call: physically measured sky + matching sun or moon lamp,
night sky with stars and city glow, height fog sized from meteorological visibility, exposure
balance, optional stylized mood (accent lights, AgX look, compositor grade).

Everything lives in the ENV_Mood collection / ENV_World / ENV_Grade; re-running replaces it.
Sun color and sun/sky ratio come from Blender 5.2's Multiple Scattering sky, measured per elevation.
Usage:
  blender -b f.blend -P scene_mood.py -- [--time noon|morning|afternoon|golden|sunrise|sunset|
      blue_hour|night|moonless] [--mood none|cyberpunk|horror|underwater|desert]
      [--elevation DEG] [--heading DEG] [--overcast 0-1] [--fog-visibility M] [--fog-height M]
      [--fog-color R G B] [--fog-anisotropy 0.6] [--no-grade] [--use-exposure] [--keep-view]
      [--moon-elevation 35] [--city-glow 0-1] [--stars 0-1] [--save out.blend]
  MCP: import scene_mood; result = scene_mood.run(time="golden", fog_visibility=300)
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PREFIX, COLL, WORLD, GRADE = "ENV_", "ENV_Mood", "ENV_World", "ENV_Grade"
K_SKY = 0.0285  # sky model -> scene units: noon sun ~4 W/m2, grey card ~0.18 at exposure 0
LUM = (0.2126, 0.7152, 0.0722)

# Measured in Blender 5.2.2 (Multiple Scattering, altitude 100 m, default densities):
# elevation deg -> horizontal sky irradiance RGB (sun disc off), direct-normal sun irradiance RGB.
SKY_TABLE = [
    (-12, (0.00052, 0.00434, 0.02001), (0, 0, 0)),
    (-9, (0.00134, 0.01087, 0.05), (0, 0, 0)),
    (-6, (0.0056, 0.02903, 0.12731), (0, 0, 0)),
    (-4, (0.04899, 0.08454, 0.27704), (0, 0, 0)),
    (-2, (0.37054, 0.38863, 0.76517), (0, 0, 0)),
    (0, (1.22718, 1.29752, 1.90794), (4.0847, 0.5232, 0.0)),
    (1, (1.72506, 1.96472, 2.74431), (17.8917, 3.9918, 0.0)),
    (2, (2.18728, 2.69088, 3.72502), (33.7886, 10.5753, 0.0666)),
    (4, (2.97495, 4.12061, 5.93637), (61.1676, 27.8893, 4.5117)),
    (6, (3.61373, 5.3837, 8.18156), (81.6948, 45.2236, 12.9207)),
    (10, (4.57352, 7.33074, 11.97798), (108.1851, 72.2033, 32.4792)),
    (15, (5.4053, 8.96377, 15.17675), (126.7271, 93.6768, 53.019)),
    (20, (6.01476, 10.11608, 17.36756), (137.6212, 107.1634, 68.0404)),
    (30, (6.90652, 11.77815, 20.50427), (149.517, 122.6031, 87.2194)),
    (45, (7.84406, 13.52765, 23.82461), (157.6205, 133.5704, 102.1744)),
    (60, (8.48658, 14.73384, 26.12468), (161.3662, 138.7539, 109.6074)),
    (90, (9.00377, 15.70996, 27.99332), (163.7695, 142.0494, 114.3969)),
]

# time: sun elevation (None = night), target grey-card brightness relative to noon
TIMES = {
    "noon": (60, 1.0), "morning": (20, 1.0), "afternoon": (35, 1.0), "golden": (6, 0.85),
    "sunrise": (1, 0.7), "sunset": (1, 0.7), "blue_hour": (-4, 0.35),
    "night": (None, 0.2), "moonless": (None, 0.1),
}
# mood: defaults (explicit arguments win)
MOODS = {
    "none": {},
    "cyberpunk": dict(time="moonless", fog_visibility=150, fog_height=10, fog_color=(0.85, 0.8, 1.0),
                      fog_anisotropy=0.5, city_glow=1.0, glow_color=(0.9, 0.2, 0.6), accents=True,
                      look="AgX - Punchy", saturation=1.1, bloom=0.6, white_point=6500),
    "horror": dict(time="night", moon_elevation=12, moon_color=(0.6, 0.8, 0.85), fog_visibility=35,
                   fog_height=1.5, fog_color=(0.7, 0.78, 0.8), look="AgX - High Contrast",
                   saturation=0.55, bloom=0.15, brightness=0.1, white_point=7500),
    "underwater": dict(time="noon", elevation=70, fog_visibility=30, fog_height=0,
                       fog_color=(0.25, 0.7, 0.75), absorption=(0.1, 0.55, 0.6), fog_anisotropy=0.85,
                       look="AgX - Base Contrast", saturation=0.9, bloom=0.2, brightness=0.4, underwater=True),
    "desert": dict(time="afternoon", elevation=45, fog_visibility=3000, fog_height=0,
                   fog_color=(1.0, 0.82, 0.6), look="AgX - Medium High Contrast", saturation=1.05,
                   bloom=0.1, white_point=5800),
}


def _lerp_table(el):
    el = max(min(el, 90), -12)
    for (e0, s0, d0), (e1, s1, d1) in zip(SKY_TABLE, SKY_TABLE[1:]):
        if e0 <= el <= e1:
            t = (el - e0) / (e1 - e0)
            return ([a + (b - a) * t for a, b in zip(s0, s1)], [a + (b - a) * t for a, b in zip(d0, d1)])
    return list(SKY_TABLE[-1][1]), list(SKY_TABLE[-1][2])


def lum(c):
    return sum(a * b for a, b in zip(c, LUM))


def _sun_dir(el, heading):
    """Direction TO the light. heading 0 = +Y, 90 = +X (matches ShaderNodeTexSky.sun_rotation)."""
    e, h = math.radians(el), math.radians(heading)
    return Vector((math.sin(h) * math.cos(e), math.cos(h) * math.cos(e), math.sin(e)))


def _scene_bounds():
    pts = [o.matrix_world @ Vector(c) for o in bpy.context.scene.objects
           if o.type in {"MESH", "CURVES", "CURVE"} and not o.name.startswith(PREFIX) and o.visible_get()
           for c in o.bound_box]
    if not pts:
        return Vector((-5, -5, 0)), Vector((5, 5, 3))
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def _clear():
    for o in [o for o in bpy.data.objects if o.name.startswith(PREFIX + "Mood_")]:
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and data.users == 0:
            for coll in (bpy.data.lights, bpy.data.meshes):
                if data.name in coll and coll[data.name] == data:
                    coll.remove(data)
                    break
    for m in [m for m in bpy.data.materials if m.name.startswith(PREFIX + "Mood_")]:
        bpy.data.materials.remove(m)


def _coll():
    col = bpy.data.collections.get(COLL)
    if col is None:
        col = bpy.data.collections.new(COLL)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    return col


def _light(col, name, kind, energy, color, direction=None, loc=None, target=None, **kw):
    ld = bpy.data.lights.new(PREFIX + "Mood_" + name, kind)
    ld.energy, ld.color = energy, color
    for k, v in kw.items():
        setattr(ld, k, v)
    ob = bpy.data.objects.new(PREFIX + "Mood_" + name, ld)
    if direction is not None:  # sun: local -Z points away from the light direction
        ob.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    if loc is not None:
        ob.location = loc
        if target is not None:
            ob.rotation_euler = (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    col.objects.link(ob)
    return ob


def _norm(c):
    m = max(c) or 1.0
    return tuple(max(x / m, 0.0) for x in c)


def _math(nt, op, a=None, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _mix_rgb(nt, fac, a, b, blend="MIX"):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type, m.blend_type = "RGBA", blend
    for sock, v in ((m.inputs[0], fac), (m.inputs[6], a), (m.inputs[7], b)):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, tuple):
            sock.default_value = (*v[:3], 1.0)
        else:
            nt.links.new(v, sock)
    return m.outputs[2]


def _world(p, mult):
    """Build ENV_World. Returns horizontal ambient irradiance (luminance, scene units)."""
    w = bpy.data.worlds.get(WORLD) or bpy.data.worlds.new(WORLD)
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    bpy.context.scene.world = w
    ambient = 0.0
    if p["underwater"]:
        col = tuple(c * 0.02 * mult for c in p["fog_color"])
        bg.inputs["Color"].default_value = (*col, 1)
        return math.pi * lum(col)
    if p["elevation"] is not None and p["elevation"] > -12:
        sky = nt.nodes.new("ShaderNodeTexSky")
        bx.set_enum(sky, "sky_type", "MULTIPLE_SCATTERING")
        sky.sun_disc = False  # the sun lamp is the sun (sharp shadows in both engines)
        sky.sun_elevation = math.radians(p["elevation"])
        sky.sun_rotation = math.radians(p["heading"])
        sky_h, _ = _lerp_table(p["elevation"])
        color = sky.outputs["Color"]
        if p["overcast"] > 0:
            oc = p["overcast_rgb"]
            color = _mix_rgb(nt, p["overcast"], color, oc)
            sky_h = [a + (b * math.pi - a) * p["overcast"] for a, b in zip(sky_h, oc)]
        nt.links.new(color, bg.inputs["Color"])
        bg.inputs["Strength"].default_value = K_SKY * mult
        ambient = K_SKY * mult * lum(sky_h)
    else:  # night dome: zenith -> horizon glow, stars for camera rays only
        zen = tuple(c * mult for c in (0.0040, 0.0065, 0.0140))
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        z = _math(nt, "MAXIMUM", sep.outputs["Z"], 0.0)
        glow = _math(nt, "EXPONENT", _math(nt, "MULTIPLY", z, -7.0))
        gc = tuple(c * zen[1] * 6 * p["city_glow"] / max(p["glow_color"]) for c in p["glow_color"])
        dome = _mix_rgb(nt, glow, zen, gc)
        if p["stars"] > 0:
            vor = nt.nodes.new("ShaderNodeTexVoronoi")
            vor.inputs["Scale"].default_value = 350.0
            nt.links.new(tc.outputs["Generated"], vor.inputs["Vector"])
            core = _math(nt, "LESS_THAN", vor.outputs["Distance"], 0.045)
            bright = _math(nt, "GREATER_THAN", _math(nt, "POWER", vor.outputs["Color"], 1.0), 1 - 0.35 * p["stars"])
            above = _math(nt, "GREATER_THAN", sep.outputs["Z"], 0.05)
            star = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", core, bright), above)
            star = _math(nt, "MULTIPLY", star, 1.0 - 0.8 * p["city_glow"])
            lp = nt.nodes.new("ShaderNodeLightPath")
            star = _math(nt, "MULTIPLY", star, lp.outputs["Is Camera Ray"])
            dome = _mix_rgb(nt, star, dome, (2.5, 2.6, 3.0))
        nt.links.new(dome, bg.inputs["Color"])
        ambient = math.pi * lum(zen) * (1 + 0.5 * p["city_glow"])
    if p["fog_visibility"]:  # camera sees the far background through fog
        lp = nt.nodes.new("ShaderNodeLightPath")
        far = 1 - math.exp(-3.912 / p["fog_visibility"] * p["fog_far"])
        fac = _math(nt, "MULTIPLY", lp.outputs["Is Camera Ray"], far)
        link = bg.inputs["Color"].links[0] if bg.inputs["Color"].is_linked else None
        src = link.from_socket if link else tuple(bg.inputs["Color"].default_value)[:3]
        fc = tuple(c * ambient / math.pi / max(bg.inputs["Strength"].default_value, 1e-6) for c in p["fog_color"])
        nt.links.new(_mix_rgb(nt, fac, src, fc), bg.inputs["Color"])
    return ambient


def _fog_box(lo, hi, cam):
    pts = [lo, hi] + ([cam.matrix_world.translation] if cam else [])
    a = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
    b = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
    pad = max((b - a).length * 0.25, 2.0)
    return a - Vector((pad, pad, min(pad, 1.0))), b + Vector((pad, pad, pad))


def _transmittance(p, lo, hi, top, el):
    """Fraction of key/sky light reaching subject height through the fog (for exposure metering)."""
    if not p["fog_visibility"]:
        return 1.0
    sigma, z = 3.912 / p["fog_visibility"], lo.z + 0.25 * (hi.z - lo.z)
    s = max(math.sin(math.radians(el)), 0.1)
    if p["fog_height"]:
        h = p["fog_height"]
        depth = sigma * h * (math.exp(-(z - lo.z) / h) - math.exp(-(top - lo.z) / h))
    else:
        depth = sigma * max(top - z, 0.0)
    return max(math.exp(-depth / s), 1 / 16)  # meter at most 4 EV up: fog should still read dense


def _fog(p, col, lo, a, b):
    """Box volume around scene + camera. Density = extinction from visibility (Koschmieder 3.912/V)."""
    sigma = 3.912 / p["fog_visibility"]
    me = bpy.data.meshes.new(PREFIX + "Mood_Fog")
    vs = [(x, y, z) for x in (a.x, b.x) for y in (a.y, b.y) for z in (a.z, b.z)]
    me.from_pydata(vs, [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    ob = bpy.data.objects.new(PREFIX + "Mood_Fog", me)
    col.objects.link(ob)
    ob.display_type = "BOUNDS"
    mat = bpy.data.materials.new(PREFIX + "Mood_Fog")
    me.materials.append(mat)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (*p["fog_color"], 1)
    vol.inputs["Anisotropy"].default_value = p["fog_anisotropy"]
    if p.get("absorption"):
        vol.inputs["Absorption Color"].default_value = (*p["absorption"], 1)
    nt.links.new(vol.outputs[0], out.inputs["Volume"])
    if p["fog_height"]:  # exponential height falloff above the ground
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], sep.inputs[0])
        h = _math(nt, "MAXIMUM", _math(nt, "SUBTRACT", sep.outputs["Z"], lo.z), 0.0)
        dens = _math(nt, "MULTIPLY", _math(nt, "EXPONENT", _math(nt, "DIVIDE", h, -p["fog_height"])), sigma)
        nt.links.new(dens, vol.inputs["Density"])
    else:
        vol.inputs["Density"].default_value = sigma
    return ob, sigma, (b - a).length


def _grade(p, ev_to_threshold):
    sc = bpy.context.scene
    cur = sc.compositing_node_group
    if cur is not None and cur.name != GRADE:
        return "kept existing compositor tree"
    ng = bpy.data.node_groups.get(GRADE) or bpy.data.node_groups.new(GRADE, "CompositorNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    img = rl.outputs["Image"]
    if p["bloom"] > 0:
        g = ng.nodes.new("CompositorNodeGlare")
        g.inputs["Type"].default_value = "Bloom"
        g.inputs["Quality"].default_value = "High"
        g.inputs["Threshold"].default_value = ev_to_threshold
        g.inputs["Strength"].default_value = p["bloom"]
        g.inputs["Size"].default_value = 0.6
        ng.links.new(img, g.inputs["Image"])
        img = g.outputs["Image"]
    if p["white_point"] != 6500:
        cb = ng.nodes.new("CompositorNodeColorBalance")
        cb.inputs["Type"].default_value = "White Point"
        cb.inputs["Input Temperature"].default_value = p["white_point"]
        ng.links.new(img, cb.inputs["Image"])
        img = cb.outputs["Image"]
    if p["saturation"] != 1.0:
        hs = ng.nodes.new("CompositorNodeHueSat")
        hs.inputs["Saturation"].default_value = p["saturation"]
        ng.links.new(img, hs.inputs["Image"])
        img = hs.outputs["Image"]
    gout = ng.nodes.new("NodeGroupOutput")
    ng.links.new(img, gout.inputs[0])
    sc.compositing_node_group = ng
    sc.render.use_compositing = True
    return GRADE


def run(time=None, mood="none", elevation=None, heading=None, overcast=0.0, fog_visibility=None,
        fog_height=None, fog_color=None, fog_anisotropy=None, grade=True, use_exposure=False,
        keep_view=False, moon_elevation=None, city_glow=None, stars=None, **_):
    if mood not in MOODS:
        raise ValueError(f"mood must be one of {sorted(MOODS)}")
    bx.object_mode()
    md = MOODS[mood]
    p = dict(time="noon", elevation=None, heading=None, overcast=0.0, fog_visibility=None, fog_height=0,
             fog_color=(1, 1, 1), fog_anisotropy=0.6, absorption=None, moon_elevation=35,
             moon_color=None, city_glow=0.0, glow_color=(1.0, 0.45, 0.15), stars=1.0, accents=False,
             look=None, saturation=1.0, bloom=0.0, brightness=None, white_point=6500, underwater=False)
    p.update(md)
    for k, v in dict(time=time, elevation=elevation, heading=heading, fog_visibility=fog_visibility,
                     fog_height=fog_height, fog_color=fog_color, fog_anisotropy=fog_anisotropy,
                     moon_elevation=moon_elevation, city_glow=city_glow, stars=stars).items():
        if v is not None:
            p[k] = tuple(v) if isinstance(v, list) else v
    p["overcast"] = max(0.0, min(1.0, overcast or md.get("overcast", 0.0)))
    if p["time"] not in TIMES:
        raise ValueError(f"time must be one of {sorted(TIMES)}")
    t_el, t_bright = TIMES[p["time"]]
    if p["elevation"] is None:
        p["elevation"] = t_el
    night = p["elevation"] is None or p["elevation"] < -12
    if p["time"] in ("night", "moonless"):
        night, p["elevation"] = True, None
    if p["brightness"] is None:
        p["brightness"] = t_bright * (1 - 0.15 * p["overcast"])
    if night and p["time"] in ("night", "moonless") and mood == "none" and city_glow is None:
        p["city_glow"] = 0.3 if p["time"] == "night" else 0.6
    sc = bpy.context.scene
    cam = sc.camera
    lo, hi = _scene_bounds()
    center = (lo + hi) / 2
    extent = max((hi - lo).length, 1.0)
    if p["heading"] is None:  # side/back light reads form; front light flattens
        yaw = 0.0
        if cam:
            f = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
            yaw = math.degrees(math.atan2(f.x, f.y))
        p["heading"] = (yaw + 135.0) % 360
    p["fog_far"] = max(extent * 4, 200.0)
    _clear()
    col = _coll()
    res = {"ok": True, "time": p["time"], "mood": mood, "heading": round(p["heading"], 1)}
    warnings = []

    # key light (sun / moon) in sky-model units, before the brightness multiplier
    key_dir, key_e, key_rgb = None, 0.0, (1, 1, 1)
    if not night and p["elevation"] > 0:
        _, dni = _lerp_table(p["elevation"])
        key_dir = _sun_dir(p["elevation"], p["heading"])
        key_e = K_SKY * lum(dni) * (1 - p["overcast"]) ** 1.5
        key_rgb = _norm(dni)
        sun_angle = math.radians(0.545 + 25 * p["overcast"])
    elif night and p["time"] == "night":
        key_dir = _sun_dir(p["moon_elevation"], (p["heading"] + 40) % 360)
        key_e = 0.3
        key_rgb = p["moon_color"] or (0.72, 0.82, 1.0)  # moonlight reads cool (Purkinje shift)
        sun_angle = math.radians(0.52)
    if p["overcast"] > 0 and not night:
        sky_h, dni = _lerp_table(p["elevation"])
        glob = (lum(sky_h) + lum(dni) * max(math.sin(math.radians(p["elevation"])), 0)) * 0.3
        p["overcast_rgb"] = tuple(c * glob / math.pi for c in (0.95, 0.98, 1.04))
    # balance: grey card under the key + ambient should read at `brightness` x 0.18
    amb0 = _world(p, 1.0)
    fa, fb = _fog_box(lo, hi, cam)
    e_key = 0.0
    if key_dir is not None:  # meter between a ground plane and a wall facing the key
        a = math.asin(key_dir.z)
        e_key = key_e * (math.sin(a) + math.cos(a)) / 2
        e_key *= _transmittance(p, lo, hi, fb.z, math.degrees(a))
    e_ref = max(e_key + amb0 * _transmittance(p, lo, hi, fb.z, 45), 1e-6)
    ev = math.log2(p["brightness"] * math.pi / e_ref)
    mult = 1.0 if use_exposure else 2 ** ev
    _world(p, mult)
    if key_dir is not None and key_e > 1e-6:
        _light(col, "Moon" if night else "Sun", "SUN", key_e * mult, key_rgb, direction=key_dir,
               angle=sun_angle)
        res["key"] = {"light": PREFIX + "Mood_" + ("Moon" if night else "Sun"), "strength": round(key_e * mult, 4),
                      "color": bx.r(list(key_rgb), 3), "elevation": round(math.degrees(math.asin(key_dir.z)), 1)}
    if p["accents"]:  # neon rim pair: magenta / cyan from opposite sides
        d = extent * 0.6
        e_target = p["brightness"] * math.pi * 4  # accents out-shine the ambient
        for nm, side, rgb in (("NeonA", -1, (1.0, 0.1, 0.6)), ("NeonB", 1, (0.1, 0.8, 1.0))):
            loc = center + Vector((side * d, d * 0.3, extent * 0.25))
            _light(col, nm, "AREA", e_target * math.pi * d * d, rgb, loc=loc, target=center,
                   size=extent * 0.3, shape="DISK")
        res["accents"] = 2
    vs = sc.view_settings
    if not keep_view:
        bx.set_enum(vs, "view_transform", "AgX")
        vs.look = p["look"] or "None"
    vs.exposure = round(ev, 2) if use_exposure else 0.0
    res["exposure"] = round(ev, 2)
    res["practical_scale"] = round(2 ** -ev if use_exposure else 1.0, 4)
    res["ambient"] = round(amb0 * mult, 4)
    if p["fog_visibility"]:
        fog, sigma, size = _fog(p, col, lo, fa, fb)
        res["fog"] = {"object": fog.name, "density": round(sigma, 5), "visibility_m": p["fog_visibility"],
                      "height_m": p["fog_height"] or None}
        ee = sc.eevee
        ee.use_volumetric_shadows = True
        ee.volumetric_tile_size = "4"
        ee.volumetric_samples = max(ee.volumetric_samples, 96)
        ee.volumetric_end = max(ee.volumetric_end, size)
        sc.cycles.volume_bounces = max(sc.cycles.volume_bounces, 1)
    if grade and (p["bloom"] or p["saturation"] != 1.0 or p["white_point"] != 6500):
        # bloom threshold is scene-linear (before the view exposure): keep it at display white
        res["grade"] = _grade(p, 2 ** -ev if use_exposure else 1.0)
    if night and p["time"] == "moonless" and not p["accents"]:
        warnings.append("moonless: add practical lights (street/window/neon) as the key")
    if sc.render.engine == "BLENDER_EEVEE" and p["fog_visibility"] and p["fog_visibility"] < 15:
        warnings.append("EEVEE: very dense fog bands at tile size 4; use 2 or Cycles")
    if not cam:
        warnings.append("no scene camera: heading defaulted to 135 deg")
    if warnings:
        res["warnings"] = warnings
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--time", default=None, choices=sorted(TIMES))
    p.add_argument("--mood", default="none", choices=sorted(MOODS))
    p.add_argument("--elevation", type=float, default=None)
    p.add_argument("--heading", type=float, default=None)
    p.add_argument("--overcast", type=float, default=0.0)
    p.add_argument("--fog-visibility", type=float, default=None)
    p.add_argument("--fog-height", type=float, default=None)
    p.add_argument("--fog-color", type=float, nargs=3, default=None)
    p.add_argument("--fog-anisotropy", type=float, default=None)
    p.add_argument("--moon-elevation", type=float, default=None)
    p.add_argument("--city-glow", type=float, default=None)
    p.add_argument("--stars", type=float, default=None)
    p.add_argument("--no-grade", dest="grade", action="store_false")
    p.add_argument("--use-exposure", action="store_true")
    p.add_argument("--keep-view", action="store_true")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
