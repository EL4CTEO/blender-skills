"""Build a correct metal/rough PBR material from texture files or a measured preset.

Texture mode: give --textures dir (or files); maps are detected by name suffix
(basecolor/albedo/diffuse/_bc/_col, normal/_n/nor_gl/nor_dx, rough, metal, ao/occlusion,
orm/arm (R=AO G=Rough B=Metal), height/disp, emissive/emission, opacity/alpha).
Color spaces are set (color -> sRGB, data -> Non-Color); DirectX normals get G flipped;
AO is wired into a "glTF Material Output" group so glTF exports it.
Preset mode: --preset gold|silver|copper|iron|aluminum|chrome|titanium|brass|plastic|rubber|
wood|concrete|glass|water|skin|fabric|paint|ceramic [--color R G B (sRGB 0-1)].
Usage:
  blender -b f.blend -P build_pbr_material.py -- --name M_Crate --textures //tex/crate [--objects A B]
      [--tile 1] [--alpha clip|blend] [--displacement bump|both] [--save out.blend]
  blender -b f.blend -P build_pbr_material.py -- --name M_Gold --preset gold --objects Ring
  MCP: import build_pbr_material as b; print(b.run(name="M_Crate", textures="C:/tex/crate", objects=["SM_Crate"]))
"""
import os
import re
import sys

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

# filename token -> map (Poly Haven, ambientCG, Substance, Quixel, UE-style suffixes)
TOKENS = {
    "orm": "orm", "arm": "orm",
    "normaldx": "normal_dx", "nordx": "normal_dx", "ndx": "normal_dx",
    "normal": "normal", "normalgl": "normal", "norgl": "normal", "nor": "normal", "nrm": "normal",
    "n": "normal", "normalopengl": "normal", "normaldirectx": "normal_dx",
    "basecolor": "basecolor", "basecolour": "basecolor", "albedo": "basecolor", "diffuse": "basecolor",
    "diff": "basecolor", "col": "basecolor", "color": "basecolor", "colour": "basecolor",
    "bc": "basecolor", "d": "basecolor", "a": "basecolor",
    "roughness": "roughness", "rough": "roughness", "rgh": "roughness", "r": "roughness",
    "metallic": "metallic", "metalness": "metallic", "metal": "metallic", "mtl": "metallic", "m": "metallic",
    "ao": "ao", "occlusion": "ao", "ambientocclusion": "ao", "occ": "ao",
    "height": "height", "displacement": "height", "disp": "height", "bump": "height", "h": "height",
    "emissive": "emission", "emission": "emission", "emit": "emission", "glow": "emission", "e": "emission",
    "opacity": "opacity", "alpha": "opacity", "mask": "opacity", "transparency": "opacity",
}
IMG_EXT = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr", ".webp", ".bmp")

# linear base color (F0 for metals) / roughness / metallic / extras  (Unreal/physicallybased.info data)
PRESETS = {
    "gold": ((1.0, 0.766, 0.336), 0.25, 1), "silver": ((0.972, 0.960, 0.915), 0.2, 1),
    "copper": ((0.955, 0.638, 0.538), 0.3, 1), "iron": ((0.560, 0.570, 0.580), 0.45, 1),
    "aluminum": ((0.913, 0.922, 0.924), 0.35, 1), "chrome": ((0.550, 0.556, 0.554), 0.08, 1),
    "titanium": ((0.542, 0.497, 0.449), 0.35, 1), "brass": ((0.910, 0.778, 0.423), 0.3, 1),
    "plastic": ((0.214, 0.214, 0.214), 0.4, 0), "rubber": ((0.023, 0.023, 0.023), 0.85, 0),
    "wood": ((0.287, 0.153, 0.074), 0.65, 0), "concrete": ((0.262, 0.258, 0.246), 0.9, 0),
    "glass": ((1.0, 1.0, 1.0), 0.0, 0), "water": ((1.0, 1.0, 1.0), 0.0, 0),
    "skin": ((0.651, 0.426, 0.338), 0.5, 0), "fabric": ((0.3, 0.3, 0.3), 0.9, 0),
    "paint": ((0.5, 0.05, 0.05), 0.35, 0), "ceramic": ((0.8, 0.8, 0.78), 0.15, 0),
}


def _srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def classify(path):
    """Map type from filename tokens, scanning from the end (suffixes win)."""
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    toks = [t for t in re.split(r"[_\-. ]+", stem) if t]
    for i in range(len(toks) - 1, -1, -1):
        for cand in ((toks[i - 1] + toks[i]) if i else None, toks[i]):
            if cand and cand in TOKENS and not (cand == toks[i] and i == 0 and len(toks) > 1 and len(cand) == 1):
                return TOKENS[cand]
    return None


def _find_textures(textures):
    files = []
    for t in textures if isinstance(textures, (list, tuple)) else [textures]:
        t = bpy.path.abspath(t)
        if os.path.isdir(t):
            files += [os.path.join(t, f) for f in sorted(os.listdir(t)) if f.lower().endswith(IMG_EXT)]
        elif os.path.isfile(t):
            files.append(t)
    maps = {}
    for f in files:
        k = classify(f)
        if k and k not in maps:
            maps[k] = f
    if "normal_dx" in maps and "normal" not in maps:
        maps["normal"] = maps["normal_dx"]
        maps["_dx"] = True
    return maps


def _gltf_output_group():
    name = "glTF Material Output"
    g = bpy.data.node_groups.get(name)
    if g is None:
        g = bpy.data.node_groups.new(name, "ShaderNodeTree")
        g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        g.nodes.new("NodeGroupOutput")
        g.nodes.new("NodeGroupInput").location = (-200, 0)
    return g


def run(name="M_Material", textures=None, preset=None, color=None, objects=None, tile=1.0,
        alpha=None, displacement="bump", dx_normal=False, **_):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    found = {}
    if preset:
        base, rough, metal = PRESETS[preset]
        if color:
            base = tuple(_srgb_to_lin(c) for c in color)
        bsdf.inputs["Base Color"].default_value = (*base, 1)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        if preset in ("glass", "water"):
            bsdf.inputs["Transmission Weight"].default_value = 1.0
            bsdf.inputs["IOR"].default_value = 1.33 if preset == "water" else 1.5
        if preset == "skin":
            bsdf.inputs["Subsurface Weight"].default_value = 1.0
            bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
            bsdf.inputs["Subsurface Scale"].default_value = 0.01
        if preset == "fabric":
            bsdf.inputs["Sheen Weight"].default_value = 0.5
        if preset == "paint":
            bsdf.inputs["Coat Weight"].default_value = 1.0
            bsdf.inputs["Coat Roughness"].default_value = 0.05
        found["preset"] = preset
    if textures:
        maps = _find_textures(textures)
        dx = dx_normal or maps.pop("_dx", False)
        maps.pop("normal_dx", None)
        coord = nt.nodes.new("ShaderNodeTexCoord")
        coord.location = (-1300, 0)
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.location = (-1100, 0)
        mapping.inputs["Scale"].default_value = (tile, tile, tile)
        nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])

        def tex(key, y, color_space):
            img = bpy.data.images.load(maps[key], check_existing=True)
            img.colorspace_settings.name = color_space
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image, n.location, n.label = img, (-700, y), key
            nt.links.new(mapping.outputs["Vector"], n.inputs["Vector"])
            found[key] = os.path.basename(maps[key])
            return n
        ao_out = None
        if "basecolor" in maps:
            n = tex("basecolor", 400, "sRGB")
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
            if alpha and "opacity" not in maps:
                nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
        if "orm" in maps:
            n = tex("orm", 100, "Non-Color")
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            sep.location = (-400, 100)
            nt.links.new(n.outputs["Color"], sep.inputs["Color"])
            nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
            nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
            ao_out = sep.outputs["Red"]
        else:
            if "roughness" in maps:
                nt.links.new(tex("roughness", 100, "Non-Color").outputs["Color"], bsdf.inputs["Roughness"])
            if "metallic" in maps:
                nt.links.new(tex("metallic", -100, "Non-Color").outputs["Color"], bsdf.inputs["Metallic"])
            if "ao" in maps:
                ao_out = tex("ao", 250, "Non-Color").outputs["Color"]
        if ao_out is not None:  # Principled has no AO input: glTF group carries it to export
            g = nt.nodes.new("ShaderNodeGroup")
            g.node_tree, g.location = _gltf_output_group(), (400, -250)
            nt.links.new(ao_out, g.inputs["Occlusion"])
        if "normal" in maps:
            n = tex("normal", -350, "Non-Color")
            nm = nt.nodes.new("ShaderNodeNormalMap")
            nm.location = (-200, -350)
            src = n.outputs["Color"]
            if dx:  # DirectX (Y-) -> OpenGL (Y+): invert green
                sep = nt.nodes.new("ShaderNodeSeparateColor")
                inv = nt.nodes.new("ShaderNodeMath")
                inv.operation, inv.inputs[0].default_value = "SUBTRACT", 1.0
                comb = nt.nodes.new("ShaderNodeCombineColor")
                sep.location, inv.location, comb.location = (-450, -500), (-450, -650), (-300, -500)
                nt.links.new(src, sep.inputs["Color"])
                nt.links.new(sep.outputs["Green"], inv.inputs[1])
                nt.links.new(sep.outputs["Red"], comb.inputs["Red"])
                nt.links.new(inv.outputs["Value"], comb.inputs["Green"])
                nt.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
                src = comb.outputs["Color"]
                found["normal_flipped_from_dx"] = True
            nt.links.new(src, nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        if "emission" in maps:
            nt.links.new(tex("emission", -550, "sRGB").outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 1.0
        if "opacity" in maps:
            nt.links.new(tex("opacity", -750, "Non-Color").outputs["Color"], bsdf.inputs["Alpha"])
        if "height" in maps:
            h = tex("height", -950, "Non-Color")
            d = nt.nodes.new("ShaderNodeDisplacement")
            d.location = (200, -500)
            d.inputs["Scale"].default_value = 0.02
            d.inputs["Midlevel"].default_value = 0.5
            nt.links.new(h.outputs["Color"], d.inputs["Height"])
            nt.links.new(d.outputs["Displacement"], out.inputs["Displacement"])
            mat.displacement_method = "BOTH" if displacement == "both" else "BUMP"
        if not found:
            raise ValueError(f"no recognizable texture maps in {textures}")
    if alpha:
        mat.surface_render_method = "BLENDED" if alpha == "blend" else "DITHERED"
    assigned = []
    if objects:
        for ob in bx.objects(objects):
            if ob.data.materials:
                ob.data.materials[0] = mat
            else:
                ob.data.materials.append(mat)
            assigned.append(ob.name)
    return {"ok": True, "material": mat.name, "maps": found, "assigned": assigned}


if __name__ == "__main__":
    p = bx.add_common(bx.parser(__doc__))
    p.add_argument("--name", default="M_Material")
    p.add_argument("--textures", nargs="*", default=None)
    p.add_argument("--preset", choices=sorted(PRESETS), default=None)
    p.add_argument("--color", nargs=3, type=float, default=None, help="sRGB 0-1 override")
    p.add_argument("--tile", type=float, default=1.0)
    p.add_argument("--alpha", choices=["clip", "blend"], default=None)
    p.add_argument("--displacement", choices=["bump", "both"], default="bump")
    p.add_argument("--dx-normal", action="store_true")
    bx.cli(run, p)
