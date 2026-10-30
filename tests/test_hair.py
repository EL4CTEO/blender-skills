import bpy
import fixtures as fx
import numpy as np
from run_all import TMP, skill_module


def _head():
    ob = fx.mesh_object("Head", lambda bm: (bm.loops.layers.uv.new("UVMap"), __import__("bmesh").ops.create_uvsphere(
        bm, u_segments=32, v_segments=16, radius=0.1, calc_uvs=True)), location=(0, 0, 1.6))
    vg = ob.vertex_groups.new(name="Scalp")
    vg.add([v.index for v in ob.data.vertices if v.co.z > 0.02], 1.0, "REPLACE")
    return ob


def test_groom_attached_masked_with_assets():
    head = _head()
    gr = skill_module("blender-hair-grooming", "groom")
    r = gr.run(surface="Head", mask="Scalp", density=2000, children=60000, viewport=1.0, length=0.12, curl=0.01)
    assert r["ok"] and r["curves"] > 500 and r["root_gap_max_m"] < 1e-3, r
    assert "Capture Rest Geometry" in r["surface_modifiers"] and r["modifiers"][-1] == "Hair Dynamics", r
    assert r["modifiers"][:2] == ["Generate Hair Curves", "Interpolate Hair Curves"]
    hair = bpy.data.objects[r["hair"]]
    assert hair.parent == head and hair.data.surface == head and hair.data.surface_uv_map == "UVMap"
    pos, off = gr._evaluated(hair)
    assert pos[off[:-1], 2].min() - 1.6 > 0.015  # every root inside the Scalp mask (z > 0.02 band)
    assert 0.05 < r["length_mean_m"] < 0.2, r


def test_hair_cards_and_atlas():
    _head()
    gr = skill_module("blender-hair-grooming", "groom")
    r = gr.run(surface="Head", mask="Scalp", children=20000, viewport=1.0, droop=0)
    c = gr.run(cards=r["hair"], card_count=40, atlas_columns=8, atlas_res=256, out=str(TMP / "hair"))
    assert c["card_count"] == 40 and c["tris"] > 40 * 2 * 4, c
    me = bpy.data.objects[c["cards"]].data
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers[0].uv.foreach_get("vector", uv)
    assert uv.min() >= 0 and uv.max() <= 1
    a = np.array(bpy.data.images.load(c["atlas"]["BC"]).pixels[:]).reshape(256, 256, 4)
    assert 0.1 < (a[..., 3] > 0.5).mean() < 0.75  # strands with gaps, not a solid sheet
    rt = np.array(bpy.data.images.load(c["atlas"]["RootTip"]).pixels[:]).reshape(256, 256, 4)
    m = rt[..., 3] > 0.5
    lo, hi = rt[48:56][m[48:56]][:, 0].mean(), rt[200:208][m[200:208]][:, 0].mean()
    assert 0.12 < lo < 0.3 and hi > 0.7, (lo, hi)  # linear root->tip gradient
    assert bpy.context.scene.name == "Scene" and len(bpy.data.scenes) == 1  # atlas scene cleaned up
