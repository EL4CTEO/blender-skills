import os

import bpy
import fixtures as fx
from run_all import TMP, fresh, skill_module


def _reimport_dims(path):
    fresh()
    if path.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path)
    elif path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.wm.usd_import(filepath=path)
    bpy.context.view_layer.update()
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    return {o.name: tuple(round(d, 3) for d in o.dimensions) for o in meshes}, \
        {o.name: tuple(round(s, 3) for s in o.scale) for o in bpy.data.objects if o.type == "ARMATURE"}


def test_all_presets_roundtrip_scale():
    ex = skill_module("blender-export-pipelines", "export_asset")
    for preset in ex.PRESETS:
        fresh()
        fx.cube("SM_Box", size=2, location=(0, 0, 1))
        body, arm = fx.simple_character()
        r = ex.run(preset=preset, objects=["SM_Box", "Char"], out=str(TMP / "exp" / f"{preset}{ex.EXT[ex.PRESETS[preset][0]]}"))
        assert r["ok"], (preset, r)
        f = r["files"][0]
        assert f["kb"] > 0
        if "summary" in f:
            assert f["summary"]["meshes"] == 2 and f["summary"]["skins"] == 1, (preset, f["summary"])
        dims, arm_scales = _reimport_dims(f["file"])
        box = next(v for k, v in dims.items() if k.startswith("SM_Box"))
        assert all(abs(d - 2) < 0.01 for d in box), (preset, dims)
        for s in arm_scales.values():  # no 100x armature scale (Unreal/Roblox symptom)
            assert all(abs(x - 1) < 0.01 or abs(x - 0.01) < 1e-4 for x in s), (preset, s)


def test_batch_export_at_origin():
    ex = skill_module("blender-export-pipelines", "export_asset")
    fx.cube("SM_A", location=(5, 0, 0))
    fx.cube("SM_B", location=(-5, 0, 0))
    r = ex.run(preset="gltf", objects=["SM_A", "SM_B"], out=str(TMP / "batch" / "x.glb"), batch=True)
    names = sorted(os.path.basename(f["file"]) for f in r["files"])
    assert names == ["SM_A.glb", "SM_B.glb"]
    assert tuple(bpy.data.objects["SM_A"].location) == (5, 0, 0)  # restored
