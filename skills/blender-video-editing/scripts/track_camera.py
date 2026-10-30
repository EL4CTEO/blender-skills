"""Automatic camera solve from footage: detect features at the start and end of the shot, track them
both ways, drop short tracks, solve (keyframes auto-picked), drop high-error tracks, re-solve, and set
up the 3D scene (camera with Camera Solver, footage as background, frame range).

Motion-tracking operators need a Clip Editor, so this runs in a live session with a window (blender-mcp
or the UI); it borrows the largest area as a Clip Editor and restores it. Background mode (-b) returns
an error. Give the real focal length and sensor width when known: the solve is far more stable.
Usage (live/MCP only):
  import track_camera; print(track_camera.run(clip="C:/shots/sh010.mp4", focal=35, sensor=36))
  track_camera.run(clip=..., tripod=True)               # nodal pans: rotation-only solve
  run(clip, focal=None, sensor=None, threshold=0.3, min_distance=60, min_frames=10, max_error=2.0,
      tripod=False, setup_scene=True) -> {"solve_error_px", "tracks", "bundles", ...}
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _clip_area():
    win = bpy.context.window or (bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None)
    if win is None:
        raise RuntimeError("motion tracking needs a window: run in a live session (blender-mcp/UI), not -b")
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    return win, area


def _solve(ctx, clip):
    with bpy.context.temp_override(**ctx):
        bpy.ops.clip.solve_camera()
    rec = clip.tracking.objects.active.reconstruction
    return rec.is_valid, rec.average_error


def run(clip=None, focal=None, sensor=None, threshold=0.3, min_distance=60, min_frames=10, max_error=2.0,
        tripod=False, setup_scene=True, **_):
    if bpy.app.background:
        raise RuntimeError("motion tracking operators need a Clip Editor: run in a live session (blender-mcp)")
    if not clip:
        raise ValueError("clip is required")
    mc = bpy.data.movieclips.load(bpy.path.abspath(clip), check_existing=True)
    sc = bpy.context.scene
    sc.active_clip = mc
    tr = mc.tracking
    if sensor:  # sensor first: focal is stored in pixels, so a later sensor change rescales the mm value
        tr.camera.sensor_width = sensor
    if focal:
        tr.camera.focal_length = focal
    st = tr.settings
    st.default_pattern_size, st.default_search_size = 21, 71
    st.default_motion_model, st.use_default_brute, st.use_default_normalization = "Loc", True, True
    st.default_correlation_min = 0.75
    st.use_keyframe_selection, st.use_tripod_solver = not tripod, tripod
    st.refine_intrinsics_focal_length = focal is None
    first, last = mc.frame_start, mc.frame_start + mc.frame_duration - 1
    win, area = _clip_area()
    old = area.ui_type
    area.ui_type = "CLIP_EDITOR"
    try:
        space = area.spaces.active
        space.clip, space.mode = mc, "TRACKING"
        region = next(r for r in area.regions if r.type == "WINDOW")
        ctx = dict(window=win, screen=win.screen, area=area, region=region, space_data=space, edit_movieclip=mc)
        with bpy.context.temp_override(**ctx):
            for frame, backwards in ((first, False), (last, True)):  # features entering late get tracked too
                sc.frame_set(frame)
                bpy.ops.clip.select_all(action="DESELECT")
                bpy.ops.clip.detect_features(threshold=threshold, min_distance=min_distance, margin=16)
                bpy.ops.clip.track_markers(backwards=backwards, sequence=True)
            bpy.ops.clip.select_all(action="SELECT")
            bpy.ops.clip.clean_tracks(frames=min_frames, error=0.0, action="DELETE_TRACK")
        ok, err = _solve(ctx, mc)
        removed = 0
        if ok and err > max_error * 0.5:  # second pass without the worst tracks
            n0 = len(tr.objects.active.tracks)
            with bpy.context.temp_override(**ctx):
                bpy.ops.clip.select_all(action="SELECT")
                bpy.ops.clip.clean_tracks(frames=0, error=max_error, action="DELETE_TRACK")
            removed = n0 - len(tr.objects.active.tracks)
            ok, err = _solve(ctx, mc)
        res = {"ok": True, "clip": mc.name, "frames": [first, last], "solved": ok, "solve_error_px": round(err, 4),
               "tracks": len(tr.objects.active.tracks), "removed_high_error": removed,
               "bundles": sum(1 for t in tr.objects.active.tracks if t.has_bundle),
               "focal_mm": round(tr.camera.focal_length, 3), "tripod": tripod}
        if ok and setup_scene:
            sc.frame_start, sc.frame_end = first, last
            with bpy.context.temp_override(**ctx):
                bpy.ops.clip.setup_tracking_scene()
            res["camera"] = sc.camera.name if sc.camera else None
        if not ok:
            res["warning"] = "solve failed: give --focal/--sensor, track more frames, or use tripod=True for pans"
        elif err > 1.0:
            res["warning"] = f"solve error {err:.2f} px: > 0.5 px will slide; refine tracks around the keyframes"
        return res
    finally:
        area.ui_type = old


if __name__ == "__main__":
    bx.emit({"ok": False, "error": "track_camera needs a live session with a window (import it via blender-mcp)"})
