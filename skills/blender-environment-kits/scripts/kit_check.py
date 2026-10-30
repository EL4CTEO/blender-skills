"""Validate modular kit pieces so they snap together: applied transforms, footprint on the grid,
pivot convention, open edges only on the piece's outer faces (seams), consistent texel density,
naming. --fix applies rotation/scale and moves each origin to the pivot convention.

Pivot conventions: corner = bounding-box min (x, y, z), the usual kit/Roblox choice;
bottom-center = center of the bottom face; center = bounding-box center.
Usage:
  blender -b f.blend -P kit_check.py -- [--objects SM_Wall_4m SM_Floor_4m] [--grid 0.5]
      [--pivot corner|bottom-center|center] [--texture 2048] [--tol 0.001] [--prefix SM_] [--fix]
      [--save out.blend]
  MCP: import kit_check; print(kit_check.run(objects=["SM_Wall_4m"], grid=0.5, fix=True))
"""
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _on_grid(v, grid, tol):
    return abs(v / grid - round(v / grid)) * grid <= tol


def _pivot_target(lo, hi, pivot):
    if pivot == "corner":
        return Vector(lo)
    c = (Vector(lo) + Vector(hi)) / 2
    return Vector((c.x, c.y, lo[2])) if pivot == "bottom-center" else c


def _texel_density(ob, texture):
    me = ob.data
    if not me.uv_layers:
        return None
    me.calc_loop_triangles()
    uv = me.uv_layers.active.uv
    mw = ob.matrix_world
    a3 = a2 = 0.0
    for t in me.loop_triangles:
        p = [mw @ me.vertices[v].co for v in t.vertices]
        q = [Vector((*uv[li].vector, 0)) for li in t.loops]
        a3 += (p[1] - p[0]).cross(p[2] - p[0]).length / 2
        a2 += (q[1] - q[0]).cross(q[2] - q[0]).length / 2
    return math.sqrt(a2 / a3) * texture if a3 > 0 and a2 > 0 else None


def _fix(ob, pivot):
    """Apply rotation+scale, then move the origin to the pivot without moving the geometry."""
    me = ob.data
    loc, rot, scl = ob.matrix_world.decompose()
    me.transform(Matrix.LocRotScale(None, rot, scl))
    ob.matrix_world = Matrix.Translation(loc)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    off = _pivot_target(co.min(0), co.max(0), pivot)
    me.transform(Matrix.Translation(-off))
    ob.location = loc + off
    me.update()


def run(objects=None, grid=0.5, pivot="corner", texture=2048, tol=0.001, prefix="SM_", fix=False, **_):
    bx.object_mode()
    if pivot not in ("corner", "bottom-center", "center"):
        raise ValueError("--pivot must be corner, bottom-center or center")
    obs = [o for o in bx.objects(objects) if o.type == "MESH"]
    pieces, tds = {}, {}
    for ob in obs:
        if fix:
            _fix(ob, pivot)
        e, w = [], []
        loc, rot, scl = ob.matrix_world.decompose()
        if any(abs(s - 1) > 1e-4 for s in scl):
            e.append(f"unapplied scale {bx.r(list(scl), 3)}")
        if rot.angle > 1e-4:
            e.append(f"unapplied rotation {round(math.degrees(rot.angle), 2)} deg")
        me = ob.data
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        lo, hi = co.min(0), co.max(0)
        dims = hi - lo
        # lengths must tile; anything thinner than one cell is a thickness (walls, trims) and may be off-grid
        bad_dims = [round(float(d), 4) for d in dims[:2] if d >= grid - tol and not _on_grid(float(d), grid, tol)]
        if bad_dims:
            e.append(f"footprint {bx.r(dims.tolist(), 4)} m is not a multiple of the {grid} m grid")
        if not _on_grid(float(dims[2]), grid, tol):
            w.append(f"height {round(float(dims[2]), 4)} m is off-grid (fine for props, not for walls)")
        tgt = _pivot_target(lo, hi, pivot)
        if tgt.length > tol:
            e.append(f"pivot is not at the {pivot}: offset {bx.r(list(tgt), 4)} m (--fix)")
        if not all(_on_grid(float(c), grid, tol) for c in loc[:2]):
            w.append(f"placed off-grid at {bx.r(list(loc), 4)}")
        bm = bmesh.new()
        bm.from_mesh(me)
        open_v = {v for ed in bm.edges if ed.is_boundary for v in ed.verts}
        axes = [i for i in range(3) if dims[i] > tol]  # a flat tile's Z faces would contain every vertex
        inner = [v for v in open_v if not any(abs(v.co[i] - b[i]) <= tol for b in (lo, hi) for i in axes)]
        seam = [v.co.copy() for v in open_v if v not in set(inner)]
        bm.free()
        if inner:
            e.append(f"{len(inner)} open-edge verts inside the piece (holes; seams must lie on its outer faces)")
        if seam and not all(_on_grid(float(c[i]), grid, tol) for c in seam for i in range(2)
                            if abs(c[i] - lo[i]) > tol and abs(c[i] - hi[i]) > tol):
            w.append("seam verts off the grid: neighbours won't weld")
        if prefix and not ob.name.startswith(prefix):
            w.append(f"name lacks {prefix!r} prefix")
        td = _texel_density(ob, texture)
        if td is None:
            w.append("no UVs")
        else:
            tds[ob.name] = td
        pieces[ob.name] = {"dims_m": bx.r(dims.tolist(), 4), "tris": bx.mesh_tris(ob, False),
                           "texel_px_per_m": round(td, 1) if td else None, "errors": e, "warnings": w}
    if len(tds) > 1:
        med = float(np.median(list(tds.values())))
        for n, td in tds.items():
            if abs(td - med) / med > 0.25:
                pieces[n]["warnings"].append(f"texel density {round(td)} px/m vs kit median {round(med)} (>25% off)")
    ok = not any(p["errors"] for p in pieces.values())
    return {"ok": True, "pass": ok, "grid_m": grid, "pivot": pivot, "fixed": fix, "pieces": pieces}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--grid", type=float, default=0.5)
    p.add_argument("--pivot", default="corner", choices=("corner", "bottom-center", "center"))
    p.add_argument("--texture", type=int, default=2048, help="texture px for texel density")
    p.add_argument("--tol", type=float, default=0.001)
    p.add_argument("--prefix", default="SM_")
    p.add_argument("--fix", action="store_true")
    bx.cli(run, p)
