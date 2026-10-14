import os

import bpy
import fixtures as fx
from run_all import TMP, skill_module


def test_scene_audit_flags_and_fixes():
    m = skill_module("blender-scene-setup", "scene_audit")
    a = fx.cube("Cube")
    a.scale = (2, 2, 2)
    b = fx.cube("SM_Crate.001", location=(3, 0, 0))
    b.rotation_euler = (0.3, 0, 0)
    bpy.data.materials.new("Orphan")
    r = m.run()
    assert "Cube" in r["issues"]["default_names"]
    assert "SM_Crate.001" in r["issues"]["duplicate_suffix"]
    assert "Cube" in r["issues"]["unapplied_scale"] and "SM_Crate.001" in r["issues"]["rotated"]
    assert r["orphans"] >= 1
    bpy.context.view_layer.update()
    dims = tuple(a.dimensions)
    r = m.run(fix=["purge", "scale"])
    assert tuple(a.scale) == (1, 1, 1) and all(abs(x - y) < 1e-5 for x, y in zip(a.dimensions, dims))
    assert "Orphan" not in bpy.data.materials


def test_collection_exporter_snippet():
    col = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(col)
    col.objects.link(fx.cube("SM_Crate"))
    with bpy.context.temp_override(collection=col):
        bpy.ops.collection.exporter_add(name="IO_FH_gltf2")
    ex = col.exporters[-1]
    out = str(TMP / "SM_Crate.glb")
    ex.export_properties.filepath = out
    with bpy.context.temp_override(collection=col):
        assert bpy.ops.collection.exporter_export(index=len(col.exporters) - 1) == {"FINISHED"}
    assert os.path.getsize(out) > 0
