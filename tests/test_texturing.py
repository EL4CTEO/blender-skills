import bpy
import fixtures as fx
import numpy as np
from run_all import TMP, skill_module


def _stepped_block():
    """1 m block with a 0.5 m step on top (convex outer edges + one concave inner edge), beveled 2 cm."""
    base = fx.cube("Block", size=1)
    top = fx.cube("Step", size=1, location=(-0.25, 0, 0.7))
    top.scale = (0.5, 1, 0.5)
    bo = base.modifiers.new("U", "BOOLEAN")
    bo.operation, bo.object = "UNION", top
    bv = base.modifiers.new("B", "BEVEL")
    bv.width, bv.segments, bv.limit_method = 0.02, 3, "ANGLE"
    ss = base.modifiers.new("S", "SUBSURF")
    ss.levels, ss.subdivision_type = 3, "SIMPLE"
    bpy.context.view_layer.objects.active = base
    for m in [m.name for m in base.modifiers]:
        with bpy.context.temp_override(object=base, active_object=base):
            bpy.ops.object.modifier_apply(modifier=m)
    bpy.data.objects.remove(top)
    bpy.context.view_layer.update()  # drop the stale view-layer entry
    mat = bpy.data.materials.new("M_Paint")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.5, 0.05, 0.03, 1)
    base.data.materials.clear()
    base.data.materials.append(mat)
    for p in base.data.polygons:
        p.material_index = 0
    return base, mat, bsdf


def test_smart_material_curvature_and_roundtrip():
    ob, mat, bsdf = _stepped_block()
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexNoise")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])  # linked input must survive
    bsdf.inputs["Roughness"].default_value = 0.37
    before = sorted((lk.from_node.name, lk.to_socket.identifier) for lk in nt.links)
    sm = skill_module("blender-texturing", "smart_material")
    r = sm.run(objects=["Block"], wear=0.6, grime=0.5, dust=0.4, rust=0.2)
    assert r["ok"] and "M_Paint" in r["materials"] and "note" not in r, r
    co = np.array([v.co for v in ob.data.vertices])
    c = np.array([d.value for d in ob.data.attributes["TX_Curvature"].data])
    mid = np.abs(co[:, 1]) < 0.4
    outer = mid & (co[:, 0] > 0.49) & (co[:, 2] > 0.49)  # bevel of the x+ top edge (convex)
    inner = mid & (np.abs(co[:, 0]) < 0.03) & (np.abs(co[:, 2] - 0.5) < 0.03)  # step's inner corner
    flat = (np.abs(co[:, 1] + 0.5) < 1e-4) & (np.abs(co[:, 0] - 0.25) < 0.15) & (np.abs(co[:, 2]) < 0.2)
    assert outer.any() and inner.any() and flat.any(), (outer.sum(), inner.sum(), flat.sum())
    assert c[outer].mean() > 0.75 and c[inner].min() < 0.35 and abs(c[flat].mean() - 0.5) < 0.05, (
        c[outer].mean(), c[inner].min(), c[flat].mean())
    assert bsdf.inputs["Base Color"].links[0].from_node.name.startswith("TX_")
    sm.run(objects=["Block"], wear=0.9)  # re-run updates in place, links intact
    assert len([n for n in nt.nodes if n.type == "GROUP" and n.name.startswith("TX_")]) == 1
    gn = bsdf.inputs["Metallic"].links[0].from_node
    assert gn.name.startswith("TX_") and gn.inputs["Base Color"].links[0].from_node == tex
    assert abs(gn.inputs["Wear"].default_value - 0.9) < 1e-6 and gn.inputs["Curvature"].is_linked
    sm.run(objects=["Block"], remove=True)
    after = sorted((lk.from_node.name, lk.to_socket.identifier) for lk in nt.links)
    assert after == before and abs(bsdf.inputs["Roughness"].default_value - 0.37) < 1e-6
    assert "TX_Curvature" not in ob.data.attributes and "tx_layers" not in mat


def test_smart_material_bakes_to_texture():
    ob, mat, _ = _stepped_block()
    fx.unwrap(ob)
    bake = skill_module("blender-texture-baking", "bake_maps")
    sm = skill_module("blender-texturing", "smart_material")

    def bake_bc(tag):
        r = bake.run(low="Block", maps=["basecolor"], res=64, samples=1, out=str(TMP / tag), name=tag, device="CPU")
        img = bpy.data.images.load(r["maps"]["basecolor"])
        a = np.empty(64 * 64 * 4, np.float32)
        img.pixels.foreach_get(a)
        return a.reshape(-1, 4)[:, :3]
    clean = bake_bc("clean")
    sm.run(objects=["Block"], wear=0.8, grime=0.6)
    worn = bake_bc("worn")
    changed = (np.abs(worn - clean).max(1) > 0.05).mean()
    assert 0.02 < changed < 0.8, changed  # wear/grime visible on part of the surface, not everywhere


def test_decal_conforms_without_zfighting():
    s = fx.uv_sphere("Ball", radius=1, segs=48, rings=24, location=(0, 0, 1))
    dc = skill_module("blender-texturing", "decal")
    r = dc.run(target="Ball", at=(0.2, -1.5, 1.3), color=(0.8, 0.1, 0.1), size=0.6, rotation=15)
    assert r["ok"] and "warning" not in r, r
    assert r["gap_min_m"] >= 0.0012 and r["gap_max_m"] <= 0.0025, r
    ob = bpy.data.objects[r["decal"]]
    assert ob.parent == s and not ob.visible_shadow and abs(ob.dimensions.x - 0.6) < 0.02
    qa = skill_module("blender-asset-qa", "qa_check").run(objects=["Ball", r["decal"]], uv=False)
    assert not any("z-fighting" in e for e in qa["errors"]), qa["errors"]
