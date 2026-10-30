"""Reversible "smart material" layers on existing Principled materials: edge wear (paint chipped to
an under-material), cavity grime, top dust, rust and roughness breakup, driven by curvature.

Curvature comes from a TX_Curvature point attribute computed here (convex > 0.5, concave < 0.5,
needs mid-poly density) or from a baked map (--curvature-map, e.g. bake_maps.py T_<name>_CURV) for
low-poly meshes. --ao-map adds baked AO to the grime mask. Inserts one TX_Layers group node in
front of each Principled BSDF (Base Color, Roughness, Metallic); --remove restores the originals.
Works in Cycles and EEVEE; bake to textures with blender-texture-baking bake_maps.py (no --high).
Usage:
  blender -b f.blend -P smart_material.py -- --objects Crate [--wear 0.5] [--grime 0.4] [--dust 0.3]
      [--rust 0] [--breakup 0.3] [--scale 0.1] [--edge-width 0.02] [--under-color 0.56 0.57 0.58] [--under-metallic 1]
      [--under-roughness 0.35] [--grime-color R G B] [--dust-color R G B] [--curvature-map T_CURV.png]
      [--ao-map T_AO.png] [--uv UVMap] [--save out.blend]
  blender -b f.blend -P smart_material.py -- --objects Crate --remove
  MCP: import smart_material as sm; print(sm.run(objects=["Crate"], wear=0.6, grime=0.4))
"""
import json
import os
import sys

import bpy
import numpy as np
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

GROUP, TAG, KEY, ATTR = "TX_Layers", "TX_", "tx_layers", "TX_Curvature"
WRAPPED = ("Base Color", "Roughness", "Metallic")
COLORS = ("Under Color", "Grime Color", "Dust Color")


def _lin(c):
    """sRGB 0-1 -> linear (Blender color sockets are linear)."""
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c[:3]) + (1.0,)


class _G:
    def __init__(self, nt):
        self.nt = nt

    def link(self, a, b):
        self.nt.links.new(a, b)

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.link(v, sock)
        elif v is not None:
            sock.default_value = v

    def n(self, type_, **props):
        node = self.nt.nodes.new(type_)
        for k, v in props.items():
            setattr(node, k, v)
        return node

    def math(self, op, a, b=0.0, c=None, clamp=False):
        m = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            self.set(m.inputs[i], v)
        return m.outputs[0]

    def mrange(self, v, a, b, lo=0.0, hi=1.0):
        m = self.n("ShaderNodeMapRange", clamp=True)
        for i, x in enumerate((v, a, b, lo, hi)):
            self.set(m.inputs[i], x)
        return m.outputs[0]

    def mix(self, kind, fac, a, b):
        m = self.n("ShaderNodeMix", data_type=kind)
        sock = {"FLOAT": (0, 2, 3, 0), "RGBA": (0, 6, 7, 2)}[kind]
        self.set(m.inputs[sock[0]], fac)
        self.set(m.inputs[sock[1]], a)
        self.set(m.inputs[sock[2]], b)
        return m.outputs[sock[3]]

    def noise(self, vec, scale, detail=4.0, rough=0.6):
        n = self.n("ShaderNodeTexNoise")
        self.set(n.inputs["Vector"], vec)
        self.set(n.inputs["Scale"], scale)
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n.outputs["Factor"]


def build_group():
    ng = bpy.data.node_groups.get(GROUP) or bpy.data.node_groups.new(GROUP, "ShaderNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    for nm, kind, d in (("Base Color", "Color", (0.8, 0.8, 0.8, 1)), ("Roughness", "Float", 0.5),
                        ("Metallic", "Float", 0.0), ("Curvature", "Float", 0.5), ("AO", "Float", 1.0),
                        ("Wear", "Float", 0.0), ("Grime", "Float", 0.0), ("Dust", "Float", 0.0),
                        ("Rust", "Float", 0.0), ("Breakup", "Float", 0.3), ("Scale", "Float", 0.1),
                        ("Under Color", "Color", (0.27, 0.28, 0.29, 1)), ("Under Metallic", "Float", 1.0),
                        ("Under Roughness", "Float", 0.35), ("Grime Color", "Color", (0.04, 0.03, 0.02, 1)),
                        ("Dust Color", "Color", (0.45, 0.4, 0.33, 1))):
        s = ng.interface.new_socket(nm, in_out="INPUT", socket_type=f"NodeSocket{kind}")
        s.default_value = d
    for nm, kind in (("Base Color", "Color"), ("Roughness", "Float"), ("Metallic", "Float"),
                     ("Wear Mask", "Float")):
        ng.interface.new_socket(nm, in_out="OUTPUT", socket_type=f"NodeSocket{kind}")
    g = _G(ng)
    gi, go = g.n("NodeGroupInput"), g.n("NodeGroupOutput")
    I = gi.outputs  # noqa: E741
    obj = g.n("ShaderNodeTexCoord").outputs["Object"]  # object space: masks stick to the asset
    inv = g.math("DIVIDE", 1.0, I["Scale"])
    up = g.n("ShaderNodeSeparateXYZ")
    g.link(g.n("ShaderNodeNewGeometry").outputs["Normal"], up.inputs[0])
    convex = g.mrange(I["Curvature"], 0.5, 1.0)
    concave = g.mrange(I["Curvature"], 0.5, 0.0)
    # edge wear: convexity above 1 - Wear, noise breaks the line into chips
    chips = g.math("SUBTRACT", g.noise(obj, g.math("MULTIPLY", inv, 2.0), 8.0, 0.7), 0.5)
    w_thr = g.math("SUBTRACT", 1.0, I["Wear"])
    wear = g.mrange(g.math("MULTIPLY_ADD", chips, 1.2, convex), w_thr, g.math("ADD", w_thr, 0.08))
    wear = g.math("MULTIPLY", wear, g.math("GREATER_THAN", I["Wear"], 0.0))
    # grime: cavities + (1 - AO), blotchy
    cav = g.math("MAXIMUM", concave, g.math("SUBTRACT", 1.0, I["AO"]))
    blot = g.noise(obj, inv, 4.0, 0.55)
    g_thr = g.math("SUBTRACT", 1.0, I["Grime"])
    grime = g.mrange(g.math("MULTIPLY_ADD", g.math("SUBTRACT", blot, 0.5), 0.8, cav), g_thr, g.math("ADD", g_thr, 0.2))
    grime = g.math("MULTIPLY", grime, g.math("GREATER_THAN", I["Grime"], 0.0))
    # dust: up-facing, in noisy patches whose coverage grows with Dust
    d_thr = g.math("SUBTRACT", 1.0, I["Dust"])
    patches = g.mrange(g.noise(obj, g.math("MULTIPLY", inv, 0.5), 5.0, 0.6), g.math("MULTIPLY", d_thr, 0.75),
                       g.math("ADD", g.math("MULTIPLY", d_thr, 0.75), 0.15))
    dust = g.math("MULTIPLY", g.mrange(up.outputs["Z"], 0.45, 0.85), patches)
    dust = g.math("MULTIPLY", dust, g.math("GREATER_THAN", I["Dust"], 0.0))
    # rust: blotches seeded in cavities and on worn edges
    r_n = g.noise(obj, g.math("MULTIPLY", inv, 0.7), 6.0, 0.65)
    r_seed = g.math("ADD", g.math("MAXIMUM", concave, wear), r_n)
    r_thr = g.math("MULTIPLY_ADD", I["Rust"], -0.9, 1.45)
    rust = g.mrange(r_seed, r_thr, g.math("ADD", r_thr, 0.12))
    rust = g.math("MULTIPLY", rust, g.math("GREATER_THAN", I["Rust"], 0.0))
    rust_col = g.mix("RGBA", g.noise(obj, g.math("MULTIPLY", inv, 6.0)), (0.12, 0.03, 0.01, 1), (0.3, 0.1, 0.03, 1))
    # roughness breakup: +-25% fine variation, the cheapest realism win
    br = g.math("MULTIPLY_ADD", g.math("SUBTRACT", g.noise(obj, g.math("MULTIPLY", inv, 4.0), 6.0), 0.5),
                g.math("MULTIPLY", I["Breakup"], 0.5), 1.0)
    # stack: base -> wear (reveals under-material) -> rust -> grime -> dust
    col = g.mix("RGBA", wear, I["Base Color"], I["Under Color"])
    rough = g.mix("FLOAT", wear, I["Roughness"], I["Under Roughness"])
    metal = g.mix("FLOAT", wear, I["Metallic"], I["Under Metallic"])
    col = g.mix("RGBA", rust, col, rust_col)
    rough = g.mix("FLOAT", rust, rough, 0.85)
    metal = g.mix("FLOAT", rust, metal, 0.0)
    col = g.mix("RGBA", g.math("MULTIPLY", grime, 0.85), col, I["Grime Color"])
    rough = g.mix("FLOAT", grime, rough, g.math("MAXIMUM", rough, 0.7))
    metal = g.mix("FLOAT", grime, metal, 0.0)
    col = g.mix("RGBA", dust, col, I["Dust Color"])
    rough = g.mix("FLOAT", dust, rough, 0.9)
    metal = g.mix("FLOAT", dust, metal, 0.0)
    g.link(col, go.inputs["Base Color"])
    g.link(g.math("MULTIPLY", rough, br, clamp=True), go.inputs["Roughness"])
    g.link(metal, go.inputs["Metallic"])
    g.link(wear, go.inputs["Wear Mask"])
    return ng


def curvature_attribute(ob, width=0.02, gain=1.0):
    """TX_Curvature point attribute: 0.5 flat, -> 1 convex, -> 0 concave.

    Mean elevation of the neighbours within `width` (world m) below/above the vertex tangent plane,
    so the band is ~width wide whatever the mesh density. Vertices with < 3 neighbours in range
    (low-poly) fall back to their 1-ring.
    """
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    mw = np.array(ob.matrix_world, np.float32)
    co = co.reshape(n, 3) @ mw[:3, :3].T + mw[:3, 3]
    nr = np.empty(n * 3, np.float32)
    me.vertex_normals.foreach_get("vector", nr)
    nr = nr.reshape(n, 3) @ np.linalg.inv(mw[:3, :3])  # normal matrix = inverse transpose
    nr /= np.maximum(np.linalg.norm(nr, axis=1), 1e-9)[:, None]
    ed = np.empty(len(me.edges) * 2, np.int32)
    me.edges.foreach_get("vertices", ed)
    ring = [[] for _ in range(n)]
    for a, b in zip(ed[0::2].tolist(), ed[1::2].tolist()):
        ring[a].append(b)
        ring[b].append(a)
    kd = KDTree(n)
    for i, p in enumerate(co.tolist()):
        kd.insert(p, i)
    kd.balance()
    c = np.zeros(n)
    for i in range(n):
        idx = [j for _, j, _ in kd.find_range(co[i], width) if j != i]
        if len(idx) < 3:
            idx = ring[i]
        if not idx:
            continue
        d = co[idx] - co[i]
        ln = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
        c[i] = -(d @ nr[i] / ln).mean()  # sine of elevation: below the tangent plane = convex
    c = np.clip(0.5 + c * gain * 2.0, 0.0, 1.0).astype(np.float32)
    at = me.attributes.get(ATTR) or me.attributes.new(ATTR, "FLOAT", "POINT")
    at.data.foreach_set("value", c)
    edge = float(np.median(np.linalg.norm(co[ed[0::2]] - co[ed[1::2]], axis=1))) if len(ed) else 0.0
    return c, edge


def _src(sock):
    if sock.is_linked:
        lk = sock.links[0]
        return {"node": lk.from_node.name, "out": lk.from_socket.identifier}
    v = sock.default_value
    return {"value": list(v) if hasattr(v, "__len__") else v}


def _image_node(nt, name, path, uv, x, y):
    node = nt.nodes.get(name) or nt.nodes.new("ShaderNodeTexImage")
    node.name, node.location = name, (x, y)
    node.image = bpy.data.images.load(bpy.path.abspath(path), check_existing=True)
    node.image.colorspace_settings.is_data = True  # masks are data, never sRGB
    if uv:
        m = nt.nodes.get(name + "_uv") or nt.nodes.new("ShaderNodeUVMap")
        m.name, m.uv_map, m.location = name + "_uv", uv, (x - 200, y)
        nt.links.new(m.outputs["UV"], node.inputs["Vector"])
    return node.outputs["Color"]


def _apply_mat(mat, ng, vals, curv_map, ao_map, uv):
    nt = mat.node_tree
    record = json.loads(mat.get(KEY, "{}"))
    for bsdf in [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]:
        gname = TAG + bsdf.name
        gn = nt.nodes.get(gname)
        x, y = bsdf.location.x - 280, bsdf.location.y
        if gn is None:  # first application: remember the originals
            record[bsdf.name] = {k: _src(bsdf.inputs[k]) for k in WRAPPED}
            gn = nt.nodes.new("ShaderNodeGroup")
            gn.name, gn.label, gn.node_tree, gn.location = gname, "TX Layers", ng, (x, y)
        # (re)wire on every run: re-running rebuilds the group, which recreates its sockets and drops links
        for k, src in record[bsdf.name].items():
            if "node" in src and src["node"] in nt.nodes:
                nt.links.new(nt.nodes[src["node"]].outputs[src["out"]], gn.inputs[k])
            else:
                gn.inputs[k].default_value = src["value"]
            nt.links.new(gn.outputs[k], bsdf.inputs[k])
        if curv_map:
            nt.links.new(_image_node(nt, TAG + "curv", curv_map, uv, x - 260, y - 420), gn.inputs["Curvature"])
        else:
            at = nt.nodes.get(TAG + "attr") or nt.nodes.new("ShaderNodeAttribute")
            at.name, at.attribute_type, at.attribute_name = TAG + "attr", "GEOMETRY", ATTR
            at.location = x - 260, y - 420
            nt.links.new(at.outputs["Fac"], gn.inputs["Curvature"])
        if ao_map:
            nt.links.new(_image_node(nt, TAG + "ao", ao_map, uv, x - 260, y - 700), gn.inputs["AO"])
        for k, v in vals.items():
            gn.inputs[k].default_value = v
    mat[KEY] = json.dumps(record)


def _remove_mat(mat):
    nt = mat.node_tree
    record = json.loads(mat.get(KEY, "{}"))
    for bname, socks in record.items():
        bsdf = nt.nodes.get(bname)
        if bsdf is None:
            continue
        for k, src in socks.items():
            s = bsdf.inputs[k]
            for lk in list(s.links):
                nt.links.remove(lk)
            if "node" in src and src["node"] in nt.nodes:
                nt.links.new(nt.nodes[src["node"]].outputs[src["out"]], s)
            elif "value" in src:
                s.default_value = src["value"]
    for nd in [nd for nd in nt.nodes if nd.name.startswith(TAG)]:
        nt.nodes.remove(nd)
    if KEY in mat:
        del mat[KEY]


def run(objects=None, wear=0.0, grime=0.0, dust=0.0, rust=0.0, breakup=0.3, scale=0.1,
        under_color=(0.56, 0.57, 0.58), under_metallic=1.0, under_roughness=0.35,
        grime_color=(0.22, 0.19, 0.15), dust_color=(0.71, 0.67, 0.6), curvature_map=None, ao_map=None,
        uv=None, edge_width=0.02, gain=1.0, remove=False, **_):
    bx.object_mode()
    obs = [o for o in bx.objects(objects) if o.type == "MESH"]
    mats = {s.material for o in obs for s in o.material_slots if s.material and s.material.node_tree}
    if remove:
        for m in mats:
            _remove_mat(m)
        for o in obs:
            if ATTR in o.data.attributes:
                o.data.attributes.remove(o.data.attributes[ATTR])
        return {"ok": True, "removed": sorted(m.name for m in mats), "objects": [o.name for o in obs]}
    res = {"ok": True, "objects": [o.name for o in obs], "materials": sorted(m.name for m in mats)}
    no_mat = [o.name for o in obs if not any(s.material for s in o.material_slots)]
    if no_mat:
        res["warning"] = f"no material (skipped): {no_mat}"
    if not curvature_map:
        coarse, stats = [], {}
        for o in obs:
            c, edge = curvature_attribute(o, edge_width, gain)
            stats[o.name] = {"convex_verts_pct": round(float((c > 0.65).mean()) * 100, 1),
                             "concave_verts_pct": round(float((c < 0.35).mean()) * 100, 1)}
            if edge > 4 * edge_width:
                coarse.append(o.name)
        res["curvature"] = stats
        if coarse:
            res["note"] = (f"{coarse}: low vertex density, wear spreads over whole faces. Bake a curvature "
                           "map (bake_maps.py --maps normal curvature) and pass --curvature-map")
    elif any(not o.data.uv_layers for o in obs):
        raise ValueError("--curvature-map/--ao-map need a UV map")
    ng = build_group()
    vals = {"Wear": wear, "Grime": grime, "Dust": dust, "Rust": rust, "Breakup": breakup, "Scale": scale,
            "Under Color": _lin(under_color), "Under Metallic": under_metallic,
            "Under Roughness": under_roughness, "Grime Color": _lin(grime_color), "Dust Color": _lin(dust_color)}
    for m in mats:
        _apply_mat(m, ng, vals, curvature_map, ao_map, uv)
    res["params"] = {k: v for k, v in vals.items() if k in ("Wear", "Grime", "Dust", "Rust", "Breakup", "Scale")}
    return res


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    for k, d in (("wear", 0.0), ("grime", 0.0), ("dust", 0.0), ("rust", 0.0), ("breakup", 0.3),
                 ("scale", 0.1), ("edge-width", 0.02), ("under-metallic", 1.0), ("under-roughness", 0.35), ("gain", 1.0)):
        p.add_argument(f"--{k}", type=float, default=d)
    p.add_argument("--under-color", type=float, nargs=3, default=(0.56, 0.57, 0.58), help="sRGB 0-1")
    p.add_argument("--grime-color", type=float, nargs=3, default=(0.22, 0.19, 0.15), help="sRGB 0-1")
    p.add_argument("--dust-color", type=float, nargs=3, default=(0.71, 0.67, 0.6), help="sRGB 0-1")
    p.add_argument("--curvature-map", default=None)
    p.add_argument("--ao-map", default=None)
    p.add_argument("--uv", default=None, help="UV map for the mask images (default: active)")
    p.add_argument("--remove", action="store_true")
    bx.cli(run, p)
