"""Mesh decal that conforms to a surface without z-fighting: a subdivided plane placed at the
closest surface point, shrinkwrapped a fixed offset above it, parented, alpha material, no shadow.

The offset (default 2 mm) stays above blender-asset-qa's 1 mm z-fight threshold and below what the
eye sees as floating. Size follows the image aspect. The result reports the measured min/max gap.
Usage:
  blender -b f.blend -P decal.py -- --target Wall --at 0 -0.1 1.5 --image //decals/logo.png
      [--size 0.5] [--rotation 0] [--offset 0.002] [--subdiv 16 (auto-doubles to 128)] [--name DC_Logo] [--save out.blend]
  blender -b f.blend -P decal.py -- --target Wall --at 0 -0.1 1.5 --color 0.8 0.1 0.1 --size 0.3
  MCP: import decal; print(decal.run(target="Wall", at=(0, -0.1, 1.5), image="C:/decals/logo.png"))
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _material(name, image, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = bx.node(nt, "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.5
    if image:
        tex = bx.node(nt, "TEX_IMAGE") or nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "CLIP"  # no smeared border pixels
        tex.location = bsdf.location.x - 320, bsdf.location.y
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    else:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    mat.surface_render_method = "DITHERED"  # sorts correctly in EEVEE; glTF exports alpha from the Alpha link
    mat.use_backface_culling = True
    return mat


def _gaps(ob, target):
    """World distance to the target at every evaluated triangle's centroid and corners-towards-centroid
    (where flat triangles over a convex crease dip closest), like blender-asset-qa samples them."""
    dg = bpy.context.evaluated_depsgraph_get()
    eo = ob.evaluated_get(dg)
    me = eo.to_mesh()
    me.calc_loop_triangles()
    tinv, tev = target.matrix_world.inverted(), target.evaluated_get(dg)
    out = []
    for t in me.loop_triangles:
        a, b, c = (ob.matrix_world @ me.vertices[i].co for i in t.vertices)
        cen = (a + b + c) / 3
        for p in (cen, cen.lerp(a, .6), cen.lerp(b, .6), cen.lerp(c, .6), a):
            ok, loc, _n, _i = tev.closest_point_on_mesh(tinv @ p)
            if ok:
                out.append((target.matrix_world @ loc - p).length)
    eo.to_mesh_clear()
    return out


def _grid(me, subdiv, w, h):
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")  # calc_uvs only fills an existing layer
    bmesh.ops.create_grid(bm, x_segments=subdiv, y_segments=subdiv, size=0.5, calc_uvs=True)
    bmesh.ops.scale(bm, vec=(w, h, 1), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()


def run(target=None, at=None, image=None, color=(0.8, 0.8, 0.8), size=0.5, rotation=0.0, offset=0.002,
        subdiv=16, name=None, **_):
    bx.object_mode()
    if not target or at is None:
        raise ValueError("--target and --at are required")
    tgt = bpy.data.objects[target]
    tev = tgt.evaluated_get(bpy.context.evaluated_depsgraph_get())
    ok, loc, nrm, _i = tev.closest_point_on_mesh(tgt.matrix_world.inverted() @ Vector(at))
    if not ok:
        raise ValueError(f"no surface found on {target}")
    loc = tgt.matrix_world @ loc
    nrm = (tgt.matrix_world.to_3x3().inverted().transposed() @ nrm).normalized()
    img = bpy.data.images.load(bpy.path.abspath(image), check_existing=True) if image else None
    w = h = size
    if img and img.size[0] and img.size[1]:
        h = size * img.size[1] / img.size[0]
    name = name or "DC_" + (os.path.splitext(os.path.basename(image))[0] if image else "Decal")
    me = bpy.data.meshes.new(name)
    _grid(me, subdiv, w, h)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    # orient +Z to the surface normal, spin about it, sit `offset` above the surface
    rot = nrm.to_track_quat("Z", "Y").to_matrix().to_4x4() @ Matrix.Rotation(math.radians(rotation), 4, "Z")
    ob.matrix_world = Matrix.Translation(loc + nrm * offset) @ rot
    sw = ob.modifiers.new("Conform", "SHRINKWRAP")
    sw.target, sw.wrap_method, sw.wrap_mode, sw.offset = tgt, "PROJECT", "ABOVE_SURFACE", offset
    sw.use_project_z, sw.use_negative_direction, sw.use_positive_direction = True, True, True
    sw.project_limit = max(w, h)  # don't jump to far faces behind the target
    me.materials.append(_material("M_" + name, img, color))
    ob.visible_shadow = False
    ob.parent = tgt
    ob.matrix_parent_inverse = tgt.matrix_world.inverted()
    bpy.context.view_layer.update()
    gaps = _gaps(ob, tgt)
    while min(gaps, default=offset) < 0.6 * offset and subdiv < 128:  # flat tris dip over convex creases
        subdiv *= 2
        _grid(me, subdiv, w, h)
        ob.data.update()
        bpy.context.view_layer.update()
        gaps = _gaps(ob, tgt)
    res = {"ok": True, "decal": name, "target": target, "size_m": bx.r([w, h], 3), "offset_m": offset, "subdiv": subdiv,
           "gap_min_m": round(min(gaps), 5) if gaps else None, "gap_max_m": round(max(gaps), 5) if gaps else None}
    if gaps and max(gaps) > offset * 3:
        res["warning"] = "decal lifts off the surface (gaps > 3x offset): smaller --size, or split it"
    elif gaps and min(gaps) < 0.6 * offset:
        res["warning"] = "decal dips near the surface on sharp creases: raise --offset or move it off the edge"
    return res


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--target", required=True)
    p.add_argument("--at", type=float, nargs=3, required=True, help="world point near the surface")
    p.add_argument("--image", default=None)
    p.add_argument("--color", type=float, nargs=3, default=(0.8, 0.8, 0.8), help="linear RGB if no image")
    p.add_argument("--size", type=float, default=0.5, help="width in m (height from image aspect)")
    p.add_argument("--rotation", type=float, default=0.0, help="degrees about the surface normal")
    p.add_argument("--offset", type=float, default=0.002)
    p.add_argument("--subdiv", type=int, default=16)
    p.add_argument("--name", default=None)
    p.add_argument("--save", default=None)
    bx.cli(run, p)
