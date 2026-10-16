import bpy
import fixtures as fx
from run_all import skill_module


def _instances(ob, frame):
    sc = bpy.context.scene
    sc.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    return [tuple(i.matrix_world.translation) for i in dg.object_instances
            if i.is_instance and i.parent and i.parent.original == ob]


def test_precipitation_loops_and_stops_on_ground():
    names = fx.street()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 48
    pr = skill_module("blender-weather-fx", "precipitation")
    r = pr.run(type="rain", density=1.0, ground=names[:3], wind=(1.0, 0.0))
    assert r["ok"] and r["count"] > 100 and abs(r["speed_ms"] - 7.07) < 0.05, r
    ob = bpy.data.objects[r["object"]]
    a, b = _instances(ob, 1), _instances(ob, 49)  # loop end + 1 == start
    assert a and len(a) == len(b)
    assert max(abs(p - q) for u, v in zip(a, b) for p, q in zip(u, v)) < 1e-3
    zs = [p[2] for p in _instances(ob, 17)]
    assert min(zs) > -0.02, min(zs)  # nothing falls through the street (top at z=0)
    r = pr.run(type="snow", density=0.5, ground=["Ground"])
    assert r["speed_ms"] == 1.0 and r["life_s"] > 0
    r = pr.run(type="embers", density=0.2)
    assert r["object"] == "ENV_Weather_Embers"


def test_surface_weather_roundtrip_restores_materials():
    names = fx.street()
    mat = bpy.data.materials["M_Ground"]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexNoise")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])  # linked input must survive
    bsdf.inputs["Roughness"].default_value = 0.42
    before = sorted((lk.from_node.name, lk.to_socket.identifier) for lk in nt.links)
    sw = skill_module("blender-weather-fx", "surface_weather")
    r = sw.run(objects=names, wetness=0.6, puddles=0.4, ripples=1, streaks=0.5, snow=0.3)
    assert "M_Ground" in r["materials"], r
    assert bsdf.inputs["Coat Weight"].is_linked and bsdf.inputs["Base Color"].links[0].from_node.name.startswith("ENV_W_")
    sw.run(objects=names, wetness=0.9)  # re-run updates in place, no second group
    assert len([n for n in nt.nodes if n.name.startswith("ENV_W_") and n.type == "GROUP"]) == 1
    sw.run(objects=names, remove=True)
    after = sorted((lk.from_node.name, lk.to_socket.identifier) for lk in nt.links)
    assert after == before and abs(bsdf.inputs["Roughness"].default_value - 0.42) < 1e-6
    assert not any(n.name.startswith("ENV_W_") for n in nt.nodes) and "env_weather" not in mat


def test_snow_geometry_and_vertex_mask():
    fx.street()
    ball = bpy.data.objects["Ball"]
    faces0 = len(ball.data.polygons)
    sw = skill_module("blender-weather-fx", "surface_weather")
    r = sw.run(objects=["Ball"], snow=0.8, snow_depth=0.05, vertex_mask=True)
    assert r["snow_geometry"]["depth_m"] == 0.05 and r["vertex_mask"] == ["ENV_Weather"]
    eo = ball.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = eo.to_mesh()
    top = max(v.co.z for v in me.vertices)
    faces = len(me.polygons)
    eo.to_mesh_clear()
    assert faces > faces0 and top > 1.0 + 0.02, (faces, top)  # shell sits above the sphere top
    assert ball.data.color_attributes.active_color_name == "ENV_Weather"
    sw.run(objects=["Ball"], remove=True)
    assert not ball.modifiers and "ENV_Weather" not in ball.data.color_attributes


def test_lightning_keys_strokes_and_bolt():
    fx.street()
    sm = skill_module("blender-time-of-day", "scene_mood")
    sm.run(time="night")
    lt = skill_module("blender-weather-fx", "lightning")
    r = lt.run(frames=[20], strokes=3, seed=1)
    assert r["bolt"] == "ENV_Storm_Bolt" and r["sky_flash"] == "ENV_World", r
    light = bpy.data.objects[r["light"]].data
    sc = bpy.context.scene
    vals = []
    for f in range(18, 32):
        sc.frame_set(f)
        vals.append(light.energy)
    peaks = sum(1 for i in range(1, len(vals) - 1) if vals[i] > vals[i - 1] and vals[i] >= vals[i + 1] and vals[i] > 0.3 * r["peak_strength"])
    assert peaks == 3 and vals[0] == 0.0, vals
    again = lt.run(frames=[20])
    assert len([o for o in bpy.data.objects if o.name.startswith("ENV_Storm_")]) == 2 and again["ok"]
