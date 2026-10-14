"""Generate an LOD chain (<name>_LOD1..N) with Decimate, preserving UV seams/normals/silhouette.

Default ratios halve the triangles per level: 1.0, 0.5, 0.25, 0.125. LOD0 is the source (renamed
<base>_LOD0 if --rename). Also cleans the mesh first (merge by distance, delete loose, degenerate).
Usage:
  blender -b f.blend -P make_lods.py -- --objects SM_Crate [--ratios 0.5 0.25 0.125]
      [--symmetry] [--cleanup] [--rename] [--collection LODs] [--save out.blend]
  MCP: import make_lods; print(make_lods.run(objects=["SM_Crate"], ratios=[0.5, 0.2]))
"""
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def cleanup(ob, dist=1e-4):
    """Merge by distance, dissolve degenerate, delete loose. Returns removed vert count."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges[:], dist=dist)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    return n0 - len(ob.data.vertices)


def run(objects=None, ratios=None, symmetry=False, do_cleanup=False, rename=False,
        collection=None, **_):
    bx.object_mode()
    ratios = ratios or [0.5, 0.25, 0.125]
    out = {}
    for src in bx.objects(objects):
        base = src.name.split("_LOD")[0]
        rec = {}
        if do_cleanup:
            rec["cleanup_removed_verts"] = cleanup(src)
        if rename and not src.name.endswith("_LOD0"):
            src.name = f"{base}_LOD0"
        col = None
        if collection:
            col = bpy.data.collections.get(collection) or bpy.data.collections.new(collection)
            if col.name not in bpy.context.scene.collection.children:
                bpy.context.scene.collection.children.link(col)
        tris0 = bx.mesh_tris(src)
        rec["LOD0"] = tris0
        for i, ratio in enumerate(ratios, start=1):
            name = f"{base}_LOD{i}"
            old = bpy.data.objects.get(name)
            if old:
                bpy.data.objects.remove(old)
            lod = src.copy()
            lod.data = src.data.copy()
            lod.name = lod.data.name = name
            for c in [col] if col else src.users_collection:
                c.objects.link(lod)
            # apply existing modifiers into the copy, then decimate
            dg = bpy.context.evaluated_depsgraph_get()
            me = bpy.data.meshes.new_from_object(src.evaluated_get(dg))
            old_me, lod.data = lod.data, me
            bpy.data.meshes.remove(old_me)
            me.name = name
            lod.modifiers.clear()
            d = lod.modifiers.new("Decimate", "DECIMATE")
            d.decimate_type = "COLLAPSE"
            d.ratio = ratio
            d.use_symmetry = symmetry
            d.use_collapse_triangulate = True
            with bpy.context.temp_override(object=lod, active_object=lod, selected_objects=[lod],
                                           selected_editable_objects=[lod]):
                bpy.ops.object.modifier_apply(modifier=d.name)
            lod.hide_set(True)
            lod.hide_render = True
            rec[f"LOD{i}"] = bx.mesh_tris(lod, evaluated=False)
        out[src.name] = rec
    return {"ok": True, "lods": out,
            "screen_size_hint": {"LOD1": 0.5, "LOD2": 0.25, "LOD3": 0.125},
            "note": "check each LOD silhouette (look/review_shots) and UV seams; LOD3+ may need a billboard/imposter"}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--ratios", nargs="*", type=float, default=None)
    p.add_argument("--symmetry", action="store_true")
    p.add_argument("--cleanup", dest="do_cleanup", action="store_true")
    p.add_argument("--rename", action="store_true")
    p.add_argument("--collection", default=None)
    bx.cli(run, p)
