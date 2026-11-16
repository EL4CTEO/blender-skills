# Runtime adapter

## Live Blender

Discover exposed tools instead of copying stale tool names. In the current Blender MCP family, use `get_addon_status`, `get_scene_info`, `get_object_info`, `get_viewport_screenshot`, `bpy_api_lookup`, `describe_node_type` and `execute_blender_code` when present. Each call must be real before reporting its result.

The upstream text sometimes says `look`, `import_asset` or `generate_3d`; these are not guaranteed tool names. Use an available viewport screenshot or headless review shots for visual review. Use the actual supported import/generation tool only when that operation was requested. Never invent a tool or silently switch to a paid asset provider.

For a minimal read-only version probe through the available code tool:

```python
import bpy, json
print(json.dumps({"version": bpy.app.version_string,
                  "file": bpy.data.filepath,
                  "objects": len(bpy.context.scene.objects),
                  "engine": bpy.context.scene.render.engine}))
```

Load modules using verified absolute paths on the Blender host. Import in every call. Inspect operator/node schemas for version-sensitive work. Keep each mutation small and inspect the resulting scene before proceeding.

## Headless Blender

Use the core runner, with `BLENDER_EXE` pointing to an existing executable if discovery fails. The Blender process is independent of the user's open UI. Do not infer it can edit the live scene.

```text
python <skills>/blender-core/scripts/run_in_blender.py --which
python <skills>/blender-core/scripts/run_in_blender.py --blend <input.blend> <script.py> -- <script-flags>
```

Blender processes command arguments in order. Factory startup must precede an input .blend; placing it after the input discards the scene just loaded. Never pass factory startup to a live MCP call. Save a new named output, not the source, unless overwriting is explicitly intended.

## Capability gate

Treat Blender version, Rigify availability, GPU, texture paths, export add-ons, node schemas and destination access as independently verified capabilities. Use a CPU preview when appropriate. A missing renderer, add-on or tool is a reported limitation, not a reason to fabricate success or change the installation unasked.
