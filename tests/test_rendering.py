import os

import bpy
import fixtures as fx
from run_all import TMP, requires_gpu, skill_module


def _camera():
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location, cam.rotation_euler = (0, -6, 1), (1.5708, 0, 0)
    bpy.context.scene.camera = cam
    return cam


def test_render_stills_cycles_eevee_workbench():
    requires_gpu()
    fx.cube("Box")
    _camera()
    rb = skill_module("blender-rendering", "render_batch")
    r = rb.run(engine="CYCLES", preset="preview", res=(64, 64), samples=4, device="CPU",
               out=str(TMP / "r" / "c_####"), frames="1,2", view="Khronos PBR Neutral")
    assert r["ok"] and len(r["files"]) == 2 and r["view"] == "Khronos PBR Neutral", r
    r = rb.run(engine="BLENDER_WORKBENCH", res=(64, 64), out=str(TMP / "r" / "w_####"), format="EXR")
    assert r["ok"] and r["files"][0].endswith(".exr")
    r = rb.run(engine="BLENDER_EEVEE", res=(64, 64), samples=1, out=str(TMP / "r" / "e_####"), transparent=True)
    assert r["ok"] and os.path.getsize(r["files"][0]) > 0


def test_lookdev_turntable_and_studio():
    requires_gpu()
    fx.uv_sphere("Hero", radius=0.5, location=(0, 0, 0.5))
    lk = skill_module("blender-lighting-lookdev", "turntable")
    r = lk.run(objects=["Hero"], rig="studio", frames=24, hdri=None)
    assert r["camera"] in bpy.data.objects and r["lights"] >= 3, r
    cam = bpy.data.objects[r["camera"]]
    assert bpy.context.scene.frame_end == 24 and cam.parent is not None
    rb = skill_module("blender-rendering", "render_batch")
    out = rb.run(engine="BLENDER_WORKBENCH", res=(48, 48), out=str(TMP / "tt" / "t_####"), frames="1,12")
    assert len(out["files"]) == 2
