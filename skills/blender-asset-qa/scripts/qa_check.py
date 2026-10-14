"""Mesh/asset QA: z-fighting, detached parts, normals, topology, transforms, UVs, weights.

Pass the objects of ONE asset (they are checked together: islands far from all others = floating).
Usage:
  blender -b f.blend -P qa_check.py -- [--objects A B] [--profile game|render|print|roblox]
      [--eps 0.001] [--tol 0.002] [--no-modifiers] [--max-tris 300000]
  MCP: import qa_check; print(qa_check.run(objects=["Chair"], profile="game"))
Returns {"pass": bool, "errors": [...], "warnings": [...], "objects": {name: metrics}}.
"""
import math
import os
import sys
from collections import Counter, defaultdict

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

# check -> severity per profile ("e" error, "w" warning, None skip)
PROFILES = {
    #               zfight floating inverted inconsist nonmanif boundary degen dupes ngons scale uv  weights
    "game":   dict(zf="e", fl="e", inv="e", inc="e", nm="w", bd=None, dg="e", dup="w", ng="w", sc="e", uv="e", wt="e"),
    "render": dict(zf="e", fl="e", inv="w", inc="w", nm=None, bd=None, dg="w", dup="w", ng=None, sc="w", uv="w", wt="w"),
    "print":  dict(zf="e", fl="e", inv="e", inc="e", nm="e", bd="e", dg="e", dup="e", ng=None, sc="w", uv=None, wt=None),
    "roblox": dict(zf="e", fl="e", inv="e", inc="e", nm="w", bd="w", dg="e", dup="w", ng="e", sc="e", uv="e", wt="e"),
}
TRI_LIMIT = {"roblox": 20000}


def _mesh_world(ob, use_mods):
    """bmesh of the (evaluated) object in world space, triangulated copy kept separately."""
    bm = bmesh.new()
    if use_mods:
        dg = bpy.context.evaluated_depsgraph_get()
        bm.from_object(ob, dg)
    else:
        bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def _islands(bm):
    parent = list(range(len(bm.verts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in bm.edges:
        a, b = find(e.verts[0].index), find(e.verts[1].index)
        if a != b:
            parent[a] = b
    roots = [find(i) for i in range(len(bm.verts))]
    remap = {r: n for n, r in enumerate(dict.fromkeys(roots))}
    return [remap[r] for r in roots]


def _point_in_tri(p, a, b, c, n):
    for u, v in ((a, b), (b, c), (c, a)):
        if (v - u).cross(p - u).dot(n) < -1e-9:
            return False
    return True


def _uv_stats(ob, bm_local):
    me = ob.data
    if not me.uv_layers:
        return {"uv_maps": 0}
    uv = bm_local.loops.layers.uv.active
    oob = total = zero = 0
    grid, n = defaultdict(set), 128
    step = max(1, len(bm_local.faces) // 30000)  # sample huge meshes
    for f in list(bm_local.faces)[::step]:
        pts = [l[uv].uv.copy() for l in f.loops]
        for p in pts:
            total += 1
            if p.x < -1e-4 or p.y < -1e-4 or p.x > 1.0001 or p.y > 1.0001:
                oob += 1
        a2 = sum(pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y
                 for i in range(len(pts)))
        if abs(a2) < 1e-12:
            zero += 1
            continue
        # coarse raster of face bbox cells whose centre is inside the polygon (fan triangles)
        xs, ys = [p.x for p in pts], [p.y for p in pts]
        for gx in range(max(0, int(min(xs) * n)), min(n, int(max(xs) * n) + 1)):
            for gy in range(max(0, int(min(ys) * n)), min(n, int(max(ys) * n) + 1)):
                c = Vector(((gx + .5) / n, (gy + .5) / n))
                for i in range(1, len(pts) - 1):
                    t = (pts[0], pts[i], pts[i + 1])
                    d = [(t[(k + 1) % 3] - t[k]).to_3d().cross((c - t[k]).to_3d()).z for k in range(3)]
                    if all(x >= 0 for x in d) or all(x <= 0 for x in d):
                        grid[(gx, gy)].add(f.index)
                        break
    used = len(grid)
    overlap = sum(1 for s in grid.values() if len(s) > 1)
    return {"uv_maps": len(me.uv_layers), "uv_oob_pct": round(100 * oob / max(total, 1), 2),
            "uv_zero_area_faces": zero, "uv_overlap_pct": round(100 * overlap / max(used, 1), 2),
            "uv_coverage_pct": round(100 * used / n / n, 1)}


def run(objects=None, profile="game", eps=0.001, tol=0.002, no_modifiers=False, max_tris=300000,
        uv=True, **_):
    bx.object_mode()
    sev = PROFILES[profile]
    obs = [o for o in bx.objects(objects) if o.type == "MESH"]
    if not obs:
        raise ValueError("no mesh objects to check")
    errors, warnings, per = [], [], {}

    def flag(key, msg):
        s = sev.get(key)
        if s == "e":
            errors.append(msg)
        elif s == "w":
            warnings.append(msg)

    # ---- gather world-space triangles of all objects --------------------------------
    verts, tris, tri_meta = [], [], []      # tri_meta: (obj_i, island_gid, normal)
    island_info = {}                         # gid -> dict(ob, verts, tris, bbox)
    gid_base = 0
    min_z = math.inf
    for oi, ob in enumerate(obs):
        bm = _mesh_world(ob, not no_modifiers)
        m = {}
        isl = _islands(bm)
        n_isl = max(isl) + 1 if isl else 0
        base_v = len(verts)
        verts.extend(v.co.copy() for v in bm.verts)
        if bm.verts:
            min_z = min(min_z, min(v.co.z for v in bm.verts))
        # topology
        ecount = Counter(len(e.link_faces) for e in bm.edges)
        m["verts"], m["faces"] = len(bm.verts), len(bm.faces)
        m["tris"] = sum(len(f.verts) - 2 for f in bm.faces)
        m["ngons"] = sum(1 for f in bm.faces if len(f.verts) > 4)
        m["boundary_edges"] = ecount.get(1, 0)
        m["nonmanifold_edges"] = sum(c for k, c in ecount.items() if k > 2)
        m["wire_edges"] = ecount.get(0, 0)
        m["loose_verts"] = sum(1 for v in bm.verts if not v.link_edges)
        m["degenerate_faces"] = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
        m["zero_length_edges"] = sum(1 for e in bm.edges if e.calc_length() < 1e-7)
        directed = Counter((l.vert.index, l.link_loop_next.vert.index) for f in bm.faces for l in f.loops)
        m["inconsistent_normals_edges"] = sum(1 for k, c in directed.items() if c > 1)
        kd = KDTree(len(bm.verts))
        for v in bm.verts:
            kd.insert(v.co, v.index)
        kd.balance()
        m["duplicate_verts"] = sum(1 for v in bm.verts
                                   if len(kd.find_range(v.co, 1e-5)) > 1) // 2
        m["islands"] = n_isl
        # per-island volume sign + bbox (closed islands only for inversion test)
        vol, closed = defaultdict(float), defaultdict(lambda: True)
        for e in bm.edges:
            if len(e.link_faces) != 2:
                closed[isl[e.verts[0].index]] = False
        bm_t = bm.copy()
        bmesh.ops.triangulate(bm_t, faces=bm_t.faces[:])
        bm_t.verts.ensure_lookup_table()
        for f in bm_t.faces:
            a, b, c = (v.co for v in f.verts)
            g = isl[f.verts[0].index]
            vol[g] += a.dot(b.cross(c)) / 6.0
            tris.append(tuple(base_v + v.index for v in f.verts))
            tri_meta.append((oi, gid_base + g, f.normal.copy()))
        bm_t.free()
        m["inside_out_islands"] = sum(1 for g in range(n_isl) if closed[g] and vol[g] < -1e-9)
        groups = defaultdict(list)
        for i, g in enumerate(isl):
            groups[g].append(i)
        for g, idx in groups.items():
            pts = [bm.verts[i].co for i in idx]
            lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
            hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
            island_info[gid_base + g] = {"ob": ob.name, "verts": [base_v + i for i in idx],
                                         "center": (lo + hi) / 2, "size": (hi - lo).length,
                                         "closed": closed[g], "tris": []}
        gid_base += n_isl
        # transforms
        s = ob.scale
        m["scale"] = bx.r(tuple(s), 3)
        if any(abs(x - 1) > 1e-4 for x in s):
            flag("sc", f"{ob.name}: unapplied scale {m['scale']}")
        if s.x * s.y * s.z < 0:
            errors.append(f"{ob.name}: negative scale (flips normals on export)")
        # materials
        m["materials"] = len(ob.material_slots)
        if any(sl.material is None for sl in ob.material_slots) or not ob.material_slots:
            warnings.append(f"{ob.name}: missing/empty material slot")
        # weights
        arm_mod = next((md for md in ob.modifiers if md.type == "ARMATURE" and md.object), None)
        if arm_mod and ob.vertex_groups:
            deform = {b.name for b in arm_mod.object.data.bones if b.use_deform}
            gidx = {g.index for g in ob.vertex_groups if g.name in deform}
            unweighted = over4 = 0
            for v in ob.data.vertices:
                ws = [g for g in v.groups if g.group in gidx and g.weight > 1e-4]
                unweighted += not ws
                over4 += len(ws) > 4
            m["unweighted_verts"], m["verts_over_4_influences"] = unweighted, over4
            if unweighted:
                flag("wt", f"{ob.name}: {unweighted} verts with no deform weights")
            if over4:
                flag("wt", f"{ob.name}: {over4} verts with >4 bone influences")
        # uv
        if uv:
            bm_l = bmesh.new()
            bm_l.from_mesh(ob.data)
            m.update(_uv_stats(ob, bm_l))
            bm_l.free()
            if m["uv_maps"] == 0:
                flag("uv", f"{ob.name}: no UV map")
            else:
                if m["uv_zero_area_faces"]:
                    flag("uv", f"{ob.name}: {m['uv_zero_area_faces']} zero-area UV faces")
                if m["uv_oob_pct"] > 0 and profile in ("roblox",):
                    flag("uv", f"{ob.name}: {m['uv_oob_pct']}% UVs outside 0-1")
                if m["uv_overlap_pct"] > 5:
                    warnings.append(f"{ob.name}: ~{m['uv_overlap_pct']}% UV overlap "
                                    "(ok only if mirrored/stacked on purpose; bakes break)")
        bm.free()
        # flags
        if m["inside_out_islands"]:
            flag("inv", f"{ob.name}: {m['inside_out_islands']} closed parts with normals pointing inward")
        if m["inconsistent_normals_edges"]:
            flag("inc", f"{ob.name}: {m['inconsistent_normals_edges']} edges with inconsistent face winding")
        if m["nonmanifold_edges"] or m["wire_edges"]:
            flag("nm", f"{ob.name}: non-manifold edges={m['nonmanifold_edges']} wire={m['wire_edges']}")
        if m["boundary_edges"]:
            flag("bd", f"{ob.name}: {m['boundary_edges']} open boundary edges (not watertight)")
        if m["degenerate_faces"] or m["zero_length_edges"]:
            flag("dg", f"{ob.name}: degenerate faces={m['degenerate_faces']} zero-len edges={m['zero_length_edges']}")
        if m["duplicate_verts"] or m["loose_verts"]:
            flag("dup", f"{ob.name}: duplicate verts={m['duplicate_verts']} loose verts={m['loose_verts']}")
        if m["ngons"]:
            flag("ng", f"{ob.name}: {m['ngons']} n-gons")
        lim = TRI_LIMIT.get(profile)
        if lim and m["tris"] > lim:
            errors.append(f"{ob.name}: {m['tris']} tris > {profile} limit {lim}")
        per[ob.name] = m

    if len(tris) > max_tris:
        warnings.append(f"{len(tris)} tris > max_tris {max_tris}: z-fighting/floating checks skipped")
        return _result(errors, warnings, per, min_z, tol, [], [], [])

    bvh = BVHTree.FromPolygons(verts, tris, epsilon=0.0)
    tri_sets = [set(t) for t in tris]
    for ti, (_, g, _) in enumerate(tri_meta):
        island_info[g]["tris"].append(ti)

    # ---- z-fighting: parallel faces within eps whose areas overlap --------------------
    zf_pairs, contact_pairs = set(), set()
    for ti, t in enumerate(tris):
        a, b, c = (verts[i] for i in t)
        n = tri_meta[ti][2]
        if n.length < 0.5:
            continue
        cen = (a + b + c) / 3
        for p in (cen, cen.lerp(a, .6), cen.lerp(b, .6), cen.lerp(c, .6)):
            for _, _, tj, _ in bvh.find_nearest_range(p, eps):
                if tj is None or tj == ti:
                    continue
                if tri_sets[ti] & tri_sets[tj]:
                    continue
                n2 = tri_meta[tj][2]
                d = n.dot(n2)
                if abs(d) < 0.999:
                    continue
                a2, b2, c2 = (verts[i] for i in tris[tj])
                q = p - n2 * n2.dot(p - a2)
                if _point_in_tri(q, a2, b2, c2, n2):
                    (zf_pairs if d > 0 else contact_pairs).add((min(ti, tj), max(ti, tj)))

    def _describe(pairs):
        out = Counter()
        for i, j in pairs:
            oa, ob_ = obs[tri_meta[i][0]].name, obs[tri_meta[j][0]].name
            out[f"{oa}<->{ob_}" if oa != ob_ else oa] += 1
        return [{"where": k, "tri_pairs": v} for k, v in out.most_common(20)]
    zf = _describe(zf_pairs)
    for z in zf:
        flag("zf", f"z-fighting: {z['where']} ({z['tri_pairs']} overlapping coplanar tri pairs)")
    contact = _describe(contact_pairs)
    for z in contact:
        warnings.append(f"hidden back-to-back faces: {z['where']} ({z['tri_pairs']} pairs) - delete to save tris")

    # ---- floating / detached islands ------------------------------------------------------
    floating, enclosed = [], []
    if len(island_info) > 1:
        tri_island = [m_[1] for m_ in tri_meta]
        biggest = max(island_info, key=lambda g: island_info[g]["size"])
        for g, info in island_info.items():
            if g == biggest:
                continue
            touching = False
            vs = info["verts"]
            step = max(1, len(vs) // 400)
            for vi in vs[::step]:
                for _, _, tj, _ in bvh.find_nearest_range(verts[vi], tol):
                    if tj is not None and tri_island[tj] != g:
                        touching = True
                        break
                if touching:
                    break
            if not touching and info["tris"]:
                sub = BVHTree.FromPolygons(verts, [tris[t] for t in info["tris"]], epsilon=0.0)
                touching = any(tri_island[j] != g for _, j in sub.overlap(bvh))
            if touching:
                continue
            # inside another closed island? (eyes in a head, internal parts) -> parity ray test
            org, hits, d = info["center"], 0, Vector((0.137, 0.271, 0.953)).normalized()
            p = org.copy()
            for _ in range(64):
                loc, _, tj, _ = bvh.ray_cast(p, d)
                if loc is None:
                    break
                if tri_island[tj] != g:
                    hits += 1
                p = loc + d * 1e-5
            rec = {"object": info["ob"], "island_verts": len(vs), "center": bx.r(tuple(info["center"]), 3)}
            (enclosed if hits % 2 == 1 else floating).append(rec)
    for f in floating:
        flag("fl", f"floating/detached part in {f['object']} ({f['island_verts']} verts at {f['center']})")
    if enclosed:
        warnings.append(f"{len(enclosed)} parts fully enclosed, not touching (eyes/internals?): "
                        f"{[e['object'] for e in enclosed][:5]}")
    return _result(errors, warnings, per, min_z, tol, zf, floating, contact, enclosed)


def _result(errors, warnings, per, min_z, tol, zf, floating, contact, enclosed=()):
    ground = None if min_z == math.inf else round(min_z, 4)
    if ground is not None and abs(ground) > max(tol, 1e-3):
        warnings.append(f"asset lowest point z={ground} (not resting on ground plane z=0)")
    return {"ok": True, "pass": not errors, "errors": errors, "warnings": warnings,
            "ground_z": ground, "zfighting": zf, "floating": floating,
            "back_to_back": contact, "enclosed": list(enclosed), "objects": per}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__), save=False)
    p.add_argument("--profile", default="game", choices=list(PROFILES))
    p.add_argument("--eps", type=float, default=0.001, help="z-fight plane distance (m)")
    p.add_argument("--tol", type=float, default=0.002, help="contact tolerance for detached parts (m)")
    p.add_argument("--no-modifiers", action="store_true")
    p.add_argument("--max-tris", type=int, default=300000)
    p.add_argument("--no-uv", dest="uv", action="store_false")
    bx.cli(run, p)
