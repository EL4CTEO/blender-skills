import json
import math
import struct

import bmesh
import bpy
import fixtures as fx
import numpy as np
from run_all import TMP, skill_module


def test_terrain_attributes_flatten_and_engine_maps():
    tr = skill_module("blender-environment-kits", "terrain")
    hm, sp = str(TMP / "T_Height.png"), str(TMP / "T_Splat.png")
    r = tr.run(size=100, res=129, height=20, type="ridged", erosion=10, flatten=(10, -10, 12), material=True,
               export_heightmap=hm, export_splat=sp)
    assert r["ok"] and r["tris"] == 128 * 128 * 2 and r["height_range_m"][1] > 15, r
    me = bpy.data.objects["Terrain"].data
    assert len(me.vertices) == 129 * 129 and {"ENV_Slope", "ENV_Height"} <= set(me.attributes.keys())
    co = np.array([v.co for v in me.vertices])
    inner = np.hypot(co[:, 0] - 10, co[:, 1] + 10) < 10
    assert np.ptp(co[inner, 2]) < 0.05  # the play area is flat
    for path, ctype in ((hm, 0), (sp, 6)):  # 16-bit grayscale heightmap, 16-bit RGBA splat
        w, h, depth, ct = struct.unpack(">IIBB", open(path, "rb").read(26)[16:26])
        assert (w, h, depth, ct) == (129, 129, 16, ctype), (path, w, h, depth, ct)
    img = bpy.data.images.load(sp)
    img.colorspace_settings.is_data = True  # data maps load as Non-Color, like engines read them
    a = np.array(img.pixels[:]).reshape(-1, 4)
    assert np.allclose(a[:, :3].sum(1), 1.0, atol=0.01)  # splat weights sum to 1
    h = bpy.data.images.load(hm)
    h.colorspace_settings.is_data = True
    hv = np.array(h.pixels[:]).reshape(129, 129, 4)[..., 0]
    zs = co[:, 2].reshape(129, 129)
    assert np.abs(hv - (zs - zs.min()) / np.ptp(zs)).max() < 1e-3  # raw 16-bit heights, no display transform
    raw = str(TMP / "T_Height.raw")
    tr.run(size=100, res=129, height=20, type="ridged", erosion=10, flatten=(10, -10, 12), export_heightmap=raw)
    rv = np.fromfile(raw, "<u2").reshape(129, 129) / 65535
    assert np.abs(rv - hv).max() < 2e-3  # .raw and .png carry the same heights


def _trees():
    col = bpy.data.collections.new("Trees")
    bpy.context.scene.collection.children.link(col)
    for i in range(2):
        me = bpy.data.meshes.new(f"Tree{i}")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=1, radius2=0, depth=4)
        bm.to_mesh(me)
        bm.free()
        col.objects.link(bpy.data.objects.new(f"Tree{i}", me))
    return col


def test_scatter_respects_slope_height_and_realize():
    skill_module("blender-environment-kits", "terrain").run(size=120, res=129, height=25, scale=50, erosion=10)
    _trees()
    sc = skill_module("blender-environment-kits", "scatter")
    r = sc.run(target="Terrain", collection="Trees", density=0.05, min_distance=3, max_slope=20, height_max=18, seed=1,
               export_points=str(TMP / "trees.json"))
    pts = json.load(open(r["points_file"]))["instances"]
    assert len(pts) == r["instances"] and all(len(p["rotation_quat_wxyz"]) == 4 for p in pts)
    assert r["instances"] > 30 and set(r["by_source"]) == {"Tree0", "Tree1"}, r
    assert r["slope_max_deg"] <= 20.05 and r["height_range"][1] <= 18.0, r
    assert bpy.context.view_layer.layer_collection.children["Trees"].exclude  # sources hidden at the origin
    r2 = sc.run(target="Terrain", collection="Trees", density=0.05, min_distance=3, max_slope=20, height_max=18,
                seed=1, realize=True)
    assert r2["tris_total"] > 128 * 128 * 2 + r["instances"] * 6, r2


def test_kit_check_flags_and_fixes():
    wall = fx.cube("SM_Wall_4m", size=1, location=(0.3, 0.1, 1.5))
    wall.scale = (4, 0.2, 3)  # unapplied scale, centered pivot, off-grid placement
    floor = fx.mesh_object("SM_Floor_4m", lambda bm: bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=2))
    holed = fx.mesh_object("Floor_Hole", lambda bm: bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=2))
    bm = bmesh.new()
    bm.from_mesh(holed.data)
    bm.faces.ensure_lookup_table()
    centre = min(bm.faces, key=lambda f: f.calc_center_median().length)
    bmesh.ops.delete(bm, geom=[centre], context="FACES_ONLY")
    bm.to_mesh(holed.data)
    bm.free()
    for o in (wall, floor, holed):
        fx.unwrap(o)
    kc = skill_module("blender-environment-kits", "kit_check")
    r = kc.run(objects=[wall.name, floor.name, holed.name], grid=0.5)
    p = r["pieces"]
    assert not r["pass"] and any("scale" in e for e in p["SM_Wall_4m"]["errors"]), p["SM_Wall_4m"]
    assert any("pivot" in e for e in p["SM_Floor_4m"]["errors"]), p["SM_Floor_4m"]
    assert any("open-edge" in e for e in p["Floor_Hole"]["errors"]) and any("prefix" in w for w in p["Floor_Hole"]["warnings"])
    r = kc.run(objects=[wall.name, floor.name], grid=0.5, fix=True)
    assert r["pass"], r["pieces"]
    bpy.context.view_layer.update()
    assert np.allclose(wall.scale, 1, atol=1e-5) and math.isclose(wall.dimensions.x, 4, abs_tol=1e-4), (
        tuple(wall.scale), tuple(wall.dimensions))
    assert np.allclose(wall.location, (-1.7, 0.0, 0.0), atol=1e-4)  # geometry stayed, origin moved to its min corner
