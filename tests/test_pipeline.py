import os

import bpy
import fixtures as fx
from run_all import ROOT, TMP, fresh, skill_module


def test_batch_convert_report_script_shard():
    src = TMP / "batch_src"
    src.mkdir(exist_ok=True)
    for i, ext in enumerate(("fbx", "glb", "blend")):
        fresh()
        fx.cube(f"SM_Item{i}")
        p = str(src / f"item{i}.{ext}")
        if ext == "fbx":
            bpy.ops.export_scene.fbx(filepath=p)
        elif ext == "glb":
            bpy.ops.export_scene.gltf(filepath=p, export_format="GLB")
        else:
            bpy.ops.wm.save_as_mainfile(filepath=p)
    bp = skill_module("blender-pipeline-automation", "batch_process")
    assert len(bp.gather(str(src))) == 3
    r = bp.run(inp=str(src), op="convert", to="obj", out=str(TMP / "batch_out"))
    assert r["ok"] and r["files"] == 3, r
    assert {"item0.obj", "item1.obj", "item2.obj"} <= set(os.listdir(TMP / "batch_out"))
    r = bp.run(inp=str(src / "*.glb"), op="report")
    assert r["results"][0]["tris"] == 12
    qa = str(ROOT / "skills/blender-asset-qa/scripts/qa_check.py")
    r = bp.run(inp=str(src), op="script", script=qa, kwargs={"uv": False}, shard="0/2")
    assert r["files"] == 2 and all("pass" in x["result"] for x in r["results"]), r
