"""Game-ready terrain: noise (fbm, ridged mountains, rolling hills) or a heightmap image on a grid,
thermal erosion, terraces, flattened play areas, slope/height attributes, an auto slope/height
material, and engine exports (16-bit heightmap + RGBA splat map, same grid).

Grid --res is vertices per side: use 2^n + 1 (129, 257, 513, 1025) so heightmaps import 1:1 into
Unity Terrain / UE Landscape. Attributes ENV_Slope (deg / 90) and ENV_Height (0-1) drive the material
and blender-environment-kits scatter.py.
Usage:
  blender -b f.blend -P terrain.py -- [--size 200] [--res 257] [--height 30] [--type fbm|ridged|hills]
      [--scale 80] [--octaves 6] [--seed 0] [--heightmap hm.png] [--erosion 20] [--terrace 0]
      [--flatten 0 0 15] [--material] [--export-heightmap //T_Height.png|.raw] [--export-splat //T_Splat.png]
      [--name Terrain] [--save out.blend]
  MCP: import terrain; print(terrain.run(size=200, height=30, type="ridged", erosion=20, material=True))
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector, noise

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

ROCK_DEG, SNOW_H = 35.0, 0.75  # rock above 35 deg, snow above 75% height on gentler slopes


def _noise_field(res, size, kind, scale, octaves, seed):
    off = Vector((seed * 31.7, seed * 17.3, seed * 7.1))
    xs = np.linspace(-size / 2, size / 2, res)
    h = np.empty((res, res), np.float64)
    basis = "PERLIN_ORIGINAL"
    for j, y in enumerate(xs):
        for i, x in enumerate(xs):
            p = Vector((x / scale, y / scale, 0.0)) + off
            if kind == "ridged":
                h[j, i] = noise.ridged_multi_fractal(p, 1.0, 2.0, octaves, 1.0, 2.0, noise_basis=basis)
            elif kind == "hills":
                h[j, i] = noise.hetero_terrain(p, 1.0, 2.0, min(octaves, 4), 0.5, noise_basis=basis)
            else:
                h[j, i] = noise.fractal(p, 1.0, 2.0, octaves, noise_basis=basis)
    return h


def _heightmap(path, res):
    img = bpy.data.images.load(bpy.path.abspath(path), check_existing=True)
    img.colorspace_settings.is_data = True
    w, hgt = img.size
    a = np.empty(w * hgt * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(hgt, w, 4)[..., 0]
    yi = np.linspace(0, hgt - 1, res).round().astype(int)
    xi = np.linspace(0, w - 1, res).round().astype(int)
    return a[np.ix_(yi, xi)].astype(np.float64)


def _erode(h, cell, steps, talus_deg=33.0, rate=0.25):
    """Thermal erosion: material above the talus angle slides to lower neighbours (4-neighbourhood)."""
    talus = math.tan(math.radians(talus_deg)) * cell
    for _ in range(steps):
        move = np.zeros_like(h)
        for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
            nb = np.roll(h, sh, axis=ax)
            d = h - nb - talus
            d[d < 0] = 0
            if ax == 0:
                d[0 if sh == 1 else -1, :] = 0  # no wrap-around at the borders
            else:
                d[:, 0 if sh == 1 else -1] = 0
            m = d * rate * 0.25
            move -= m
            move += np.roll(m, -sh, axis=ax)
        h = h + move
    return h


def _slope_deg(h, cell):
    gy, gx = np.gradient(h, cell)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def _material(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = bx.node(nt, "BSDF_PRINCIPLED")
    for n in [n for n in nt.nodes if n.name.startswith("ENV_T_")]:
        nt.nodes.remove(n)

    def nn(t, **kw):
        n = nt.nodes.new(t)
        n.name = "ENV_T_" + n.name
        for k, v in kw.items():
            setattr(n, k, v)
        return n
    sl = nn("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="ENV_Slope")
    ht = nn("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="ENV_Height")
    tc = nn("ShaderNodeTexCoord")
    nz = nn("ShaderNodeTexNoise")
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nz.inputs["Scale"].default_value = 0.15
    nz.inputs["Detail"].default_value = 6.0

    def ramp(src, lo, hi):
        m = nn("ShaderNodeMapRange", clamp=True)
        add = nn("ShaderNodeMath", operation="MULTIPLY_ADD")
        nt.links.new(nz.outputs["Factor"], add.inputs[0])
        add.inputs[1].default_value = 0.12
        nt.links.new(src, add.inputs[2])
        nt.links.new(add.outputs[0], m.inputs[0])
        m.inputs[1].default_value, m.inputs[2].default_value = lo, hi
        return m.outputs[0]
    rock = ramp(sl.outputs["Fac"], ROCK_DEG / 90 - 0.03, ROCK_DEG / 90 + 0.03)
    snow = ramp(ht.outputs["Fac"], SNOW_H - 0.03, SNOW_H + 0.03)
    snow_ok = nn("ShaderNodeMath", operation="MULTIPLY")
    nt.links.new(snow, snow_ok.inputs[0])
    nt.links.new(ramp(sl.outputs["Fac"], 0.5, 0.42), snow_ok.inputs[1])  # snow slides off > ~40 deg

    def mix(fac, a, b):
        m = nn("ShaderNodeMix", data_type="RGBA")
        nt.links.new(fac, m.inputs[0])
        for i, v in ((6, a), (7, b)):
            if isinstance(v, bpy.types.NodeSocket):
                nt.links.new(v, m.inputs[i])
            else:
                m.inputs[i].default_value = v
        return m.outputs[2]
    grass = mix(nz.outputs["Factor"], (0.045, 0.075, 0.02, 1), (0.08, 0.1, 0.03, 1))  # measured-range grass albedo
    col = mix(snow_ok.outputs[0], mix(rock, grass, (0.2, 0.18, 0.16, 1)), (0.8, 0.82, 0.86, 1))
    nt.links.new(col, bsdf.inputs["Base Color"])
    rough = mix(rock, (0.85, 0.85, 0.85, 1), (0.7, 0.7, 0.7, 1))
    bw = nn("ShaderNodeRGBToBW")
    nt.links.new(rough, bw.inputs[0])
    nt.links.new(bw.outputs[0], bsdf.inputs["Roughness"])
    return mat


def _save_png16(path, rgba, res, bw):
    img = bpy.data.images.new(os.path.basename(path), res, res, alpha=not bw, float_buffer=True)
    img.colorspace_settings.is_data = True
    img.pixels.foreach_set(rgba.astype(np.float32).ravel())
    sc = bpy.context.scene
    st, vt = sc.render.image_settings, sc.view_settings.view_transform
    prev = (st.file_format, st.color_mode, st.color_depth)
    st.file_format, st.color_mode, st.color_depth = "PNG", "BW" if bw else "RGBA", "16"
    sc.view_settings.view_transform = "Raw"  # write data values, not a display transform
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        img.save_render(path, scene=sc)
    finally:
        st.file_format, st.color_mode, st.color_depth = prev
        sc.view_settings.view_transform = vt
        bpy.data.images.remove(img)
    return path


def run(size=200.0, res=257, height=30.0, type="fbm", scale=80.0, octaves=6, seed=0, heightmap=None,
        erosion=0, terrace=0.0, flatten=None, material=False, export_heightmap=None, export_splat=None,
        name="Terrain", **_):
    bx.object_mode()
    cell = size / (res - 1)
    h = _heightmap(heightmap, res) if heightmap else _noise_field(res, size, type, scale, octaves, seed)
    h = (h - h.min()) / max(np.ptp(h), 1e-9) * height
    if erosion:
        h = _erode(h, cell, int(erosion))
    if terrace > 0:
        frac = (h / terrace) % 1.0
        h = (np.floor(h / terrace) + np.clip((frac - 0.75) / 0.25, 0, 1)) * terrace  # flats with short risers
    xs = np.linspace(-size / 2, size / 2, res)
    X, Y = np.meshgrid(xs, xs)
    if flatten:
        cx, cy, rad = flatten
        d = np.hypot(X - cx, Y - cy)
        target = h[np.abs(d) <= rad].mean() if (d <= rad).any() else h.mean()
        w = np.clip((d - rad) / (rad * 0.6), 0, 1)
        w = w * w * (3 - 2 * w)  # smoothstep blend back into the terrain
        h = target + (h - target) * w
    slope = _slope_deg(h, cell)
    hn = (h - h.min()) / max(np.ptp(h), 1e-9)
    me = bpy.data.meshes.get(name) or bpy.data.meshes.new(name)
    me.clear_geometry()
    me.vertices.add(res * res)
    me.vertices.foreach_set("co", np.stack([X, Y, h], -1).astype(np.float32).ravel())
    q = np.arange(res * res).reshape(res, res)
    quads = np.stack([q[:-1, :-1], q[:-1, 1:], q[1:, 1:], q[1:, :-1]], -1).reshape(-1, 4)
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.ravel().astype(np.int32))
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
    me.update()
    me.validate()
    uv = me.uv_layers.new(name="UVMap")
    uvs = np.stack([(X + size / 2) / size, (Y + size / 2) / size], -1).reshape(-1, 2)
    uv.uv.foreach_set("vector", uvs[quads.ravel()].astype(np.float32).ravel())
    for an, val in (("ENV_Slope", slope / 90.0), ("ENV_Height", hn)):
        at = me.attributes.get(an) or me.attributes.new(an, "FLOAT", "POINT")
        at.data.foreach_set("value", val.astype(np.float32).ravel())
    me.shade_smooth()
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
    res_d = {"ok": True, "object": ob.name, "size_m": size, "res": res, "cell_m": round(cell, 4),
             "tris": int(len(quads) * 2), "height_range_m": [round(float(h.min()), 3), round(float(h.max()), 3)],
             "slope_mean_deg": round(float(slope.mean()), 2), "rock_pct": round(float((slope > ROCK_DEG).mean()) * 100, 1)}
    if material:
        mat = _material("M_" + name)
        me.materials.clear()
        me.materials.append(mat)
        res_d["material"] = mat.name
    if export_heightmap:  # row 0 = -Y (south) edge; .raw = 16-bit little-endian (Unity), .png = 16-bit gray (UE)
        path = bpy.path.abspath(export_heightmap)
        if path.lower().endswith(".raw"):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            np.round(hn * 65535).astype("<u2").tofile(path)
            res_d["heightmap"] = path
        else:
            g = np.repeat(hn[..., None], 4, -1)
            g[..., 3] = 1
            res_d["heightmap"] = _save_png16(path, g, res, True)
        res_d["heightmap_z_scale_m"] = round(float(np.ptp(h)), 4)
    if export_splat:  # R grass, G rock, B snow, weights sum to 1
        rock = np.clip((slope - ROCK_DEG + 2) / 4, 0, 1)
        snow = np.clip((hn - SNOW_H + 0.03) / 0.06, 0, 1) * np.clip((40 - slope) / 4, 0, 1) * (1 - rock)
        grass = np.clip(1 - rock - snow, 0, 1)
        res_d["splat"] = _save_png16(bpy.path.abspath(export_splat), np.stack([grass, rock, snow, np.ones_like(grass)], -1), res, False)
    if res > 1025:
        res_d["warning"] = "res > 1025: split into tiles/chunks for engines and LODs"
    return res_d


if __name__ == "__main__":
    p = bx.parser(__doc__)
    for k, t, d in (("size", float, 200.0), ("res", int, 257), ("height", float, 30.0), ("scale", float, 80.0),
                    ("octaves", int, 6), ("seed", int, 0), ("erosion", int, 0), ("terrace", float, 0.0)):
        p.add_argument(f"--{k}", type=t, default=d)
    p.add_argument("--type", default="fbm", choices=("fbm", "ridged", "hills"))
    p.add_argument("--heightmap", default=None)
    p.add_argument("--flatten", type=float, nargs=3, default=None, metavar=("X", "Y", "RADIUS"))
    p.add_argument("--material", action="store_true")
    p.add_argument("--export-heightmap", default=None)
    p.add_argument("--export-splat", default=None)
    p.add_argument("--name", default="Terrain")
    p.add_argument("--save", default=None)
    bx.cli(run, p)
