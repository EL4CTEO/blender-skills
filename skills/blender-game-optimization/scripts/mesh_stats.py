"""Budget report: tris/verts per object, materials (draw calls), textures + VRAM, vs a platform budget.

Usage:
  blender -b f.blend -P mesh_stats.py -- [--objects A B] [--budget mobile|roblox|console|pc|vr|web]
  MCP: import mesh_stats; result = mesh_stats.run(budget="mobile")
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

# per-ASSET guidance, not hard engine limits (Roblox: 20k tris/mesh, 10,742 tris/R15 body - Creator Hub)
BUDGETS = {
    "mobile":  {"char_tris": 15000, "prop_tris": 3000, "materials": 2, "tex": 1024, "bones": 75},
    "roblox":  {"char_tris": 10742, "prop_tris": 20000, "materials": 1, "tex": 1024, "bones": None},
    "web":     {"char_tris": 30000, "prop_tris": 10000, "materials": 2, "tex": 2048, "bones": 100},
    "vr":      {"char_tris": 40000, "prop_tris": 10000, "materials": 3, "tex": 2048, "bones": 100},
    "console": {"char_tris": 80000, "prop_tris": 30000, "materials": 4, "tex": 4096, "bones": 250},
    "pc":      {"char_tris": 150000, "prop_tris": 50000, "materials": 6, "tex": 4096, "bones": 300},
}


def _vram(img):
    w, h = img.size
    bpp = 16 if img.is_float else 4
    return w * h * bpp * 4 / 3  # + mip chain, uncompressed upper bound


def run(objects=None, budget=None, **_):
    bx.object_mode()
    obs = bx.objects(objects, types=("MESH",))
    per, mats, imgs = {}, set(), set()
    total_tris = total_verts = 0
    is_char = False
    for ob in obs:
        eo = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = eo.to_mesh()
        me.calc_loop_triangles()
        t, v = len(me.loop_triangles), len(me.vertices)
        eo.to_mesh_clear()
        used = {s.material for s in ob.material_slots if s.material}
        mats |= used
        for m in used:
            for n in m.node_tree.nodes if m.node_tree else []:
                if n.type == "TEX_IMAGE" and n.image:
                    imgs.add(n.image)
        arm = next((m.object for m in ob.modifiers if m.type == "ARMATURE" and m.object), None)
        is_char |= arm is not None
        per[ob.name] = {"tris": t, "verts": v, "materials": len(used),
                        "modifiers": [m.type for m in ob.modifiers],
                        "uv_maps": len(ob.data.uv_layers), "shape_keys":
                        len(ob.data.shape_keys.key_blocks) if ob.data.shape_keys else 0}
        total_tris += t
        total_verts += v
    bones = max((len(m.object.data.bones) for ob in obs for m in ob.modifiers
                 if m.type == "ARMATURE" and m.object), default=0)
    tex = [{"name": i.name, "size": list(i.size), "mb": round(_vram(i) / 2**20, 1)} for i in imgs]
    rep = {"ok": True, "objects": per, "total_tris": total_tris, "total_verts": total_verts,
           "draw_calls_est": sum(p["materials"] or 1 for p in per.values()),
           "unique_materials": len(mats), "textures": tex,
           "texture_vram_mb_uncompressed": round(sum(_vram(i) for i in imgs) / 2**20, 1),
           "bones": bones, "kind": "character" if is_char else "prop"}
    if budget:
        b = BUDGETS[budget]
        lim = b["char_tris"] if is_char else b["prop_tris"]
        over = []
        if total_tris > lim:
            over.append(f"tris {total_tris} > {lim}")
        if len(mats) > b["materials"]:
            over.append(f"materials {len(mats)} > {b['materials']} (merge/atlas)")
        big = [t["name"] for t in tex if max(t["size"]) > b["tex"]]
        if big:
            over.append(f"textures > {b['tex']}px: {big}")
        if b["bones"] and bones > b["bones"]:
            over.append(f"bones {bones} > {b['bones']}")
        rep["budget"] = {"name": budget, "limits": b, "over": over, "pass": not over}
    return rep


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__), save=False)
    p.add_argument("--budget", choices=list(BUDGETS), default=None)
    bx.cli(run, p)
