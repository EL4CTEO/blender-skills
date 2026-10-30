import json
import math
import os
import pathlib
import struct
import subprocess
import wave

import bmesh
import bpy
import numpy as np
from run_all import TMP, requires_gpu, skill_module

HERE = pathlib.Path(__file__).resolve().parent


def _png(path, rgb, w=160, h=90):
    img = bpy.data.images.new("t", w, h)
    a = np.zeros((h, w, 4), np.float32)
    a[...] = (*rgb, 1)
    img.pixels.foreach_set(a.ravel())
    img.filepath_raw, img.file_format = str(path), "PNG"
    img.save()
    bpy.data.images.remove(img)


def test_vse_edit_crossfade_title_audio_mp4():
    d = TMP / "vse"
    for c, rgb in (("red", (1, 0, 0)), ("blue", (0, 0, 1))):
        (d / c).mkdir(parents=True, exist_ok=True)
        for i in range(12):
            _png(d / c / f"f_{i:04d}.png", rgb)
    _png(d / "green.png", (0, 1, 0))
    with wave.open(str(d / "tone.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * t / 22050))) for t in range(22050 * 3)))
    ve = skill_module("blender-video-editing", "vse_edit")
    r = ve.run(clips=[str(d / "red"), str(d / "blue" / "f_####.png"), str(d / "green.png")], fps=12,
               resolution=(160, 90), crossfade=4, still_seconds=1, title="Test", audio=str(d / "tone.wav"),
               out=str(d / "frames" / "f_####"), render=True)
    assert r["frame_end"] == 28 and [c.get("crossfade") for c in r["clips"]] == [None, 4, 4], r

    def px(f):
        a = np.array(bpy.data.images.load(str(d / "frames" / f"f_{f:04d}.png")).pixels[:]).reshape(90, 160, 4)
        return np.round(a[45, 20, :3], 2).tolist()
    assert px(1) == [1, 0, 0] and px(11) == [0.5, 0, 0.5] and px(14) == [0, 0, 1] and px(26) == [0, 1, 0]
    edit = bpy.data.scenes["Edit"]
    music = edit.sequence_editor.strips["Music"]
    assert music.right_handle == 29  # trimmed to the edit
    edit.frame_set(10)
    loud = music.volume
    edit.frame_set(28)
    assert loud == 1.0 and music.volume < 0.01  # fade-out keys live on the scene's action
    r = ve.run(clips=[str(d / "red"), str(d / "blue")], fps=12, resolution=(160, 90), crossfade=4,
               audio=str(d / "tone.wav"), out=str(d / "edit.mp4"), render=True)  # re-run clears the old edit
    assert r["bytes"] > 1000 and r["strips"] == 4, r
    mc = bpy.data.movieclips.load(r["out"])
    assert mc.frame_duration == r["frame_end"] == 20 and tuple(mc.size) == (160, 90)


DRIVER = """
import bpy, sys, json
args = sys.argv[sys.argv.index("--") + 1:]
sys.path.insert(0, args[2])
def go():
    try:
        import track_camera
        r = track_camera.run(clip=args[0], focal=35, sensor=36)
        r["constraints"] = [c.type for c in bpy.context.scene.camera.constraints]
        r["area_restored"] = all(a.ui_type != "CLIP_EDITOR" for a in bpy.context.window.screen.areas)
    except Exception as e:
        r = {"ok": False, "error": repr(e)}
    open(args[1], "w").write(json.dumps(r))
    bpy.ops.wm.quit_blender()
bpy.app.timers.register(go, first_interval=2.0)
"""


def _footage(out):
    """40 frames of a textured set seen by a dollying 35 mm camera (Workbench, textured)."""
    sc = bpy.context.scene
    rng = np.random.default_rng(3)
    img = bpy.data.images.new("noise", 512, 512)
    a = np.kron(rng.random((64, 64)), np.ones((8, 8)))[..., None].repeat(4, -1)
    a[..., 3] = 1
    img.pixels.foreach_set(a.astype(np.float32).ravel())
    mat = bpy.data.materials.new("N")
    t = mat.node_tree.nodes.new("ShaderNodeTexImage")
    t.image = img
    mat.node_tree.links.new(t.outputs[0], next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs[0])

    def obj(name, build, loc=(0, 0, 0)):
        me, bm = bpy.data.meshes.new(name), bmesh.new()
        uv = bm.loops.layers.uv.new("UVMap")
        build(bm)
        for f in bm.faces:
            for lp in f.loops:
                c = lp.vert.co
                lp[uv].uv = (c.x * 0.13 + c.z * 0.07, c.y * 0.13 + c.z * 0.05)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        o.location = loc
        sc.collection.objects.link(o)
        me.materials.append(mat)
    obj("Ground", lambda bm: bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=10))
    for i, (x, y, s) in enumerate(((-2, 2, 1.2), (1.5, 3, 1.6), (3, 0.5, 0.8), (-3, -1, 1.0))):
        obj(f"Box{i}", lambda bm, s=s: bmesh.ops.create_cube(bm, size=s), (x, y, s / 2))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    sc.collection.objects.link(cam)
    sc.camera, cam.data.lens, cam.data.sensor_width = cam, 35, 36
    for f, x in ((1, -2.0), (40, 2.0)):
        cam.location, cam.rotation_euler = (x, -9, 3.2), (math.radians(75), 0, math.radians(-x * 3))
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
    sc.frame_start, sc.frame_end = 1, 40
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.color_type, sc.display.shading.light = "TEXTURE", "FLAT"
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.filepath, sc.render.image_settings.file_format = str(out / "f_"), "PNG"
    bpy.ops.render.render(animation=True)


def test_track_camera_solves_in_ui_session():
    requires_gpu()  # opens a real Blender window: Clip Editor operators don't run in -b
    out = TMP / "footage"
    out.mkdir(exist_ok=True)
    _footage(out)
    drv, res = TMP / "drive_track.py", TMP / "track.json"
    drv.write_text(DRIVER)
    scripts = HERE.parent / "skills" / "blender-video-editing" / "scripts"
    subprocess.run([bpy.app.binary_path, "--factory-startup", "--no-window-focus", "--window-geometry", "0", "0",
                    "1000", "700", "--python", str(drv), "--", str(out / "f_0001.png"), str(res), str(scripts)],
                   timeout=300, capture_output=True)
    r = json.loads(res.read_text())
    assert r["ok"] and r["solved"] and r["solve_error_px"] < 0.5 and r["bundles"] >= 20, r
    assert abs(r["focal_mm"] - 35) < 0.01 and r["constraints"] == ["CAMERA_SOLVER"] and r["area_restored"], r
    tc = skill_module("blender-video-editing", "track_camera")
    try:
        tc.run(clip=str(out / "f_0001.png"))
        raise AssertionError("background mode must refuse")
    except RuntimeError as e:
        assert "live session" in str(e)
    assert os.path.exists(out / "f_0040.png")
