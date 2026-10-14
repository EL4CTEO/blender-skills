import bpy
import fixtures as fx
from run_all import TMP, skill_module


def _img(name, color, colorspace="sRGB"):
    im = bpy.data.images.new(name, 8, 8)
    im.pixels.foreach_set(list(color) * 64)
    im.filepath_raw = str(TMP / "tex" / f"{name}.png")
    im.file_format = "PNG"
    (TMP / "tex").mkdir(exist_ok=True)
    im.save()
    bpy.data.images.remove(im)


def test_texture_set_autowire_orm_dx_normal():
    _img("T_Crate_BC", (0.5, 0.3, 0.2, 1))
    _img("T_Crate_ORM", (1, 0.6, 0, 1))
    _img("T_Crate_nor_dx", (0.5, 0.5, 1, 1))
    _img("T_Crate_Height", (0.5, 0.5, 0.5, 1))
    fx.cube("SM_Crate")
    m = skill_module("blender-pbr-materials", "build_pbr_material")
    r = m.run(name="M_Crate", textures=str(TMP / "tex"), objects=["SM_Crate"])
    assert set(r["maps"]) >= {"basecolor", "orm", "normal", "height", "normal_flipped_from_dx"}, r
    mat = bpy.data.materials["M_Crate"]
    imgs = {n.label: n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"}
    assert imgs["basecolor"].colorspace_settings.name == "sRGB"
    assert imgs["orm"].colorspace_settings.name == "Non-Color"
    assert any(n.type == "GROUP" and n.node_tree.name == "glTF Material Output" for n in mat.node_tree.nodes)
    assert bpy.data.objects["SM_Crate"].active_material == mat


def test_presets_and_srgb_color_override():
    m = skill_module("blender-pbr-materials", "build_pbr_material")
    fx.cube("Ring")
    r = m.run(name="M_Gold", preset="gold", objects=["Ring"])
    bsdf = next(n for n in bpy.data.materials["M_Gold"].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert bsdf.inputs["Metallic"].default_value == 1 and r["assigned"] == ["Ring"]
    r = m.run(name="M_Red", preset="plastic", color=(1, 0, 0))
    bsdf = next(n for n in bpy.data.materials["M_Red"].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert abs(bsdf.inputs["Base Color"].default_value[0] - 1) < 1e-6
