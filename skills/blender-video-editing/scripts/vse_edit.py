"""Assemble a video edit in the Video Sequencer headless: movies (with their audio), image
sequences and stills in order, crossfades, a title card, a music bed with fade-out, then render
H.264/AAC MP4 or PNG frames.

Builds into its own scene (--scene, default "Edit") so the user's 3D scenes stay untouched. Channels:
1-2 clips (alternating), 3 crossfades, 4 title, 6-7 clip audio, 8 music. Clips
alternate channels 1/2 so each crossfade (channel 3) overlaps the previous clip by --crossfade frames.
A clip may be a movie file, a single image (held --still-seconds), a folder of frames, or a
frame pattern with # (render_####.png).
Usage:
  blender -b -P vse_edit.py -- --clips intro.mp4 //shots/sh010/ //logo.png [--fps 30]
      [--resolution 1920 1080] [--crossfade 12] [--still-seconds 3] [--title "My Film"]
      [--title-seconds 3] [--audio music.wav] [--audio-fade 1.0] [--out //edit.mp4] [--render]
      [--scene Edit] [--save out.blend]
  MCP: import vse_edit; print(vse_edit.run(clips=["a.mp4", "b.mp4"], crossfade=12, out="//edit.mp4", render=True))
"""
import glob
import os
import re
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

MOVIE = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf")
IMAGE = (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".webp", ".bmp", ".tga")


def _frames(path):
    """Sorted frame files for a folder or a # pattern, else None."""
    p = bpy.path.abspath(path)
    if os.path.isdir(p):
        files = sorted(f for f in glob.glob(os.path.join(p, "*")) if f.lower().endswith(IMAGE))
        return files or None
    if "#" in p:
        files = sorted(glob.glob(re.sub(r"#+", "*", p)))
        return files or None
    return None


def _add_clip(sed, path, channel, start, fps, still_seconds):
    p = bpy.path.abspath(path)
    name = os.path.splitext(os.path.basename(p.rstrip("/\\")))[0] or "clip"
    frames = _frames(path)
    sound = None
    if frames:
        st = sed.strips.new_image(name, frames[0], channel, start, fit_method="FIT")
        for f in frames[1:]:
            st.elements.append(os.path.basename(f))
    elif p.lower().endswith(MOVIE):
        st = sed.strips.new_movie(name, p, channel, start, fit_method="FIT")
        try:  # a movie's audio is a separate strip; files without audio raise
            sound = sed.strips.new_sound(name + "_audio", p, channel + 5, start)  # 6/7
        except RuntimeError:
            sound = None
    elif p.lower().endswith(IMAGE):
        st = sed.strips.new_image(name, p, channel, start, fit_method="FIT")
        st.right_handle = start + max(1, round(still_seconds * fps))
    else:
        raise ValueError(f"unsupported clip: {path}")
    if not os.path.exists(frames[0] if frames else p):
        raise FileNotFoundError(path)
    return st, sound


def _output(sc, out):
    path = bpy.path.abspath(out)
    st = sc.render.image_settings
    if path.lower().endswith((".mp4", ".mov", ".mkv")):
        st.media_type = "VIDEO"  # 5.0+: set the media type before the file format
        st.file_format = "FFMPEG"
        ff = sc.render.ffmpeg
        ff.format = "MPEG4" if path.lower().endswith(".mp4") else ("QUICKTIME" if path.lower().endswith(".mov") else "MKV")
        ff.codec, ff.constant_rate_factor, ff.ffmpeg_preset = "H264", "HIGH", "GOOD"
        ff.audio_codec, ff.audio_bitrate, ff.audio_channels = "AAC", 192, "STEREO"
    else:
        st.media_type, st.file_format = "IMAGE", "PNG"
    sc.render.filepath = path
    return path


def run(clips=None, fps=30, resolution=(1920, 1080), crossfade=12, still_seconds=3.0, title=None,
        title_seconds=3.0, audio=None, audio_fade=1.0, out=None, render=False, scene="Edit", **_):
    if not clips:
        raise ValueError("--clips is required")
    sc = bpy.data.scenes.get(scene) or bpy.data.scenes.new(scene)
    sc.render.fps, sc.render.fps_base = int(fps), 1.0
    sc.render.resolution_x, sc.render.resolution_y = resolution
    sc.render.resolution_percentage = 100
    sc.render.use_sequencer = True
    sc.view_settings.view_transform = "Standard"  # editorial: footage passes through (AgX would grade it)
    sc.view_settings.look = "None"
    sed = sc.sequence_editor_create()
    for nm in [s.name for s in sed.strips]:  # removing a clip also removes its crossfade
        if nm in sed.strips:
            sed.strips.remove(sed.strips[nm])
    placed, start, prev = [], 1, None
    for i, c in enumerate(clips):
        ch = 1 + i % 2
        st, snd = _add_clip(sed, c, ch, start, fps, still_seconds)
        info = {"name": st.name, "start": st.left_handle, "end": st.right_handle}
        if prev is not None and crossfade > 0:
            xf = min(crossfade, prev.right_handle - prev.left_handle - 1, st.right_handle - st.left_handle - 1)
            if xf > 0:  # slide the new clip back to overlap, then fade across the overlap
                shift = prev.right_handle - xf - st.left_handle
                st.frame_start += shift
                if snd:
                    snd.frame_start += shift
                sed.strips.new_effect(f"XF_{i}", "CROSS", 3, st.left_handle, length=xf, input1=prev, input2=st)
                info.update(start=st.left_handle, end=st.right_handle, crossfade=xf)
        placed.append(info)
        prev, start = st, st.right_handle
    end = max(s.right_handle for s in sed.strips) - 1
    sc.frame_start, sc.frame_end = 1, end
    if title:
        t = sed.strips.new_effect("Title", "TEXT", 4, 1, length=max(1, round(title_seconds * fps)))
        t.text, t.font_size = title, max(24, resolution[1] * 0.07)
        t.location, t.alignment_x, t.anchor_x = (0.5, 0.15), "CENTER", "CENTER"  # lower third
        t.use_shadow = True
        t.blend_type = "ALPHA_OVER"
    if audio:
        a = sed.strips.new_sound("Music", bpy.path.abspath(audio), 8, 1)
        if a.right_handle > end + 1:
            a.right_handle = end + 1
        fade = max(1, round(audio_fade * fps))
        a.volume = 1.0
        a.keyframe_insert("volume", frame=max(1, end - fade))
        a.volume = 0.0
        a.keyframe_insert("volume", frame=end)
        a.volume = 1.0
    res = {"ok": True, "scene": sc.name, "clips": placed, "frame_end": end, "fps": int(fps),
           "duration_s": round(end / fps, 3), "strips": len(sed.strips)}
    ws = getattr(bpy.context, "workspace", None)
    if ws is not None and hasattr(ws, "sequencer_scene"):
        ws.sequencer_scene = sc  # 5.0+: the VSE shows the workspace's sequencer scene
    if out:
        path = _output(sc, out)
        res["out"] = path
        if render:
            with bpy.context.temp_override(scene=sc):
                bpy.ops.render.render(animation=True, scene=sc.name)
            if sc.render.image_settings.media_type == "VIDEO":
                res["bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--clips", nargs="+", required=True)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--resolution", type=int, nargs=2, default=(1920, 1080))
    p.add_argument("--crossfade", type=int, default=12, help="frames (0 = hard cuts)")
    p.add_argument("--still-seconds", type=float, default=3.0)
    p.add_argument("--title", default=None)
    p.add_argument("--title-seconds", type=float, default=3.0)
    p.add_argument("--audio", default=None)
    p.add_argument("--audio-fade", type=float, default=1.0, help="fade-out seconds")
    p.add_argument("--out", default=None, help=".mp4/.mov/.mkv = H.264 video, else PNG frames path")
    p.add_argument("--render", action="store_true")
    p.add_argument("--scene", default="Edit")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
