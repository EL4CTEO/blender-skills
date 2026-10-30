"""Groom hair curves on a surface with Blender's bundled hair node assets, and turn a groom into
game hair cards with a rendered strand atlas.

Groom: Add Empty Hair (5.2: attaches to --surface, UV, rest geometry, node Hair Dynamics), then
Generate (density per m^2, optional vertex-group mask) -> Clump -> Curl -> Droop (Displace +
Shrinkwrap off the scalp) -> Noise -> Set Profile, plus a
Principled Hair BSDF (melanin). Every asset stays a modifier with live inputs.
Cards: ribbons along --card-count well-spaced strands of the evaluated groom (UV v: root 0 -> tip 1,
one atlas column per card), plus an atlas rendered with Cycles from flat strand clumps:
T_<name>_BC (color + coverage alpha), T_<name>_RootTip, T_<name>_ID.
Usage:
  blender -b f.blend -P groom.py -- --surface Head [--mask Scalp] [--density 2000] [--children 100000] [--viewport 0.2]
      [--length 0.12]
      [--points 12] [--clump 0.5] [--curl 0] [--droop 0.8] [--noise 0.003] [--radius 0.00005] [--melanin 0.65]
      [--redness 0.1] [--roughness 0.3] [--seed 0] [--name Hair] [--save out.blend]
  blender -b f.blend -P groom.py -- --cards Hair [--card-count 120] [--card-width 0.012]
      [--atlas-columns 8] [--atlas-res 1024] [--out //textures] [--save out.blend]
  MCP: import groom; print(groom.run(surface="Head", density=20000, length=0.12))
"""
import os
import random
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

ASSETS = ("Generate Hair Curves", "Interpolate Hair Curves", "Clump Hair Curves", "Curl Hair Curves", "Displace Hair Curves",
          "Shrinkwrap Hair Curves", "Hair Curves Noise", "Set Hair Curve Profile")


def _assets():
    path = os.path.join(bpy.utils.system_resource("DATAFILES"), "assets", "nodes", "procedural_hair_node_assets.blend")
    need = [n for n in ASSETS if n not in bpy.data.node_groups]
    if need:
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.node_groups = need
    return {n: bpy.data.node_groups[n] for n in ASSETS}


def _modifier(ob, group, vals):
    md = ob.modifiers.get(group.name) or ob.modifiers.new(group.name, "NODES")
    md.node_group = group
    ids = {}
    for i in group.interface.items_tree:  # assets reuse names ("Surface" Object + Geometry): "Name:Type" picks one
        if getattr(i, "in_out", "") == "INPUT":
            ids.setdefault(i.name, i.identifier)
            ids[f"{i.name}:{i.socket_type[len('NodeSocket'):]}"] = i.identifier
    for k, v in vals.items():
        sock = getattr(md.properties.inputs, ids[k])
        if isinstance(v, tuple) and v[0] == "ATTR":
            sock.type, sock.attribute_name = "ATTRIBUTE", v[1]
        else:
            sock.value = v
    return md


def hair_material(name, melanin, redness, roughness):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    h = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    h.model, h.parametrization = "CHIANG", "MELANIN"
    h.inputs["Melanin"].default_value = melanin
    h.inputs["Melanin Redness"].default_value = redness
    h.inputs["Roughness"].default_value = roughness
    h.inputs["Radial Roughness"].default_value = 0.3
    nt.links.new(h.outputs[0], out.inputs["Surface"])
    return mat


def groom(surface, mask=None, density=2000.0, children=100000.0, viewport=0.2, length=0.12, points=12, clump=0.5, curl=0.0, droop=0.8,
          noise=0.003, radius=0.00005, melanin=0.65, redness=0.1, roughness=0.3, seed=0, name="Hair"):
    surf = bpy.data.objects[surface]
    if not surf.data.uv_layers:
        raise ValueError(f"{surface} needs a UV map (hair attaches by UV)")
    if mask and mask not in surf.vertex_groups:
        raise KeyError(f"vertex group {mask!r} not on {surface}")
    before = set(bpy.data.objects)
    bx.select_only([surf])
    with bpy.context.temp_override(object=surf, active_object=surf, selected_objects=[surf]):
        bpy.ops.object.curves_empty_hair_add()
    hair = next(o for o in bpy.data.objects if o not in before and o.type == "CURVES")
    hair.name = hair.data.name = name
    g = _assets()
    gen = {"Hair Length": length, "Density": density, "Control Points": points, "Seed": seed}
    if mask:
        gen["Density Mask"] = ("ATTR", mask)
    _modifier(hair, g["Generate Hair Curves"], gen)
    if children > 0:  # guides -> interpolated children: the production way to get strand counts
        ch = {"Density": children, "Viewport Amount": viewport, "Interpolation Guides": 4, "Seed": seed}
        if mask:
            ch["Density Mask"] = ("ATTR", mask)
        _modifier(hair, g["Interpolate Hair Curves"], ch)
    guide = max(0.004, length * 0.1)  # asset default 0.1 m clumps a whole head into a few tufts
    if clump > 0:
        _modifier(hair, g["Clump Hair Curves"], {"Factor": clump, "Shape": 0.5, "Guide Distance": guide, "Seed": seed})
    if curl > 0:
        _modifier(hair, g["Curl Hair Curves"], {"Factor": 1.0, "Radius": curl, "Frequency": 3.0,
                                                "Guide Distance": guide, "Seed": seed})
    if droop > 0:  # gravity: tips fall by droop x length, then pushed back above the scalp
        _modifier(hair, g["Displace Hair Curves"], {"Displace Vector": (0.0, 0.0, -droop * length), "Shape": 0.35})
        _modifier(hair, g["Shrinkwrap Hair Curves"], {"Surface Input Type": "Object", "Surface:Object": surf,
                                                      "Offset Distance": 0.002, "Lock Roots": True})
    if noise > 0:
        _modifier(hair, g["Hair Curves Noise"], {"Distance": noise, "Seed": seed})
    _modifier(hair, g["Set Hair Curve Profile"], {"Radius": radius, "Shape": 0.5})
    mat = hair_material("M_" + name, melanin, redness, roughness)
    hair.data.materials.clear()
    hair.data.materials.append(mat)
    for md in hair.modifiers:  # the material lives on the generated curves, set by the Generate input
        if md.node_group and md.node_group.name == "Generate Hair Curves":
            ids = {i.name: i.identifier for i in md.node_group.interface.items_tree if getattr(i, "in_out", "") == "INPUT"}
            getattr(md.properties.inputs, ids["Hair Material"]).value = mat
    stats = curve_stats(hair, surf)
    return {"ok": True, "hair": hair.name, "surface": surface, "modifiers": [m.name for m in hair.modifiers],
            "surface_modifiers": [m.name for m in surf.modifiers], "material": mat.name, **stats}


def _evaluated(hair):
    ev = hair.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    n = len(ev.points)
    pos = np.empty(n * 3, np.float32)
    ev.attributes["position"].data.foreach_get("vector", pos)
    off = np.empty(len(ev.curves) + 1, np.int32)
    ev.curve_offset_data.foreach_get("value", off)
    mw = np.array(hair.matrix_world, np.float32)
    return pos.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3], off


def curve_stats(hair, surf):
    pos, off = _evaluated(hair)
    if len(off) < 2:
        return {"curves": 0}
    roots, tips = pos[off[:-1]], pos[off[1:] - 1]
    seg = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    lens = np.array([seg[a:b - 1].sum() for a, b in zip(off[:-1], off[1:])])
    sinv = surf.matrix_world.inverted()
    sev = surf.evaluated_get(bpy.context.evaluated_depsgraph_get())
    gap = max((surf.matrix_world @ sev.closest_point_on_mesh(sinv @ Vector(r))[1] - Vector(r)).length
              for r in roots[:: max(1, len(roots) // 400)])
    return {"curves": int(len(off) - 1), "points": int(len(pos)), "length_mean_m": round(float(lens.mean()), 4),
            "root_gap_max_m": round(gap, 5), "tip_z_mean": round(float(tips[:, 2].mean()), 4)}


def _spaced(roots, k, rng):
    """Farthest-point sampling: k well-spread curve indices."""
    k = min(k, len(roots))
    pick = [rng.randrange(len(roots))]
    d = np.linalg.norm(roots - roots[pick[0]], axis=1)
    for _ in range(k - 1):
        i = int(d.argmax())
        pick.append(i)
        d = np.minimum(d, np.linalg.norm(roots - roots[i], axis=1))
    return pick


def build_cards(hair, count=120, width=0.012, columns=8, seed=0):
    surf = hair.data.surface
    pos, off = _evaluated(hair)
    roots = pos[off[:-1]]
    rng = random.Random(seed)
    idx = _spaced(roots, count, rng)
    sev = surf.evaluated_get(bpy.context.evaluated_depsgraph_get()) if surf else None
    verts, faces, uvs = [], [], []
    for c, ci in enumerate(idx):
        p = pos[off[ci]:off[ci + 1]]
        if len(p) < 2:
            continue
        nrm = Vector((0, 0, 1))
        if sev is not None:  # side vector = tangent x surface normal: cards lie flat on the head
            sinv = surf.matrix_world.inverted()
            nrm = (surf.matrix_world.to_3x3() @ sev.closest_point_on_mesh(sinv @ Vector(p[0]))[2]).normalized()
        col = c % columns
        u0, u1 = col / columns, (col + 1) / columns
        base = len(verts)
        n = len(p)
        for j in range(n):
            t = Vector(p[min(j + 1, n - 1)] - p[max(j - 1, 0)]).normalized()
            side = t.cross(nrm)
            if side.length < 1e-6:
                side = t.orthogonal()
            side.normalize()
            w = width * 0.5 * (1.0 - 0.7 * j / (n - 1))  # taper to 30% at the tip
            verts += [Vector(p[j]) - side * w, Vector(p[j]) + side * w]
            v = j / (n - 1)
            uvs += [(u0, v), (u1, v)]
        for j in range(n - 1):
            a = base + 2 * j
            faces.append((a, a + 1, a + 3, a + 2))
    me = bpy.data.meshes.new(hair.name + "_Cards")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    uv = me.uv_layers.new(name="UVMap")
    loop_v = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", loop_v)
    uv.uv.foreach_set("vector", np.array(uvs, np.float32)[loop_v].ravel())
    ob = bpy.data.objects.get(me.name)
    if ob is None:
        ob = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(ob)
    else:
        ob.data = me
    return ob, len(idx), len(faces)


def render_atlas(name, columns=8, res=1024, out="//textures", seed=0, color=(0.12, 0.07, 0.04)):
    """Flat strand clumps (one per column) rendered orthographically: BC+alpha, root-tip, ID."""
    rng = np.random.default_rng(seed)
    src = bpy.context.window.scene if bpy.context.window else bpy.context.scene
    sc = bpy.data.scenes.new("HairAtlas")
    strands, pts = 40, 16
    curves = bpy.data.hair_curves.new("HairAtlas")
    curves.add_curves([pts] * (strands * columns))
    P = np.zeros((strands * columns, pts, 3), np.float32)
    for c in range(columns):
        cx = (c + 0.5) / columns
        for s in range(strands):
            k = c * strands + s
            x0 = cx + rng.uniform(-0.38, 0.38) / columns
            ln = rng.uniform(0.82, 0.98)
            t = np.linspace(0, 1, pts)
            wave = 0.04 / columns * np.sin(t * rng.uniform(4, 9) + rng.uniform(0, 6.28))
            pinch = (cx - x0) * t ** 1.5 * 0.6  # clump toward the column center at the tip
            P[k, :, 0] = x0 + wave + pinch
            P[k, :, 2] = 0.01 + t * ln
    curves.attributes["position"].data.foreach_set("vector", P.ravel())
    rad = curves.attributes.get("radius") or curves.attributes.new("radius", "FLOAT", "POINT")
    rad.data.foreach_set("value", np.full(strands * columns * pts, 0.6 / res, np.float32))  # ~1.2 px wide
    ob = bpy.data.objects.new("HairAtlas", curves)
    sc.collection.objects.link(ob)
    cam = bpy.data.objects.new("AtlasCam", bpy.data.cameras.new("AtlasCam"))
    sc.collection.objects.link(cam)
    cam.data.type, cam.data.ortho_scale = "ORTHO", 1.0
    cam.location, cam.rotation_euler = (0.5, -2.0, 0.5), (np.pi / 2, 0, 0)
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.samples, sc.cycles.device = 16, "CPU"
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.film_transparent = True
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGBA"
    mat = bpy.data.materials.new("HairAtlas_Emit")
    nt = mat.node_tree
    nt.nodes.clear()
    o, em, info = (nt.nodes.new(t) for t in ("ShaderNodeOutputMaterial", "ShaderNodeEmission", "ShaderNodeHairInfo"))
    nt.links.new(em.outputs[0], o.inputs["Surface"])
    curves.materials.append(mat)
    out_dir = bpy.path.abspath(out)
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for key, setup in (("BC", "color"), ("RootTip", "Intercept"), ("ID", "Random")):
        for lk in list(em.inputs["Color"].links):
            nt.links.remove(lk)
        if setup == "color":  # darker roots, the usual card albedo
            mix = nt.nodes.get("rootdark") or nt.nodes.new("ShaderNodeMix")
            mix.name, mix.data_type = "rootdark", "RGBA"
            mix.inputs[6].default_value = tuple(x * 0.45 for x in color) + (1,)
            mix.inputs[7].default_value = (*color, 1)
            nt.links.new(info.outputs["Intercept"], mix.inputs[0])
            nt.links.new(mix.outputs[2], em.inputs["Color"])
        else:
            nt.links.new(info.outputs[setup], em.inputs["Color"])
        sc.view_settings.view_transform = "Standard" if key == "BC" else "Raw"  # data maps stay linear
        sc.render.filepath = os.path.join(out_dir, f"T_{name}_{key}.png")
        with bpy.context.temp_override(scene=sc):
            bpy.ops.render.render(write_still=True, scene=sc.name)
        paths[key] = sc.render.filepath
    for d in (ob, cam):
        bpy.data.objects.remove(d)
    bpy.data.scenes.remove(sc)
    if bpy.context.window:
        bpy.context.window.scene = src
    return paths


def card_material(name, bc_path):
    mat = bpy.data.materials.get("M_" + name) or bpy.data.materials.new("M_" + name)
    nt = mat.node_tree
    bsdf = bx.node(nt, "BSDF_PRINCIPLED")
    tex = bx.node(nt, "TEX_IMAGE") or nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(bc_path, check_existing=True)
    tex.location = bsdf.location.x - 320, bsdf.location.y
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.45
    mat.surface_render_method = "DITHERED"
    mat.use_backface_culling = False  # cards are seen from both sides
    return mat


def run(surface=None, cards=None, mask=None, density=2000.0, children=100000.0, viewport=0.2, length=0.12, points=12, clump=0.5, curl=0.0,
        droop=0.8, noise=0.003, radius=0.00005, melanin=0.65, redness=0.1, roughness=0.3, seed=0, name="Hair",
        card_count=120, card_width=0.012, atlas_columns=8, atlas_res=1024, out="//textures", **_):
    bx.object_mode()
    if surface:
        return groom(surface, mask, density, children, viewport, length, points, clump, curl, droop, noise, radius, melanin, redness,
                     roughness, seed, name)
    if not cards:
        raise ValueError("give --surface (groom) or --cards HAIR_OBJECT")
    hair = bpy.data.objects[cards]
    ob, n_cards, quads = build_cards(hair, card_count, card_width, atlas_columns, seed)
    paths = render_atlas(cards + "Card", atlas_columns, atlas_res, out, seed)
    mat = card_material(cards + "Card", paths["BC"])
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    if hair.parent:
        ob.parent = hair.parent
        ob.matrix_parent_inverse = hair.parent.matrix_world.inverted()
    return {"ok": True, "cards": ob.name, "card_count": n_cards, "tris": quads * 2, "atlas": paths,
            "material": mat.name}


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--surface", default=None)
    p.add_argument("--cards", default=None, help="hair curves object to convert to cards")
    p.add_argument("--mask", default=None, help="surface vertex group = density mask")
    for k, t, d in (("density", float, 2000.0), ("children", float, 100000.0), ("viewport", float, 0.2), ("length", float, 0.12), ("points", int, 12),
                    ("clump", float, 0.5), ("curl", float, 0.0), ("droop", float, 0.8), ("noise", float, 0.003), ("radius", float, 0.00005),
                    ("melanin", float, 0.65), ("redness", float, 0.1), ("roughness", float, 0.3), ("seed", int, 0),
                    ("card-count", int, 120), ("card-width", float, 0.012), ("atlas-columns", int, 8),
                    ("atlas-res", int, 1024)):
        p.add_argument(f"--{k}", type=t, default=d)
    p.add_argument("--name", default="Hair")
    p.add_argument("--out", default="//textures")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
