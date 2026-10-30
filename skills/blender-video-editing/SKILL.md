---
name: blender-video-editing
description: Video in Blender 5.2 - Video Sequencer edits from Python (clips, image sequences, crossfades, titles, music fades, proxies, color management, H.264/AAC output) and motion tracking (feature detection, camera solve, scene orientation, tripod and plane tracking, stabilization) for VFX shots. Use to cut renders/footage together or match-move a camera.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.2.0"
---

# Video editing and tracking

The execution model is in `blender-core`. Rendering the 3D shots and the compositor (5.0 API) are in `blender-rendering`.

## One call each
```
scripts/vse_edit.py -- --clips //renders/sh010/ //renders/sh020/ //logo.png --crossfade 12 --title "Project" --audio //music.wav --out //edit.mp4 --render
scripts/vse_edit.py -- --clips a.mp4 b.mp4 c.mp4 --crossfade 0 --fps 24 --out //review/f_#### --render   # hard cuts to PNG
```
```python
import track_camera; print(track_camera.run(clip="C:/shots/sh010.mp4", focal=35, sensor=36))  # live/MCP only
```

## vse_edit.py
- Builds into its own `Edit` scene (`--scene`), so 3D scenes stay untouched. Clips go on alternating channels 1/2, crossfades (`CROSS`) on 3, the title on 4, clip audio on 6/7 (movies get their sound strip), and music on 8 (trimmed to the edit with a `--audio-fade` volume fade-out).
- A clip may be a movie, a still (`--still-seconds`), a folder of frames, or a `####` pattern. Each crossfade overlaps the previous clip by `--crossfade` frames, so the edit gets shorter by that much per cut. Re-running replaces the previous edit.
- Sets **view transform Standard**: footage must pass through untouched (measured: AgX turned pure red into 0.86/0.23/0.13). Grade on purpose with strip modifiers instead.
- Output: `.mp4/.mov/.mkv` = H.264 (CRF high, preset good) + AAC 192k stereo. Any other path = PNG frames. 5.0+ needs `image_settings.media_type = "VIDEO"` **before** `file_format = "FFMPEG"`. It reports the file size, and the test decodes it back (frame count, size).

## Editing rules pros follow
- **Match the frame rate first** (`--fps` = the footage/render rate). Mixed rates drift audio. Re-render or retime (`SPEED` effect) instead.
- Heavy footage: build proxies (`strip.use_proxy = True`, 25/50%, `sequencer.rebuild_proxy`). 5.2 builds only proxies (no `.blen_tc` timecode files anymore).
- Per-strip color: `strip.colorspace_settings.name` (sRGB for 8-bit video, Linear Rec.709 for EXR renders). A dedicated edit scene keeps 3D color settings out of the edit.
- 5.2 API: `strips.new_movie(..., stream=N)` / `new_sound(stream=N)` pick a stream from multi-track files. `strip.connections` lists connected strips. New effect type `COMPOSITOR` (a node-tree effect). Text strips have Subtitles / Main Title / Corner Title presets in the UI. Timing uses `left_handle`/`right_handle`/`duration` (5.1 names). Strip keyframes live on the **scene's** action.

## Motion tracking (track_camera.py, live session)
- The Clip Editor operators need a window, so this borrows the largest area, runs, and restores it. In `-b` it raises. It detects features at the first and last frame, tracks both ways, deletes tracks shorter than `min_frames`, solves (auto keyframes, refines focal only if unknown), deletes tracks above `max_error` px and re-solves, then runs `setup_tracking_scene` (camera + Camera Solver constraint, background footage, frame range).
- Measured on a synthetic 40-frame dolly at 960×540: 56 tracks, **0.19 px** solve error, 35 mm focal kept exactly. Quality bar: < 0.3 px great, < 0.5 good, > 1 px slides.
- Give `focal`/`sensor` whenever known. The solver is far more stable than when refining the focal. Set the sensor before the focal (focal is stored in px).
- Nodal pans (camera only rotates): `tripod=True`. A normal solve fails without parallax.
- Orient the scene after solving (UI, Clip Editor context): select 3 floor tracks → `clip.set_plane(plane="FLOOR")`, 1 track → `clip.set_origin()`, 2 tracks a known distance apart → `clip.set_scale(distance=…)`. Otherwise scale and up are arbitrary.
- Other jobs: screen/sign replacement → `clip.create_plane_track()` on 4+ tracks of a planar surface. Shaky footage → 2D stabilization (`tracking.stabilization.use_2d_stabilization`, add tracks). Points for modeling → `clip.bundles_to_mesh()`.

## Shooting/footage tips that make solves work
Fast shutter (little motion blur), real parallax (move the camera, don't just pan), textured static surfaces at several depths, no rolling-shutter whip pans, and a lens grid shot to calibrate distortion when using wide lenses.

## Gotchas
- `bpy.ops.render.render(animation=True)` renders the sequencer only when `scene.render.use_sequencer` is on and the strips are in the **scene being rendered**. The script renders its own edit scene.
- Removing a clip also removes its effect strips. Collect names before deleting in loops.
- Image sequences must be contiguous. Missing frames show as black.
