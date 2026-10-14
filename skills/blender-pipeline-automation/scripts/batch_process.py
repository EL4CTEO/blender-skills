"""Batch over many files in one Blender process: convert formats, inventory report, or run any
skill script's run(**kwargs) per file and save. Sharding for parallel processes.

Inputs: .blend .fbx .glb .gltf .obj .stl .ply .usd .usda .usdc .usdz .abc (folder, glob, or list)
Usage:
  blender -b -P batch_process.py -- --in "assets/**/*.fbx" --op convert --to glb --out export/
  blender -b -P batch_process.py -- --in assets/ --op report
  blender -b -P batch_process.py -- --in "src/*.blend" --op script --script skills/blender-asset-qa/scripts/qa_check.py
      --kwargs '{"profile":"game"}' [--save-to out/]
  parallel: run N processes with --shard 0/4, 1/4, 2/4, 3/4
  MCP (careful: replaces the open file): import batch_process; batch_process.run(inp="C:/assets", op="report")
Prints one JSON line per file (@@JSON@@ when run via run_in_blender.py) and a summary.
"""
import glob
import importlib.util
import json
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

IMPORTERS = {
    ".fbx": lambda p: bpy.ops.import_scene.fbx(filepath=p),
    ".glb": lambda p: bpy.ops.import_scene.gltf(filepath=p),
    ".gltf": lambda p: bpy.ops.import_scene.gltf(filepath=p),
    ".obj": lambda p: bpy.ops.wm.obj_import(filepath=p),
    ".stl": lambda p: bpy.ops.wm.stl_import(filepath=p),
    ".ply": lambda p: bpy.ops.wm.ply_import(filepath=p),
    ".abc": lambda p: bpy.ops.wm.alembic_import(filepath=p),
    **{e: (lambda p: bpy.ops.wm.usd_import(filepath=p)) for e in (".usd", ".usda", ".usdc", ".usdz")},
}
EXPORTERS = {
    "glb": lambda p, kw: bpy.ops.export_scene.gltf(filepath=p, export_format="GLB", **kw),
    "fbx": lambda p, kw: bpy.ops.export_scene.fbx(filepath=p, **({"add_leaf_bones": False} | kw)),
    "obj": lambda p, kw: bpy.ops.wm.obj_export(filepath=p, **kw),
    "stl": lambda p, kw: bpy.ops.wm.stl_export(filepath=p, **kw),
    "usd": lambda p, kw: bpy.ops.wm.usd_export(filepath=p, **kw),
    "usdz": lambda p, kw: bpy.ops.wm.usd_export(filepath=p, **kw),
    "blend": lambda p, kw: bpy.ops.wm.save_as_mainfile(filepath=p, copy=True),
}


def gather(inp):
    items = inp if isinstance(inp, (list, tuple)) else [inp]
    files = []
    for it in items:
        it = bpy.path.abspath(it)
        if os.path.isdir(it):
            files += [os.path.join(r, f) for r, _, fs in os.walk(it) for f in fs]
        else:
            files += glob.glob(it, recursive=True)
    exts = set(IMPORTERS) | {".blend"}
    return sorted({f for f in files if os.path.splitext(f)[1].lower() in exts})


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        IMPORTERS[ext](path)


def inventory():
    dg = bpy.context.evaluated_depsgraph_get()
    tris, mats, dims = 0, set(), None
    for ob in bpy.context.scene.objects:
        if ob.type == "MESH":
            eo = ob.evaluated_get(dg)
            me = eo.to_mesh()
            me.calc_loop_triangles()
            tris += len(me.loop_triangles)
            eo.to_mesh_clear()
            mats |= {s.material.name for s in ob.material_slots if s.material}
    missing = [i.name for i in bpy.data.images if i.source == "FILE" and not i.packed_file
               and not os.path.exists(bpy.path.abspath(i.filepath))]
    kinds = {}
    for ob in bpy.context.scene.objects:
        kinds[ob.type] = kinds.get(ob.type, 0) + 1
    return {"objects": kinds, "tris": tris, "materials": len(mats), "images": len(bpy.data.images),
            "missing_images": missing[:10], "actions": len(bpy.data.actions)}


def _module(path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec = importlib.util.spec_from_file_location("batch_target", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(inp=None, op="report", to="glb", out="", script=None, kwargs=None, save_to=None, shard=None,
        set=None, stream=False, **_):  # noqa: A002
    files = gather(inp)
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        files = files[i::n]
    out_dir = os.path.abspath(bpy.path.abspath(out)) if out else None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    kw = json.loads(kwargs) if isinstance(kwargs, str) else (kwargs or {})
    exp_kw = dict(x.split("=", 1) for x in set or [])
    exp_kw = {k: {"true": True, "false": False}.get(v.lower(), v) for k, v in exp_kw.items()}
    mod = _module(script) if op == "script" else None
    results, t0 = [], time.time()
    for f in files:
        rec = {"file": f}
        t = time.time()
        try:
            load(f)
            if op == "report":
                rec.update(inventory())
            elif op == "convert":
                name = os.path.splitext(os.path.basename(f))[0] + "." + ("usdz" if to == "usdz" else to)
                dst = os.path.join(out_dir or os.path.dirname(f), name)
                res = EXPORTERS[to](dst, exp_kw)
                rec.update(out=dst, ok=res == {"FINISHED"} and os.path.exists(dst))
            elif op == "script":
                rec["result"] = mod.run(**kw)
                if save_to:
                    os.makedirs(bpy.path.abspath(save_to), exist_ok=True)
                    dst = os.path.join(bpy.path.abspath(save_to), os.path.splitext(os.path.basename(f))[0] + ".blend")
                    bpy.ops.wm.save_as_mainfile(filepath=dst, copy=True)
                    rec["saved"] = dst
            rec.setdefault("ok", True)
        except Exception as e:
            rec.update(ok=False, error=f"{type(e).__name__}: {e}")
        rec["sec"] = round(time.time() - t, 2)
        results.append(rec)
        if stream:  # CLI: one JSON line per file as it finishes
            bx.emit(rec)
    return {"ok": all(r.get("ok") for r in results), "op": op, "files": len(files),
            "failed": [r["file"] for r in results if not r.get("ok")], "sec": round(time.time() - t0, 1),
            "results": "streamed" if stream else results}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--in", dest="inp", nargs="+", required=True)
    p.add_argument("--op", default="report", choices=["report", "convert", "script"])
    p.add_argument("--to", default="glb", choices=list(EXPORTERS))
    p.add_argument("--out", default="")
    p.add_argument("--script", default=None)
    p.add_argument("--kwargs", default=None, help="JSON dict passed to the script's run()")
    p.add_argument("--save-to", default=None)
    p.add_argument("--shard", default=None, help="i/n")
    p.add_argument("--set", nargs="*", default=None, help="exporter kwargs key=value")
    p.set_defaults(stream=True)
    bx.cli(run, p)
