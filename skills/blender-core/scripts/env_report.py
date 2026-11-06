"""Report Blender version, engines, GPU, add-ons, units and scene stats as JSON.

Usage:
  blender -b [file.blend] -P env_report.py
  MCP: import env_report; result = env_report.run()
"""
import os
import sys

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _gpu():
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices()
        return {"backend": prefs.compute_device_type,
                "devices": sorted({d.name for d in prefs.devices if d.type != "CPU"})}
    except Exception as e:
        return {"error": str(e)}


def run():
    sc = bpy.context.scene
    try:
        sc.render.engine = "__probe__"
    except TypeError as e:
        engines = str(e).split("in (")[-1].rstrip(")").replace("'", "").split(", ")
    us = sc.unit_settings
    kinds = {}
    for o in sc.objects:
        kinds[o.type] = kinds.get(o.type, 0) + 1
    enabled = sorted(bpy.context.preferences.addons.keys())
    return {
        "ok": True,
        "blender": bpy.app.version_string,
        "python": sys.version.split()[0],
        "background": bpy.app.background,
        "file": bpy.data.filepath or None,
        "engines": engines,
        "engine": sc.render.engine,
        "gpu": _gpu(),
        "addons_enabled": enabled,
        "rigify_available": any(m.__name__ == "rigify" for m in addon_utils.modules()),
        "units": {"system": us.system, "scale_length": us.scale_length, "length": us.length_unit},
        "color": {"view": sc.view_settings.view_transform, "look": sc.view_settings.look,
                  "display": sc.display_settings.display_device},
        "frame_range": [sc.frame_start, sc.frame_end, sc.render.fps],
        "objects": kinds,
        "data": {k: len(getattr(bpy.data, k)) for k in
                 ("meshes", "materials", "images", "actions", "node_groups", "collections")},
    }


if __name__ == "__main__":
    bx.cli(lambda **k: run(), bx.parser(__doc__))
