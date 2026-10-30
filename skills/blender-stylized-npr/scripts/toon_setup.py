"""Reversible toon/cel look: banded shading, shadow tint, rim, hard specular, inverted-hull outlines,
smoothed outline normals for engine shaders, and an optional Line Art (Grease Pencil) pass.

--lighting key (default): N.L against one sun (--light, created if missing) through drivers. Works in
Cycles and EEVEE and matches engine toon shaders. --lighting scene: EEVEE Shader to RGB, reacting
to every light and cast shadows (Shader to RGB is constant in Cycles). Sets view transform Standard
(AgX desaturates flat colors). --remove restores materials, slots, modifiers and view transform.
Usage:
  blender -b f.blend -P toon_setup.py -- --objects Hero Sword [--bands 2|3] [--shadow-tint 0.6 0.55 0.75]
      [--threshold 0.0] [--softness 0.02] [--rim 0.4] [--spec 0.0] [--lighting key|scene] [--light Sun]
      [--outline 0.004] [--outline-color 0.05 0.04 0.06] [--outline-group LineWidth]
      [--smooth-normals] [--line-art] [--line-radius 0.002] [--save out.blend]
  blender -b f.blend -P toon_setup.py -- --objects Hero Sword --remove
  MCP: import toon_setup as t; print(t.run(objects=["Hero"], bands=3, outline=0.004, rim=0.4))
"""
import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

GROUP, TAG, KEY = "NPR_Toon", "NPR_", "npr_toon"
OUTLINE_MAT, OUTLINE_MOD, NORMAL_ATTR = "NPR_M_Outline", "NPR_Outline", "NPR_OutlineNormal"
LINEART = "NPR_LineArt"


def _lin(c):
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

    def math(self, op, a, b=0.0, clamp=False):
        m = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(m.inputs[0], a)
        self.set(m.inputs[1], b)
        return m.outputs[0]

    def vmath(self, op, a, b=None):
        m = self.n("ShaderNodeVectorMath", operation=op)
        self.set(m.inputs[0], a)
        self.set(m.inputs[1], b)
        return m.outputs["Value" if op == "DOT_PRODUCT" else "Vector"]

    def step(self, v, edge, soft):
        m = self.n("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        self.set(m.inputs[0], v)
        self.set(m.inputs[1], self.math("SUBTRACT", edge, soft))
        self.set(m.inputs[2], self.math("ADD", edge, soft))
        return m.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        m = self.n("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self.set(m.inputs[0], fac)
        self.set(m.inputs[6], a)
        self.set(m.inputs[7], b)
        return m.outputs[2]


def build_group():
    ng = bpy.data.node_groups.get(GROUP) or bpy.data.node_groups.new(GROUP, "ShaderNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    for nm, kind, d in (("Base Color", "Color", (0.8, 0.8, 0.8, 1)), ("Light Direction", "Vector", (0.3, -0.5, 0.8)),
                        ("Scene Lighting", "Float", 0.0), ("Bands", "Float", 2.0), ("Threshold", "Float", 0.0),
                        ("Softness", "Float", 0.02), ("Shadow Tint", "Color", (0.32, 0.27, 0.52, 1)),
                        ("Rim", "Float", 0.0), ("Specular", "Float", 0.0)):
        s = ng.interface.new_socket(nm, in_out="INPUT", socket_type=f"NodeSocket{kind}")
        s.default_value = d
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    g = _G(ng)
    gi, go = g.n("NodeGroupInput"), g.n("NodeGroupOutput")
    I = gi.outputs  # noqa: E741
    geo = g.n("ShaderNodeNewGeometry")
    N, V = geo.outputs["Normal"], geo.outputs["Incoming"]
    L = g.vmath("NORMALIZE", I["Light Direction"])
    ndl = g.vmath("DOT_PRODUCT", N, L)
    # scene lighting (EEVEE): luminance of a lit white diffuse, remapped to the same -1..1 range
    s2r = g.n("ShaderNodeShaderToRGB")
    g.link(g.n("ShaderNodeBsdfDiffuse").outputs[0], s2r.inputs[0])
    lum = g.n("ShaderNodeRGBToBW")
    g.link(s2r.outputs["Color"], lum.inputs[0])
    scene_v = g.n("ShaderNodeMapRange", clamp=False)
    g.link(lum.outputs[0], scene_v.inputs[0])
    scene_v.inputs[1].default_value, scene_v.inputs[2].default_value = 0.0, 0.6
    scene_v.inputs[3].default_value, scene_v.inputs[4].default_value = -1.0, 1.0
    shade = g.n("ShaderNodeMix", data_type="FLOAT")
    g.link(I["Scene Lighting"], shade.inputs[0])
    g.link(ndl, shade.inputs[2])
    g.link(scene_v.outputs[0], shade.inputs[3])
    s = shade.outputs[0]
    lit = g.step(s, I["Threshold"], I["Softness"])
    # optional mid band (Bands >= 3) halfway between shadow and light, 0.45 above the threshold
    mid = g.math("MULTIPLY", g.step(s, g.math("ADD", I["Threshold"], 0.45), I["Softness"]),
                 g.math("GREATER_THAN", I["Bands"], 2.5))
    shadow_col = g.mix(1.0, I["Base Color"], I["Shadow Tint"], "MULTIPLY")
    mid_col = g.mix(0.5, shadow_col, I["Base Color"])
    three = g.math("GREATER_THAN", I["Bands"], 2.5)
    col = g.mix(lit, shadow_col, g.mix(three, I["Base Color"], g.mix(mid, mid_col, I["Base Color"])))
    # hard specular: N.H above 1 - size (Blinn half vector), only on the lit side
    H = g.vmath("NORMALIZE", g.vmath("ADD", L, V))
    spec_on = g.math("GREATER_THAN", I["Specular"], 0.0)
    spec = g.step(g.vmath("DOT_PRODUCT", N, H), g.math("SUBTRACT", 1.0, g.math("MULTIPLY", I["Specular"], 0.03)), 0.002)
    spec = g.math("MULTIPLY", g.math("MULTIPLY", spec, lit), spec_on)
    col = g.mix(spec, col, (1, 1, 1, 1), "SCREEN")
    # rim: grazing angles on the lit side
    lw = g.n("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    rim = g.step(lw.outputs["Facing"], g.math("SUBTRACT", 1.0, g.math("MULTIPLY", I["Rim"], 0.35)), 0.02)
    rim = g.math("MULTIPLY", g.math("MULTIPLY", rim, lit), g.math("GREATER_THAN", I["Rim"], 0.0))
    col = g.mix(g.math("MULTIPLY", rim, 0.6), col, (1, 1, 1, 1), "SCREEN")
    em = g.n("ShaderNodeEmission")
    g.link(col, em.inputs["Color"])
    g.link(em.outputs[0], go.inputs[0])
    return ng


def _outline_material(color):
    mat = bpy.data.materials.get(OUTLINE_MAT) or bpy.data.materials.new(OUTLINE_MAT)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em, tr, mx = (nt.nodes.new(t) for t in ("ShaderNodeEmission", "ShaderNodeBsdfTransparent", "ShaderNodeMixShader"))
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    em.inputs["Color"].default_value = _lin(color)
    nt.links.new(geo.outputs["Backfacing"], mx.inputs[0])  # flipped hull: only its far shell faces us
    nt.links.new(em.outputs[0], mx.inputs[1])
    nt.links.new(tr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    mat.use_backface_culling = True  # EEVEE/Workbench; Cycles relies on the Backfacing mix
    mat.surface_render_method = "DITHERED"
    return mat


def _key_light(name):
    if name:
        return bpy.data.objects[name]
    sun = next((o for o in bpy.context.scene.objects if o.type == "LIGHT" and o.data.type == "SUN"), None)
    if sun is None:
        sun = bpy.data.objects.new("NPR_Key", bpy.data.lights.new("NPR_Key", "SUN"))
        bpy.context.scene.collection.objects.link(sun)
        sun.rotation_euler = (0.7, 0.0, 0.6)
        sun.data.energy = 3.0
    return sun


def _drive_light(sock, sun):
    """Light Direction = the sun's local +Z in world space (the sun shines along -Z)."""
    for i in range(3):
        fc = sock.driver_add("default_value", i)
        d = fc.driver
        d.type = "SCRIPTED"
        for v in list(d.variables):
            d.variables.remove(v)
        var = d.variables.new()
        var.name, var.type = "m", "SINGLE_PROP"
        var.targets[0].id, var.targets[0].data_path = sun, f"matrix_world[2][{i}]"
        d.expression = "m"


def _apply_mat(mat, ng, vals, sun):
    nt = mat.node_tree
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    bsdf = bx.node(nt, "BSDF_PRINCIPLED")
    if out is None:
        return False
    gn = nt.nodes.get(TAG + "toon")
    surf = out.inputs["Surface"]
    if gn is None:  # first application: remember the original surface
        rec = {"out": out.name}
        if surf.is_linked:
            rec["from"] = [surf.links[0].from_node.name, surf.links[0].from_socket.identifier]
        mat[KEY] = json.dumps(rec)
        gn = nt.nodes.new("ShaderNodeGroup")
        gn.name, gn.label, gn.node_tree = TAG + "toon", "NPR Toon", ng
        gn.location = out.location.x - 220, out.location.y + 220
    # (re)wire on every run: re-running rebuilds the group, which recreates its sockets and drops links
    if bsdf is not None:
        bc = bsdf.inputs["Base Color"]
        if bc.is_linked:
            nt.links.new(bc.links[0].from_socket, gn.inputs["Base Color"])
        else:
            gn.inputs["Base Color"].default_value = bc.default_value
    nt.links.new(gn.outputs[0], surf)
    for k, v in vals.items():
        gn.inputs[k].default_value = v
    if sun is not None:
        _drive_light(gn.inputs["Light Direction"], sun)
    return True


def _remove_mat(mat):
    nt = mat.node_tree
    rec = json.loads(mat.get(KEY, "{}"))
    out = nt.nodes.get(rec.get("out", ""))
    for nd in [nd for nd in nt.nodes if nd.name.startswith(TAG)]:
        if nd.inputs.get("Light Direction") is not None:
            nd.inputs["Light Direction"].driver_remove("default_value")
        nt.nodes.remove(nd)
    if out is not None and "from" in rec and rec["from"][0] in nt.nodes:
        nt.links.new(nt.nodes[rec["from"][0]].outputs[rec["from"][1]], out.inputs["Surface"])
    if KEY in mat:
        del mat[KEY]


def smooth_outline_normals(ob, uv=None):
    """NPR_OutlineNormal corner color: position-averaged normal in tangent space, packed 0.5 + 0.5 n.

    Engine outline shaders extrude along this instead of the split normal, so hard edges don't open
    gaps. Decode: n = TBN * (c * 2 - 1)."""
    me = ob.data
    if not me.uv_layers:
        raise ValueError(f"{ob.name}: --smooth-normals needs a UV map (tangent space)")
    me.calc_tangents(uvmap=uv or me.uv_layers.active.name)
    nl, nv = len(me.loops), len(me.vertices)
    co = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get("co", co)
    key = np.unique(np.round(co.reshape(-1, 3), 5), axis=0, return_inverse=True)[1].ravel()
    vn = np.empty(nv * 3, np.float32)
    me.vertex_normals.foreach_get("vector", vn)
    acc = np.zeros((key.max() + 1, 3))
    np.add.at(acc, key, vn.reshape(-1, 3))  # weld split vertices by position
    acc /= np.maximum(np.linalg.norm(acc, axis=1), 1e-9)[:, None]
    lv = np.empty(nl, np.int32)
    me.loops.foreach_get("vertex_index", lv)
    t, n, sgn = np.empty(nl * 3, np.float32), np.empty(nl * 3, np.float32), np.empty(nl, np.float32)
    me.loops.foreach_get("tangent", t)
    me.loops.foreach_get("normal", n)
    me.loops.foreach_get("bitangent_sign", sgn)
    t, n = t.reshape(-1, 3), n.reshape(-1, 3)
    b = np.cross(n, t) * sgn[:, None]
    s = acc[key[lv]]
    ts = np.stack([(t * s).sum(1), (b * s).sum(1), (n * s).sum(1)], 1)
    me.free_tangents()
    at = me.color_attributes.get(NORMAL_ATTR) or me.color_attributes.new(NORMAL_ATTR, "FLOAT_COLOR", "CORNER")
    at.data.foreach_set("color", np.hstack([ts * 0.5 + 0.5, np.ones((nl, 1))]).astype(np.float32).ravel())
    return float(ts[:, 2].min())


def _line_art(radius, color):
    ob = bpy.data.objects.get(LINEART)
    if ob is None:
        gp = bpy.data.grease_pencils.new(LINEART)
        gp.layers.new("Lines")
        ob = bpy.data.objects.new(LINEART, gp)
        bpy.context.scene.collection.objects.link(ob)
    gp = ob.data
    mat = bpy.data.materials.get("NPR_M_Line") or bpy.data.materials.new("NPR_M_Line")
    if not mat.is_grease_pencil:
        bpy.data.materials.create_gpencil_data(mat)
    mat.grease_pencil.color = _lin(color)
    if mat.name not in gp.materials:
        gp.materials.append(mat)
    md = ob.modifiers.get("LineArt") or ob.modifiers.new("LineArt", "LINEART")
    md.source_type, md.target_layer, md.target_material = "SCENE", "Lines", mat
    md.use_contour = md.use_crease = md.use_intersection = True
    md.radius = radius
    return ob.name


def run(objects=None, bands=2, shadow_tint=(0.6, 0.55, 0.75), threshold=0.0, softness=0.02, rim=0.0,
        spec=0.0, lighting="key", light=None, outline=0.004, outline_color=(0.05, 0.04, 0.06),
        outline_group=None, smooth_normals=False, line_art=False, line_radius=0.002, remove=False, **_):
    bx.object_mode()
    sc = bpy.context.scene
    obs = [o for o in bx.objects(objects) if o.type == "MESH"]
    mats = {s.material for o in obs for s in o.material_slots if s.material and s.material.node_tree
            and s.material.name != OUTLINE_MAT}
    if remove:
        for m in mats:
            _remove_mat(m)
        for o in obs:
            md = o.modifiers.get(OUTLINE_MOD)
            if md:
                o.modifiers.remove(md)
            idx = o.data.materials.find(OUTLINE_MAT)
            if idx >= 0:
                o.data.materials.pop(index=idx)
            ca = o.data.color_attributes.get(NORMAL_ATTR)
            if ca:
                o.data.color_attributes.remove(ca)
        if KEY in sc:
            sc.view_settings.view_transform = sc[KEY]
            del sc[KEY]
        la = bpy.data.objects.get(LINEART)
        if la and line_art:
            bpy.data.objects.remove(la)
        return {"ok": True, "removed": sorted(m.name for m in mats), "objects": [o.name for o in obs]}
    if lighting not in ("key", "scene"):
        raise ValueError("--lighting must be key or scene")
    sun = _key_light(light) if lighting == "key" else None
    ng = build_group()
    vals = {"Bands": float(bands), "Threshold": threshold, "Softness": softness, "Shadow Tint": _lin(shadow_tint),
            "Rim": rim, "Specular": spec, "Scene Lighting": 1.0 if lighting == "scene" else 0.0}
    done = [m.name for m in mats if _apply_mat(m, ng, vals, sun)]
    if KEY not in sc:
        sc[KEY] = sc.view_settings.view_transform
    sc.view_settings.view_transform = "Standard"
    res = {"ok": True, "objects": [o.name for o in obs], "materials": sorted(done), "lighting": lighting,
           "view_transform": "Standard"}
    if sun is not None:
        res["key_light"] = sun.name
    if lighting == "scene" and sc.render.engine != "BLENDER_EEVEE":
        res["warning"] = "lighting=scene needs EEVEE (Shader to RGB is constant in Cycles)"
    no_mat = [o.name for o in obs if not any(s.material for s in o.material_slots)]
    if no_mat:
        res["warning"] = f"no material (skipped): {no_mat}"
    if outline > 0:
        omat = _outline_material(outline_color)
        for o in obs:
            if o.data.materials.find(OUTLINE_MAT) < 0:
                o.data.materials.append(omat)
            md = o.modifiers.get(OUTLINE_MOD) or o.modifiers.new(OUTLINE_MOD, "SOLIDIFY")
            md.thickness, md.offset = outline, 1.0  # grow outward only
            md.use_flip_normals, md.use_rim, md.use_quality_normals = True, False, True
            md.material_offset = o.data.materials.find(OUTLINE_MAT)  # shell faces use the outline slot
            if outline_group:
                md.vertex_group = outline_group if outline_group in o.vertex_groups else ""
        res["outline"] = {"modifier": OUTLINE_MOD, "thickness_m": outline}
    if smooth_normals:
        res["outline_normals"] = {o.name: {"attribute": NORMAL_ATTR, "min_z": round(smooth_outline_normals(o), 3)}
                                  for o in obs}
    if line_art:
        res["line_art"] = _line_art(line_radius, outline_color)
        if sc.camera is None:
            res["warning"] = "Line Art needs a scene camera"
    return res


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--bands", type=int, default=2, choices=(2, 3))
    p.add_argument("--shadow-tint", type=float, nargs=3, default=(0.6, 0.55, 0.75), help="sRGB multiplier")
    for k, d in (("threshold", 0.0), ("softness", 0.02), ("rim", 0.0), ("spec", 0.0), ("outline", 0.004),
                 ("line-radius", 0.002)):
        p.add_argument(f"--{k}", type=float, default=d)
    p.add_argument("--lighting", default="key", choices=("key", "scene"))
    p.add_argument("--light", default=None, help="sun object for key lighting (default: first sun)")
    p.add_argument("--outline-color", type=float, nargs=3, default=(0.05, 0.04, 0.06), help="sRGB")
    p.add_argument("--outline-group", default=None, help="vertex group scaling outline width")
    p.add_argument("--smooth-normals", action="store_true")
    p.add_argument("--line-art", action="store_true")
    p.add_argument("--remove", action="store_true")
    bx.cli(run, p)
