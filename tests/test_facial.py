import bpy
import fixtures as fx
from run_all import skill_module


def test_arkit_split_mirror_drivers_report():
    sk = skill_module("blender-facial-shapekeys", "shapekeys")
    head = fx.uv_sphere("Head", segs=32, rings=16)
    r = sk.run(mesh="Head", create="arkit")
    assert r["created"] == 52 and len(sk.ARKIT) == 52 == len(set(sk.ARKIT))
    # sculpt a symmetric "eyeBlink" (move all verts up) and split it
    kb = head.shape_key_add(name="eyeBlink", from_mix=False)
    for d in kb.data:
        d.co.z += 0.1
    r = sk.run(mesh="Head", split="eyeBlink")
    kbs = head.data.shape_keys.key_blocks
    left, basis = kbs["eyeBlinkLeft"], kbs["Basis"]
    i_pos = max(range(len(basis.data)), key=lambda i: basis.data[i].co.x)
    i_neg = min(range(len(basis.data)), key=lambda i: basis.data[i].co.x)
    assert abs(left.data[i_pos].co.z - basis.data[i_pos].co.z - 0.1) < 1e-5
    assert abs(left.data[i_neg].co.z - basis.data[i_neg].co.z) < 1e-5
    r = sk.run(mesh="Head", mirror="eyeBlinkLeft")
    assert r["mirrored"]["to"] == "eyeBlinkRight" and "FINISHED" in r["mirrored"]["op"]
    right = kbs["eyeBlinkRight"]
    assert abs(right.data[i_neg].co.z - basis.data[i_neg].co.z - 0.1) < 1e-3
    r = sk.run(mesh="Head", drivers="FaceCtrl")
    assert r["drivers"]["count"] == 53  # 52 ARKit + the symmetric source key
    ctrl = bpy.data.objects["FaceCtrl"]
    ctrl["jawOpen"] = 0.7
    bpy.context.view_layer.update()
    bpy.context.evaluated_depsgraph_get().update()
    r = sk.run(mesh="Head", report=True)
    assert "jawOpen" in r["unsculpted"] and "eyeBlinkLeft" in r["max_offset"] and r["arkit_missing"] == []
