import os

import bpy
import fixtures as fx
import numpy as np
from run_all import TMP, skill_module


def _pixels(path):
    im = bpy.data.images.load(path)
    a = np.empty(len(im.pixels), dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(-1, 4)


def test_high_to_low_bake_normal_ao_curv_orm_basecolor():
    hi = fx.uv_sphere("Ball_high", radius=1, segs=64, rings=32)
    hi.modifiers.new("D", "DISPLACE").strength = 0.05
    tex = bpy.data.textures.new("N", "CLOUDS")
    tex.noise_scale = 0.2
    hi.modifiers["D"].texture = tex
    mat = bpy.data.materials.new("M_Red")
    next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (1, 0, 0, 1)
    hi.data.materials.append(mat)
    lo = fx.uv_sphere("SM_Ball", radius=1, segs=16, rings=8)
    fx.unwrap(lo)
    bake = skill_module("blender-texture-baking", "bake_maps")
    r = bake.run(low="SM_Ball", high=["Ball_high"], maps=["normal", "ao", "basecolor", "curvature"],
                 res=128, samples=4, device="CPU", out=str(TMP / "bake"), pack_orm=True)
    for k in ("normal", "ao", "basecolor", "curvature", "orm"):
        assert os.path.getsize(r["maps"][k]) > 0, k
    n = _pixels(r["maps"]["normal"])
    assert n[:, 2].mean() > 0.6 and n[:, 0].std() > 0.01      # tangent normal, with detail
    bc = _pixels(r["maps"]["basecolor"])
    assert bc[:, 0].max() > 0.9 and bc[:, 1].max() < 0.1          # red came through
    assert not any(n.label == "BAKE_TARGET" for m in bpy.data.materials if m.node_tree for n in m.node_tree.nodes)
    out = next(n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL")
    assert out.inputs["Surface"].links[0].from_node.type == "BSDF_PRINCIPLED"  # restored


def test_self_bake_procedural_roughness():
    lo = fx.cube("SM_Box")
    fx.unwrap(lo)
    mat = bpy.data.materials.new("M_Box")
    next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Roughness"].default_value = 0.25
    lo.data.materials.append(mat)
    r = skill_module("blender-texture-baking", "bake_maps").run(
        low="SM_Box", maps=["roughness", "metallic"], res=64, samples=1, device="CPU", out=str(TMP / "bake2"))
    px = _pixels(r["maps"]["roughness"])
    assert abs(np.median(px[:, 0]) - 0.25) < 0.02
