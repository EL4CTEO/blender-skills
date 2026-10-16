import bpy
import fixtures as fx
from run_all import TMP, skill_module


def _mean_luma(path):
    img = bpy.data.images.load(path)
    px = list(img.pixels)
    bpy.data.images.remove(img)
    return sum(px[i] * 0.2126 + px[i + 1] * 0.7152 + px[i + 2] * 0.0722 for i in range(0, len(px), 4)) / (len(px) / 4)


def _render(tag):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device, sc.cycles.samples, sc.cycles.use_denoising = "CPU", 8, False
    sc.render.resolution_x, sc.render.resolution_y = 32, 18
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(TMP / "mood" / f"{tag}.png")
    bpy.ops.render.render(write_still=True)
    return _mean_luma(sc.render.filepath)


def test_time_presets_sun_color_and_balance():
    fx.street()
    sm = skill_module("blender-time-of-day", "scene_mood")
    noon = sm.run(time="noon")
    assert noon["key"]["color"][2] > 0.6 and abs(noon["exposure"]) < 0.3, noon
    sunset = sm.run(time="sunset")
    assert sunset["key"]["color"][1] < 0.4 and sunset["key"]["color"][2] < 0.05, sunset  # red sun
    assert len([o for o in bpy.data.objects if o.name.startswith("ENV_Mood_")]) == 1  # rerun replaces
    blue = sm.run(time="blue_hour")
    assert "key" not in blue and bpy.context.scene.world.name == "ENV_World"
    night = sm.run(time="night")
    assert night["key"]["light"] == "ENV_Mood_Moon"
    sky = next(n for n in bpy.context.scene.world.node_tree.nodes if n.type == "TEX_VORONOI")  # stars
    assert sky is not None


def test_night_renders_darker_than_noon():
    fx.street()
    sm = skill_module("blender-time-of-day", "scene_mood")
    sm.run(time="noon")
    day = _render("noon")
    sm.run(time="night")
    night = _render("night")
    assert 0.25 < day < 0.85 and night < day * 0.75, (day, night)


def test_fog_density_from_visibility_and_moods():
    fx.street()
    sm = skill_module("blender-time-of-day", "scene_mood")
    r = sm.run(time="morning", fog_visibility=150, fog_height=4)
    assert abs(r["fog"]["density"] - 3.912 / 150) < 1e-4, r
    fog = bpy.data.objects[r["fog"]["object"]]
    assert any(n.type == "PRINCIPLED_VOLUME" for n in fog.data.materials[0].node_tree.nodes)
    assert bpy.context.scene.eevee.use_volumetric_shadows
    r = sm.run(mood="cyberpunk")
    assert r["accents"] == 2 and r["grade"] == "ENV_Grade", r
    ng = bpy.context.scene.compositing_node_group
    assert ng.name == "ENV_Grade" and any(n.bl_idname == "CompositorNodeGlare" for n in ng.nodes)
    assert bpy.context.scene.view_settings.look == "AgX - Punchy"
    r = sm.run(time="noon", use_exposure=True, mood="horror")
    assert r["practical_scale"] > 0 and abs(bpy.context.scene.view_settings.exposure - r["exposure"]) < 0.01
