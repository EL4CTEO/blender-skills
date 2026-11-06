"""Measure (and optionally set) texel density in px/m for objects' active UV map.

Reports per-object area-weighted mean, min/max over islands, and spread (max/min).
--set scales every island to the target density (about its UV centre) then repacks
without rescaling; reports overflow if it no longer fits in 0-1.
Usage:
  blender -b f.blend -P texel_density.py -- [--objects A B] [--res 2048] [--set 512] [--margin-px 8] [--save out.blend]
  MCP: import texel_density; result = texel_density.run(objects=["SM_Crate"], res=2048)
"""
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _islands(bm, uv):
    """UV islands as lists of faces (connected through shared UV coords)."""
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            isl.append(cur)
            for l in cur.loops:
                rad = l.link_loop_radial_next
                nf = rad.face
                if nf.index in seen or rad == l:
                    continue
                # same UV on both sides of the edge -> connected
                a1, a2 = l[uv].uv, l.link_loop_next[uv].uv
                b1, b2 = rad.link_loop_next[uv].uv, rad[uv].uv
                if (a1 - b1).length < 1e-5 and (a2 - b2).length < 1e-5:
                    seen.add(nf.index)
                    stack.append(nf)
        out.append(isl)
    return out


def _uv_area(f, uv):
    pts = [l[uv].uv for l in f.loops]
    return abs(sum(pts[i].x * pts[i - 1].y - pts[i - 1].x * pts[i].y for i in range(len(pts)))) / 2


def _measure(ob, res):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    uv = bm.loops.layers.uv.active
    if uv is None:
        bm.free()
        return None, None, None
    bm.faces.ensure_lookup_table()
    isl_d = []
    tot_w = tot_uv = 0.0
    for isl in _islands(bm, uv):
        wa = sum(f.calc_area() for f in isl)
        ua = sum(_uv_area(f, uv) for f in isl)
        tot_w, tot_uv = tot_w + wa, tot_uv + ua
        if wa > 1e-10:
            isl_d.append((math.sqrt(ua / wa) * res, [f.index for f in isl]))
    mean = math.sqrt(tot_uv / tot_w) * res if tot_w > 1e-10 else 0.0
    return bm, mean, isl_d


def run(objects=None, res=2048, set=None, margin_px=8, **_):  # noqa: A002 (CLI name)
    bx.object_mode()
    out = {}
    for ob in bx.objects(objects):
        bm, mean, isl = _measure(ob, res)
        if bm is None:
            out[ob.name] = {"error": "no UV map"}
            continue
        bm.free()
        dens = [d for d, _ in isl] or [0]
        rec = {"px_per_m": round(mean, 1), "island_min": round(min(dens), 1),
               "island_max": round(max(dens), 1), "islands": len(isl),
               "spread": round(max(dens) / max(min(dens), 1e-6), 2)}
        if set:
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            uv = bm.loops.layers.uv.active
            bm.faces.ensure_lookup_table()
            for d, faces in isl:
                k = set / max(d, 1e-6)
                loops = [l for i in faces for l in bm.faces[i].loops]
                c = sum((l[uv].uv for l in loops), loops[0][uv].uv * 0) / len(loops)
                for l in loops:
                    l[uv].uv = c + (l[uv].uv - c) * k
            bm.to_mesh(ob.data)
            bm.free()
            bx.select_only([ob])
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.select_all(action="SELECT")
            bpy.ops.uv.pack_islands(scale=False, rotate=True, shape_method="AABB", margin_method="FRACTION",
                                    margin=margin_px / res)
            bpy.ops.object.mode_set(mode="OBJECT")
            bm, mean2, isl2 = _measure(ob, res)
            uvl = ob.data.uv_layers.active.data
            co = [d.uv for d in uvl]
            over = any(u.x > 1.0001 or u.y > 1.0001 or u.x < -1e-4 or u.y < -1e-4 for u in co)
            bm.free()
            rec["after"] = {"px_per_m": round(mean2, 1), "fits_0_1": not over}
            if over:
                rec["after"]["hint"] = "lower density, raise --res, or split into more texture sets/UDIMs"
        out[ob.name] = rec
    return {"ok": True, "res": res, "objects": out}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--res", type=int, default=2048)
    p.add_argument("--set", type=float, default=None, help="target px/m")
    p.add_argument("--margin-px", type=int, default=8)
    bx.cli(run, p)
