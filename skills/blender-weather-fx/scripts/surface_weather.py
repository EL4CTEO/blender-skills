"""Reversible weather layer on existing materials: wetness (porous darkening + water film coat),
puddles with flattened normals and animated rain ripples, rain streaks on walls, snow cover; plus
optional real snow geometry (GN shell) and a vertex-color mask for game engines.

Inserts one ENV_Weather group node in front of every Principled BSDF of the target objects'
materials; the original links/values are stored on the material and --remove restores them exactly.
Masks are world-space, so puddles and snow line up across objects. Works in Cycles and EEVEE.
Usage:
  blender -b f.blend -P surface_weather.py -- --objects Street Car [--wetness 0.6] [--puddles 0.4]
      [--ripples 1] [--streaks 0.5] [--snow 0.7] [--snow-depth 0.06] [--porosity 0.6]
      [--scale 3.0] [--vertex-mask] [--save out.blend]
  blender -b f.blend -P surface_weather.py -- --objects Street Car --remove
  MCP: import surface_weather as sw; print(sw.run(objects=["Street"], wetness=0.7, puddles=0.4))
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector, noise

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

GROUP, SNOW_GN, SNOW_MAT, TAG, KEY = "ENV_Weather", "ENV_SnowCover", "ENV_M_Snow", "ENV_W_", "env_weather"
WRAPPED = ("Base Color", "Roughness", "Normal", "Coat Weight", "Coat Roughness", "Coat Normal")
PARAMS = ("Wetness", "Puddles", "Ripples", "Streaks", "Snow", "Porosity", "Scale")


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
        sock = {"FLOAT": (0, 2, 3, 0), "VECTOR": (0, 4, 5, 1), "RGBA": (0, 6, 7, 2)}[kind]
        self.set(m.inputs[sock[0]], fac)
        self.set(m.inputs[sock[1]], a)
        self.set(m.inputs[sock[2]], b)
        return m.outputs[sock[3]]

    def noise(self, vec, scale, detail=3.0, rough=0.55):
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
                        ("Normal", "Vector", None), ("Coat Weight", "Float", 0.0),
                        ("Coat Roughness", "Float", 0.03), ("Wetness", "Float", 0.0),
                        ("Puddles", "Float", 0.0), ("Ripples", "Float", 0.0), ("Streaks", "Float", 0.0),
                        ("Snow", "Float", 0.0), ("Porosity", "Float", 0.6), ("Scale", "Float", 1.5)):
        s = ng.interface.new_socket(nm, in_out="INPUT", socket_type=f"NodeSocket{kind}")
        if d is not None:
            s.default_value = d
    for nm, kind in (("Base Color", "Color"), ("Roughness", "Float"), ("Normal", "Vector"),
                     ("Coat Weight", "Float"), ("Coat Roughness", "Float"), ("Coat Normal", "Vector")):
        ng.interface.new_socket(nm, in_out="OUTPUT", socket_type=f"NodeSocket{kind}")
    g = _G(ng)
    gi, go = g.n("NodeGroupInput"), g.n("NodeGroupOutput")
    I = gi.outputs  # noqa: E741
    geo = g.n("ShaderNodeNewGeometry")
    pos, nrm = geo.outputs["Position"], geo.outputs["Normal"]
    sep_n = g.n("ShaderNodeSeparateXYZ")
    g.link(nrm, sep_n.inputs[0])
    up = sep_n.outputs["Z"]
    sep_p = g.n("ShaderNodeSeparateXYZ")
    g.link(pos, sep_p.inputs[0])
    flat = g.n("ShaderNodeCombineXYZ")  # world XY: puddles/ripples ignore height
    g.link(sep_p.outputs["X"], flat.inputs["X"])
    g.link(sep_p.outputs["Y"], flat.inputs["Y"])
    inv_scale = g.math("DIVIDE", 1.0, I["Scale"])
    # puddles: low-frequency noise on up-facing surfaces; coverage ~ Puddles
    wn = g.n("ShaderNodeTexNoise")  # domain warp: organic puddle edges
    g.link(flat.outputs[0], wn.inputs["Vector"])
    g.link(g.math("MULTIPLY", inv_scale, 0.7), wn.inputs["Scale"])
    warp = g.n("ShaderNodeVectorMath", operation="MULTIPLY_ADD")
    g.link(wn.outputs["Color"], warp.inputs[0])
    amp = g.n("ShaderNodeCombineXYZ")  # warp amplitude ~ 0.3 x feature size
    wa = g.math("MULTIPLY", I["Scale"], 0.3)
    g.link(wa, amp.inputs["X"])
    g.link(wa, amp.inputs["Y"])
    g.link(amp.outputs[0], warp.inputs[1])
    g.link(flat.outputs[0], warp.inputs[2])
    pn = g.noise(warp.outputs[0], inv_scale, 6.0, 0.6)
    thr = g.math("MULTIPLY_ADD", I["Puddles"], -0.24, 0.62)
    puddle = g.math("MULTIPLY", g.mrange(pn, thr, g.math("ADD", thr, 0.04)), g.mrange(up, 0.9, 0.97))
    puddle = g.math("MULTIPLY", puddle, g.math("GREATER_THAN", I["Puddles"], 0.0))
    wet = g.math("ADD", I["Wetness"], puddle, clamp=True)
    # streaks: vertically stretched noise on walls
    side = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", up, up))
    mp = g.n("ShaderNodeMapping")
    g.link(pos, mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = (14.0, 14.0, 0.7)
    streak = g.math("MULTIPLY", g.mrange(g.noise(mp.outputs[0], 1.0, 2.0), 0.5, 0.62),
                    g.math("MULTIPLY", side, I["Streaks"]))
    # ripples: expanding rings, one per Voronoi cell, random phase; time from a frame driver
    t = g.n("ShaderNodeValue", label="ENV time (s)")
    fc = t.outputs[0].driver_add("default_value")
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    fc.driver.expression = f"frame / {fps:g}"
    vor = g.n("ShaderNodeTexVoronoi")
    vor.voronoi_dimensions = "2D"
    g.link(flat.outputs[0], vor.inputs["Vector"])
    vor.inputs["Scale"].default_value = 6.0  # ~17 cm cells
    cr = g.n("ShaderNodeSeparateColor")
    g.link(vor.outputs["Color"], cr.inputs[0])
    phase = g.math("FRACT", g.math("MULTIPLY_ADD", t.outputs[0], 1.6, cr.outputs[0]))
    ring = g.math("SUBTRACT", 1.0, g.math("DIVIDE", g.math("ABSOLUTE", g.math(
        "SUBTRACT", vor.outputs["Distance"], g.math("MULTIPLY", phase, 0.5))), 0.06), clamp=True)
    ring = g.math("MULTIPLY", ring, g.math("SUBTRACT", 1.0, phase))
    rip_h = g.math("MULTIPLY", ring, g.math("MULTIPLY", I["Ripples"], puddle))
    bump_r = g.n("ShaderNodeBump")
    bump_r.inputs["Strength"].default_value = 0.6
    bump_r.inputs["Distance"].default_value = 0.002
    g.link(rip_h, bump_r.inputs["Height"])
    g.link(nrm, bump_r.inputs["Normal"])
    # wet response (Lagarde): porous albedo darkens, roughness drops, a water film = coat
    dark = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", g.math("MULTIPLY", I["Porosity"], wet), 0.55))
    base = g.mix("RGBA", 1.0, I["Base Color"], (0, 0, 0, 1))
    m = base.node
    m.blend_type = "MULTIPLY"
    m.inputs[0].default_value = 1.0
    dvec = g.n("ShaderNodeCombineColor")
    for i in range(3):
        g.link(dark, dvec.inputs[i])
    g.link(dvec.outputs[0], m.inputs[7])
    rough = g.math("MULTIPLY", I["Roughness"], g.math("MULTIPLY_ADD", wet, -0.6, 1.0))
    coat_w = g.math("ADD", g.math("MULTIPLY_ADD", I["Wetness"], 0.6, puddle), streak, clamp=True)
    coat_w = g.math("MAXIMUM", coat_w, I["Coat Weight"])
    coat_r = g.mix("FLOAT", puddle, g.mix("FLOAT", I["Wetness"], I["Coat Roughness"], 0.12), 0.02)
    normal = g.mix("VECTOR", puddle, I["Normal"], nrm)  # water fills the cracks
    # snow: up-facing with noisy edge; overrides everything it covers
    sn = g.noise(pos, 2.0, 6.0, 0.6)
    s_thr = g.math("MULTIPLY_ADD", I["Snow"], -0.8, 1.0)  # coverage 1 -> anything facing up-ish
    snow = g.mrange(g.math("MULTIPLY_ADD", g.math("SUBTRACT", sn, 0.5), 0.5, up), s_thr, g.math("ADD", s_thr, 0.15))
    snow = g.math("MULTIPLY", snow, g.math("GREATER_THAN", I["Snow"], 0.0))
    bump_s = g.n("ShaderNodeBump")
    bump_s.inputs["Strength"].default_value = 0.25
    g.link(g.noise(pos, 40.0, 2.0), bump_s.inputs["Height"])
    g.link(normal, bump_s.inputs["Normal"])
    g.link(g.mix("RGBA", snow, base, (0.88, 0.9, 0.94, 1)), go.inputs["Base Color"])
    g.link(g.mix("FLOAT", snow, rough, 0.6), go.inputs["Roughness"])
    g.link(g.mix("VECTOR", snow, normal, bump_s.outputs[0]), go.inputs["Normal"])
    g.link(g.math("MULTIPLY", coat_w, g.math("SUBTRACT", 1.0, snow)), go.inputs["Coat Weight"])
    g.link(coat_r, go.inputs["Coat Roughness"])
    g.link(bump_r.outputs[0], go.inputs["Coat Normal"])
    return ng


def _src(sock):
    if sock.is_linked:
        lk = sock.links[0]
        return {"node": lk.from_node.name, "out": lk.from_socket.identifier}
    v = sock.default_value
    return {"value": list(v) if hasattr(v, "__len__") else v}


def _apply_mat(mat, ng, vals):
    nt = mat.node_tree
    record = json.loads(mat.get(KEY, "{}"))
    for bsdf in [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]:
        gname = TAG + bsdf.name
        gn = nt.nodes.get(gname)
        if gn is None:  # first application: remember and rewire
            record[bsdf.name] = {k: _src(bsdf.inputs[k]) for k in WRAPPED}
            gn = nt.nodes.new("ShaderNodeGroup")
            gn.name, gn.label, gn.node_tree = gname, "ENV Weather", ng
            gn.location = bsdf.location.x - 260, bsdf.location.y
            for k in ("Base Color", "Roughness", "Coat Weight", "Coat Roughness"):
                s = bsdf.inputs[k]
                if s.is_linked:
                    nt.links.new(s.links[0].from_socket, gn.inputs[k])
                else:
                    gn.inputs[k].default_value = s.default_value
            if bsdf.inputs["Normal"].is_linked:
                nt.links.new(bsdf.inputs["Normal"].links[0].from_socket, gn.inputs["Normal"])
            else:  # unlinked = shading normal; an unlinked group vector would be (0,0,0)
                geo = nt.nodes.new("ShaderNodeNewGeometry")
                geo.name = TAG + "geo_" + bsdf.name
                geo.location = gn.location.x - 200, gn.location.y - 300
                nt.links.new(geo.outputs["Normal"], gn.inputs["Normal"])
            for k in WRAPPED:
                nt.links.new(gn.outputs[k], bsdf.inputs[k])
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
    for n in [n for n in nt.nodes if n.name.startswith(TAG)]:
        nt.nodes.remove(n)
    if KEY in mat:
        del mat[KEY]


def _snow_tree():
    ng = bpy.data.node_groups.get(SNOW_GN) or bpy.data.node_groups.new(SNOW_GN, "GeometryNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    ng.is_modifier = True
    for nm, kind, d in (("Geometry", "Geometry", None), ("Coverage", "Float", 0.7), ("Depth", "Float", 0.06),
                        ("Noise Scale", "Float", 1.5), ("Material", "Material", None)):
        s = ng.interface.new_socket(nm, in_out="INPUT", socket_type=f"NodeSocket{kind}")
        if d is not None:
            s.default_value = d
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    g = _G(ng)
    gi, go = g.n("NodeGroupInput"), g.n("NodeGroupOutput")
    I = gi.outputs  # noqa: E741
    sep_n = g.n("ShaderNodeSeparateXYZ")
    g.link(g.n("GeometryNodeInputNormal").outputs["Normal"], sep_n.inputs[0])
    sel = g.math("GREATER_THAN", sep_n.outputs["Z"], g.math("MULTIPLY_ADD", I["Coverage"], -0.8, 1.0))
    part = g.n("GeometryNodeSeparateGeometry", domain="FACE")
    g.link(I["Geometry"], part.inputs["Geometry"])
    g.link(sel, part.inputs["Selection"])
    sub = g.n("GeometryNodeSubdivideMesh")
    g.link(part.outputs["Selection"], sub.inputs["Mesh"])
    sub.inputs["Level"].default_value = 2
    nz = g.noise(g.n("GeometryNodeInputPosition").outputs[0], g.math("DIVIDE", 1.0, I["Noise Scale"]))
    h = g.math("MULTIPLY", g.math("MULTIPLY_ADD", nz, 0.8, 0.6), I["Depth"])  # never 0: no z-fighting
    off = g.n("ShaderNodeCombineXYZ")
    g.link(h, off.inputs["Z"])
    ext = g.n("GeometryNodeExtrudeMesh", mode="FACES")
    g.link(sub.outputs[0], ext.inputs["Mesh"])
    g.link(off.outputs[0], ext.inputs["Offset"])
    ext.inputs["Individual"].default_value = False
    smooth = g.n("GeometryNodeSetShadeSmooth")
    g.link(ext.outputs["Mesh"], smooth.inputs["Geometry"])
    sm = g.n("GeometryNodeSetMaterial")
    g.link(smooth.outputs[0], sm.inputs["Geometry"])
    g.link(I["Material"], sm.inputs["Material"])
    join = g.n("GeometryNodeJoinGeometry")
    g.link(sm.outputs[0], join.inputs[0])
    g.link(I["Geometry"], join.inputs[0])
    g.link(join.outputs[0], go.inputs[0])
    return ng


def _snow_material():
    mat = bpy.data.materials.get(SNOW_MAT) or bpy.data.materials.new(SNOW_MAT)
    b = bx.node(mat.node_tree, "BSDF_PRINCIPLED")
    for k, v in {"Base Color": (0.88, 0.9, 0.94, 1), "Roughness": 0.6, "Subsurface Weight": 0.6,
                 "Subsurface Radius": (0.6, 0.8, 1.0), "Subsurface Scale": 0.03}.items():
        b.inputs[k].default_value = v
    return mat


def _vertex_mask(ob, puddles, snow, scale):
    """Color attribute ENV_Weather (R puddle, G snow, B wall/streak) for engine shaders."""
    me = ob.data
    attr = me.color_attributes.get("ENV_Weather") or me.color_attributes.new("ENV_Weather", "FLOAT_COLOR", "POINT")
    mw, nm = ob.matrix_world, ob.matrix_world.to_3x3().inverted().transposed()
    cols = []
    for v in me.vertices:
        p, n = mw @ v.co, (nm @ v.normal).normalized()
        nz = noise.noise(Vector((p.x / scale, p.y / scale, 0.0))) * 0.5 + 0.5
        thr = 0.62 - 0.24 * puddles
        pud = (min(max((nz - thr) / 0.04, 0), 1) * min(max((n.z - 0.9) / 0.07, 0), 1)) if puddles else 0.0
        sthr = 1 - 0.8 * snow
        sn = min(max((n.z - sthr) / 0.15, 0), 1) if snow else 0.0
        cols.extend((pud, sn, 1 - n.z * n.z, 1.0))
    attr.data.foreach_set("color", cols)
    me.color_attributes.active_color_name = attr.name  # exporters write the active color
    return attr.name


def run(objects=None, wetness=0.0, puddles=0.0, ripples=0.0, streaks=0.0, snow=0.0, snow_depth=0.0,
        porosity=0.6, scale=3.0, vertex_mask=False, remove=False, **_):
    bx.object_mode()
    obs = [o for o in bx.objects(objects) if o.type == "MESH"]
    mats = {s.material for o in obs for s in o.material_slots if s.material and s.material.node_tree}
    if remove:
        for m in mats:
            _remove_mat(m)
        for o in obs:
            for md in [md for md in o.modifiers if md.name == SNOW_GN]:
                o.modifiers.remove(md)
            ca = o.data.color_attributes.get("ENV_Weather")
            if ca:
                o.data.color_attributes.remove(ca)
        return {"ok": True, "removed": sorted(m.name for m in mats), "objects": [o.name for o in obs]}
    no_mat = [o.name for o in obs if not any(s.material for s in o.material_slots)]
    ng = build_group()
    vals = dict(Wetness=wetness, Puddles=puddles, Ripples=ripples, Streaks=streaks, Snow=snow,
                Porosity=porosity, Scale=scale)
    for m in mats:
        _apply_mat(m, ng, vals)
    res = {"ok": True, "materials": sorted(m.name for m in mats), "objects": [o.name for o in obs],
           "params": {k: v for k, v in vals.items() if v}}
    if no_mat:
        res["warning"] = f"no material (skipped): {no_mat}"
    if snow_depth > 0:
        sg, smat = _snow_tree(), _snow_material()
        for o in obs:
            md = o.modifiers.get(SNOW_GN) or o.modifiers.new(SNOW_GN, "NODES")
            md.node_group = sg
            ids = {i.name: i.identifier for i in sg.interface.items_tree if getattr(i, "in_out", "") == "INPUT"}
            for k, v in (("Coverage", snow or 0.7), ("Depth", snow_depth), ("Noise Scale", scale), ("Material", smat)):
                getattr(md.properties.inputs, ids[k]).value = v
        res["snow_geometry"] = {"modifier": SNOW_GN, "depth_m": snow_depth}
    if vertex_mask:
        res["vertex_mask"] = [_vertex_mask(o, puddles, snow, scale) for o in obs][:1]
    if ripples and not puddles:
        res["note"] = "ripples only show inside puddles (--puddles > 0)"
    return res


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    for k in ("wetness", "puddles", "ripples", "streaks", "snow", "snow-depth"):
        p.add_argument(f"--{k}", type=float, default=0.0)
    p.add_argument("--porosity", type=float, default=0.6)
    p.add_argument("--scale", type=float, default=3.0)
    p.add_argument("--vertex-mask", action="store_true")
    p.add_argument("--remove", action="store_true")
    bx.cli(run, p)
