"""Headless-safe sculpt preparation and procedural "sculpt" ops (no Sculpt Mode - it crashes in -b).

Ops run in the order given:
  remesh=SIZE        voxel remesh (uniform topology, fuses parts)   e.g. remesh=0.01
  symmetrize=+X      mirror one side onto the other (+X|-X|+Y|-Y|+Z|-Z)
  multires=LEVELS    add Multires and subdivide (Catmull-Clark) LEVELS times
  inflate=DIST       push surface along normals (m)
  detail=STR,SCALE   noise displacement (organic surface breakup), e.g. detail=0.01,0.05
  smooth=ITER        volume-preserving Laplacian smooth
  apply              apply all modifiers except Multires
Usage:
  blender -b f.blend -P sculpt_ops.py -- --objects Blob --ops remesh=0.02 symmetrize=+X multires=3 [--save out.blend]
  MCP: import sculpt_ops; result = sculpt_ops.run(objects=["Blob"], ops=["remesh=0.02", "smooth=5"])
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402


def _ctx(ob):
    return bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                     selected_editable_objects=[ob])


def _apply(ob, keep_multires=True):
    names = [m.name for m in ob.modifiers if not (keep_multires and m.type == "MULTIRES")]
    for name in names:  # names: applied modifiers are freed
        with _ctx(ob):
            bpy.ops.object.modifier_apply(modifier=name)


def run(objects=None, ops=None, **_):
    bx.object_mode()
    out = {}
    for ob in bx.objects(objects):
        log = []
        for op in ops or []:
            k, _, v = op.partition("=")
            if k == "remesh":
                _apply(ob, keep_multires=False)
                ob.data.remesh_voxel_size = float(v)
                ob.data.use_remesh_preserve_volume = True
                with _ctx(ob):
                    bpy.ops.object.voxel_remesh()
            elif k == "symmetrize":
                axis = {"+X": "POSITIVE_X", "-X": "NEGATIVE_X", "+Y": "POSITIVE_Y", "-Y": "NEGATIVE_Y",
                        "+Z": "POSITIVE_Z", "-Z": "NEGATIVE_Z"}[v or "+X"]
                bx.select_only([ob])
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.mesh.symmetrize(direction=axis)
                bpy.ops.object.mode_set(mode="OBJECT")
            elif k == "multires":
                m = next((m for m in ob.modifiers if m.type == "MULTIRES"), None) or ob.modifiers.new("Multires", "MULTIRES")
                for _ in range(int(v)):
                    with _ctx(ob):
                        bpy.ops.object.multires_subdivide(modifier=m.name, mode="CATMULL_CLARK")
                m.levels = m.sculpt_levels = m.render_levels = m.total_levels
            elif k == "inflate":
                d = ob.modifiers.new("Inflate", "DISPLACE")
                d.mid_level, d.strength = 0.0, float(v)
            elif k == "detail":
                strength, scale = (float(x) for x in v.split(","))
                tex = bpy.data.textures.new(f"{ob.name}_detail", "CLOUDS")
                tex.noise_scale, tex.noise_depth = scale, 4
                d = ob.modifiers.new("Detail", "DISPLACE")
                d.texture, d.strength, d.texture_coords = tex, strength, "LOCAL"
            elif k == "smooth":
                s = ob.modifiers.new("Smooth", "LAPLACIANSMOOTH")
                s.iterations, s.lambda_factor, s.use_volume_preserve = int(v), 0.5, True
            elif k == "apply":
                _apply(ob)
            else:
                raise ValueError(f"unknown op {op}")
            log.append(op)
        bpy.context.view_layer.update()
        mr = next((m for m in ob.modifiers if m.type == "MULTIRES"), None)
        out[ob.name] = {"ops": log, "base_faces": len(ob.data.polygons),
                        "evaluated_tris": bx.mesh_tris(ob), "multires_levels": mr.total_levels if mr else 0,
                        "stack": [m.name for m in ob.modifiers]}
    return {"ok": True, "objects": out}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--ops", nargs="*", default=[])
    bx.cli(run, p)
