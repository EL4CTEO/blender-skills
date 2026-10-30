import math

import bpy
import fixtures as fx
import numpy as np
from run_all import TMP, requires_gpu, skill_module


def _scene():
    ob = fx.unwrap(fx.uv_sphere("Ball", radius=1, segs=32, rings=16))
    for p in ob.data.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new("M_Skin")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.8, 0.3, 0.2, 1)
    ob.data.materials.append(mat)
    sc = bpy.context.scene
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    sc.collection.objects.link(cam)
    sc.camera, cam.location, cam.rotation_euler = cam, (0, -5, 0), (math.pi / 2, 0, 0)
    return ob, mat, bsdf


def _clusters(a, tol=0.04, min_frac=0.02):
    """Distinct flat colors (8-bit rounding splits a band into near-identical values)."""
    cols, counts = np.unique(np.round(a, 2), axis=0, return_counts=True)
    centers, sizes = [], []
    for i in np.argsort(-counts):
        k = next((k for k, c in enumerate(centers) if np.abs(cols[i] - c).max() <= tol), None)
        if k is None:
            centers.append(cols[i])
            sizes.append(counts[i])
        else:
            sizes[k] += counts[i]
    return sum(s > min_frac * len(a) for s in sizes)


def _bands(engine, tag):
    sc = bpy.context.scene
    sc.render.engine = engine
    if engine == "CYCLES":
        sc.cycles.samples, sc.cycles.device = 4, "CPU"
    sc.render.resolution_x = sc.render.resolution_y = 96
    sc.render.film_transparent = True
    sc.render.filepath = str(TMP / f"npr_{tag}.png")
    bpy.ops.render.render(write_still=True)
    a = np.array(bpy.data.images.load(sc.render.filepath).pixels[:]).reshape(-1, 4)
    a = a[a[:, 3] > 0.99, :3]  # opaque object pixels only
    return _clusters(a)


def test_toon_hull_bands_lineart_roundtrip():
    ob, mat, bsdf = _scene()
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    ts = skill_module("blender-stylized-npr", "toon_setup")
    r = ts.run(objects=["Ball"], bands=2, outline=0.03, smooth_normals=True, line_art=True)
    assert r["ok"] and r["key_light"] == "NPR_Key" and bpy.context.scene.view_settings.view_transform == "Standard", r
    me = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    body = [p.normal.dot(p.center) for p in me.polygons if p.material_index == 0]
    hull = [(p.normal.dot(p.center), p.center.length) for p in me.polygons if p.material_index == 1]
    ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    assert len(hull) == len(body) and min(body) > 0  # body faces outward
    assert max(d for d, _ in hull) < 0 and min(rad for _, rad in hull) > 1.0  # hull outside, facing inward
    sun = bpy.data.objects["NPR_Key"]
    sun.rotation_euler = (0, 0, 0)
    bpy.context.scene.frame_set(2)
    assert tuple(nt.nodes["NPR_toon"].inputs["Light Direction"].default_value) == (0.0, 0.0, 1.0)
    la = bpy.data.objects[r["line_art"]].evaluated_get(bpy.context.evaluated_depsgraph_get())
    assert len(la.data.layers["Lines"].current_frame().drawing.strokes) > 0
    sun.rotation_euler = (0.9, 0, 0.5)
    bpy.context.scene.frame_set(1)
    ts.run(objects=["Ball"], outline=0, rim=0, spec=0)  # bands only for the color count
    ob.modifiers["NPR_Outline"].show_render = False
    bpy.data.objects[r["line_art"]].hide_render = True
    assert _bands("CYCLES", "key") == 2
    ts.run(objects=["Ball"], remove=True, line_art=True)
    assert out.inputs["Surface"].links[0].from_node == bsdf and len(ob.material_slots) == 1
    assert not ob.modifiers and "NPR_OutlineNormal" not in ob.data.color_attributes
    assert bpy.context.scene.view_settings.view_transform == "AgX" and "NPR_LineArt" not in bpy.data.objects


def test_toon_scene_lighting_eevee():
    requires_gpu()
    _scene()
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler, sun.data.energy = (0.9, 0, 0.5), 4.0
    ts = skill_module("blender-stylized-npr", "toon_setup")
    ts.run(objects=["Ball"], bands=3, lighting="scene", outline=0)
    assert _bands("BLENDER_EEVEE", "scene") == 3
