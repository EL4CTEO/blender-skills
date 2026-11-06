# Official Blender MCP (Blender Lab add-on)

The skills target the official Blender MCP server: Blender runs with the MCP add-on enabled, and the agent calls the tools below. Tool names may carry a client prefix (for example `mcp__blender__execute_blender_code`).

## Tools
| Need | Tool | Notes |
|---|---|---|
| Run bpy in the open Blender | `execute_blender_code(code)` | Return data by assigning a JSON-serialisable dict to `result`; the reply is `{"status", "result", "stdout"}` (`print` goes to `stdout`). Each call gets a fresh namespace. Runs in the user's session: changes are live and there is no undo step for the agent, so save or back up first. |
| Run bpy on a file in a background Blender | `execute_blender_code_for_cli(blend_file, code)` | Needs `BLENDER_PATH` pointing at the Blender executable (macOS: `/Applications/Blender.app/Contents/MacOS/Blender`). Same `result` rule. Without it, use `blender-core/scripts/run_in_blender.py`. |
| Scene overview | `get_objects_summary` | Collections, objects, parents, visibility. Read this before touching anything. |
| One object in detail | `get_object_detail_summary` | Transforms, modifiers, materials, data. |
| File info | `get_blendfile_summary_path_info`, `_datablocks`, `_missing_files`, `_of_linked_libraries`, `_usage_guess` | Each has a `_for_cli` variant for files that are not open. |
| See the UI | `get_screenshot_of_window_as_image`, `get_screenshot_of_area_as_image(area_ui_type)`, `get_screenshot_of_window_as_json` | Shows exactly what the user sees, including bones, overlays and edit mode. |
| Frame an object in the viewport | `jump_to_view3d_object_by_name(name, allow_edits=False)` | Use before a `VIEW_3D` screenshot. Also `jump_to_tab_by_name`, `jump_to_tab_by_space_type`. |
| Render | `render_viewport_to_path(output_path)` (current render settings), `render_thumbnail_to_path(output_path)` (small, quick) | Uses the scene camera; set one first. |
| API / manual lookup | `search_api_docs`, `get_python_api_docs`, `search_manual_docs` | Bundled with the server; use them when code fails with AttributeError/TypeError. |

## Replacing `look`
Some skills were first written for a server with a `look` tool. With the official server, use:

| Old call | Official-MCP equivalent |
|---|---|
| `look(mode="angles")`, shading solid/material | `review_shots.run(objects=[...], mode="solid"` or `"material"` or `"texture")` |
| `look` wireframe | `review_shots.run(objects=[...], mode="wire")` |
| `look` xray (mesh internals) | `review_shots.run(objects=[...], mode="xray")` (inner parts show through; a closed body alone looks only slightly faded) |
| `look(mode="frames", frames=[...])` / `frame_count=N` | `review_shots.run(objects=[...], frames=[...])` or `frame_count=N` |
| Bones, joint placement, overlays, edit mode | `jump_to_view3d_object_by_name` + `get_screenshot_of_area_as_image(area_ui_type="VIEW_3D")`. Workbench renders don't draw armatures. |

```python
import sys; sys.path.insert(0, r"<skills_dir>/blender-asset-qa/scripts")
import review_shots; result = review_shots.run(objects=["Hero"], mode="texture", out="/tmp/hero_review.png")
```
Then open `result["sheet"]` with your image reader. `result["order"]` gives the tile order (left to right, top to bottom). The script restores every render and shading setting it touches and removes its temporary camera.

## Not in the official server
- **Asset search/import (Poly Haven, Sketchfab, AI generators)**: there is no `search_assets`/`import_asset`. Download the file yourself (Poly Haven has a public API at `https://api.polyhaven.com`) or ask the user for it, then load it with bpy (`bpy.data.images.load`, `bpy.ops.wm.append`, importers).
- **Long jobs** (big renders, bakes, simulations) block Blender's UI while `execute_blender_code` runs. Prefer `execute_blender_code_for_cli` or `run_in_blender.py` on a saved copy for heavy work.
