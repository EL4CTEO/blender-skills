# bpy migration: 4.x → 5.2 (what LLM memory / old tutorials get wrong)

Each row was verified against Blender 5.2.2. Format: **old → new** (version).

## Core / properties
| Old | New |
|---|---|
| `scene["cycles"]`, dict access to `bpy.props` values | attribute access only; ID-props and RNA props are separate (5.0) |
| `bpy.props` `get` without `set` for read-only | `options={'READ_ONLY'}`; `set` without `get` is an error (5.0) |
| `get_transform`/`set_transform` | new prop callbacks that keep default storage (5.0) |
| user site-packages auto-loaded | no longer loaded by default (5.1) |
| Python 3.11 | Python 3.13 (5.1) |
| — | `bpy.data.all_ids` iterates over every ID (5.2) |
| — | `gpu.init()` required for `gpu` in `--background` (5.2) |
| IDProperty nesting unlimited | capped at 1024 levels (5.2) |
| mathutils float64 buffers | float32 buffers; numpy views are non-contiguous (5.0) |

## Mesh / modeling
| Old | New |
|---|---|
| `mesh.use_auto_smooth`, `auto_smooth_angle` | removed (4.1). Use `bpy.ops.object.shade_smooth_by_angle(angle=…)` or the "Smooth by Angle" modifier asset (`shade_auto_smooth`) |
| `mesh.calc_normals_split()`, `loop.normal` | `mesh.corner_normals` (read-only), `mesh.normals_domain` (4.1) |
| custom normals need auto smooth | they work directly: `mesh.normals_split_custom_set(...)` (4.1) |
| face maps | removed. Use a boolean face attribute (4.0) |
| Boolean solver `FAST` | `FLOAT`. Solvers: `EXACT` (default), `FLOAT`, `MANIFOLD` (4.5+) (5.0) |
| per-UV-map selection, `BMLoopUV.select*` | shared `.uv_select_*` attributes; `bm.uv_select_flush()` etc. (5.0) |
| UV pin auto-creates attribute | use the `*_ensure()` functions (5.0) |
| `brush.sculpt_tool` | `brush.sculpt_brush_type` (5.0); brushes are assets (4.3) |
| `tool_settings.unified_paint_settings` | `tool_settings.sculpt.unified_paint_settings` (mode-specific) (5.0) |
| radial symmetry on tool settings | `mesh.radial_symmetry` (5.0) |
| `brush.use_airbrush/use_anchor/use_space/...` | `brush.stroke_method` enum (5.1) |
| `brush.use_automasking_*`, `automasking_*` | `brush.mesh_automasking_settings.*` (5.2) |

## Nodes
| Old | New |
|---|---|
| `ng.inputs.new()` / `ng.outputs.new()` | `ng.interface.new_socket(name, in_out='INPUT', socket_type='NodeSocketFloat')` (4.0) |
| `mod["Socket_2"] = 1.0`, `mod["Socket_2_use_attribute"]` | `mod.properties.inputs.Socket_2.value = 1.0`; `.type = "ATTRIBUTE"`; `.attribute_name` (5.2). Use `getattr(mod.properties.inputs, sock.identifier)` |
| Compare / Random Value socket identifiers | changed (5.2): look up by name, not identifier |
| `scene.node_tree`, `scene.use_nodes = True` | `scene.compositing_node_group = bpy.data.node_groups.new(n, "CompositorNodeTree")` (5.0) |
| `material.use_nodes = True` | deprecated (5.0). New materials already have Principled + Output. Same for `world.use_nodes` |
| File Output `base_path`, `file_slots`, `layer_slots` | `directory`, `file_name`, `file_output_items` (5.0) |
| `CompositorNodeGamma`, `...MixRGB`, etc. | shader-node equivalents (`ShaderNodeGamma`, `ShaderNodeMix`) (5.0) |
| Color node output "RGBA" | "Color" (5.0) |
| Principled `Subsurface`, `Specular`, `Transmission`, `Coat`/`Clearcoat`, `Sheen`, `Emission` | `Subsurface Weight`, `Specular IOR Level`, `Transmission Weight`, `Coat Weight`, `Sheen Weight`, `Emission Color` (4.0) |
| — | Principled `Thin Wall` input (5.2); `Diffuse Roughness`, `Thin Film Thickness/IOR` (4.2–4.3) |
| `SpaceNodeEditor.geometry_nodes_type` | `node_tree_sub_type` (5.0) |
| Point Density texture node | removed (5.0) |

## Materials / rendering
| Old | New |
|---|---|
| engine `BLENDER_EEVEE_NEXT` (4.2–4.5) | `BLENDER_EEVEE` (5.0) |
| `material.blend_method`, `shadow_method` | `material.surface_render_method` = `DITHERED` / `BLENDED`; `shadow_method` removed (4.2). Use `visible_shadow` on the object |
| `scene.eevee.use_gtao`, `gtao_distance` | removed; `view_layer.eevee.ambient_occlusion_distance` (5.0) |
| render pass names `DiffCol`, `Z`, ... | `Diffuse Color`, `Depth`, ... (5.0) |
| `image_settings.file_format = "FFMPEG"` alone | set `image_settings.media_type` (`IMAGE`/`MULTI_LAYER_IMAGE`/`VIDEO`) **before** `file_format` (5.0) |
| Filmic default | AgX default (4.0). Views: Standard, AgX, Khronos PBR Neutral, ACES 1.3/2.0, Filmic, ... |
| — | Cycles texture cache: `scene.render.use_texture_cache`, `use_auto_generate_texture_cache` (.tx) (5.2) |
| `bgl`, `Image.bindcode`, GLSL-source shaders | `gpu` module, `gpu.texture.from_image()` (5.0) |

## Animation / rigging
| Old | New |
|---|---|
| `action.fcurves`, `action.groups`, `action.id_root` | slotted/layered actions. `cb = anim_utils.action_ensure_channelbag_for_slot(action, slot)` → `cb.fcurves.new/ensure/find`, `cb.groups`; `slot.target_id_type` (removed in 5.0; slots since 4.4) |
| `fcurves.new(path, index, action_group)` | `cb.fcurves.new(path, index=0, group_name="")` |
| assigning `animation_data.action` was enough | also set/check `animation_data.action_slot` (auto-picked on assign if suitable) |
| `ANIM_OT_convert_legacy_action` | removed. All actions are layered (5.1) |
| `armature.layers`, `bone.layers`, bone groups | bone collections: `arm.collections.new("FK")`, `bcoll.assign(bone)`, `bone.color.palette`, `pose_bone.color` (4.0) |
| `bone.select`, `select_head/tail` | removed from Bone; use `pose_bone.select` / `edit_bone.select*` (5.0) |
| `context.space_data.action` | removed (5.0) |

## Add-ons / UI / misc
| Old | New |
|---|---|
| `bl_info` dict add-on | extension with `blender_manifest.toml` (4.2). Legacy add-ons still load |
| `UILayout.template_list(columns=)` | no effect (deprecated 5.1) |
| `UIList.layout_type = "GRID"` | removed (5.0) |
| `AssetHandle`, `context.active_file` (asset shelf) | `AssetRepresentation`, `context.asset` (5.0) |
| `GPencilStroke`, `scene.grease_pencil` (annotations) | `AnnotationStroke`, `scene.annotation` (5.0) |
| `GreasePencilv3`, `bpy.data.grease_pencils_v3` | `GreasePencil`, `bpy.data.grease_pencils` (5.0) |
| VSE `frame_final_start/end/duration` | `left_handle`, `right_handle`, `duration` (5.1; old names deprecated) |
| VSE uses `context.scene` | `context.sequencer_scene` (5.0) |
| USD export `export_textures`, `visible_objects_only` | removed (5.0) |
| `PreferencesFilePaths.active_asset_library` index == `asset_libraries` index | offset: list starts with "All Libraries", "Essentials" (5.2) |
| log output format | changed (5.0). Don't regex-parse the render progress |

When something is missing: `dir(obj)`, `T.bl_rna.properties.keys()`, `T.bl_rna.functions.keys()`, or `op.get_rna_type().properties` show the truth faster than docs.
