import os
import shutil
import subprocess
import sys

import bpy
import fixtures as fx
from run_all import ROOT, TMP


def test_template_validates_builds_and_registers():
    src = ROOT / "skills/blender-addon-development/assets/addon_template"
    exe = bpy.app.binary_path
    r = subprocess.run([exe, "--factory-startup", "--command", "extension", "validate", str(src)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = TMP / "ext_build"
    out.mkdir(exist_ok=True)
    r = subprocess.run([exe, "--factory-startup", "--command", "extension", "build", "--source-dir", str(src),
                        "--output-dir", str(out)], capture_output=True, text=True)
    assert r.returncode == 0 and any(p.suffix == ".zip" for p in out.iterdir()), r.stdout + r.stderr
    # register as a package in-process (what Blender does for an installed extension)
    pkg = TMP / "pkgs" / "my_tool"
    shutil.rmtree(pkg, ignore_errors=True)
    shutil.copytree(src, pkg)
    sys.path.insert(0, str(pkg.parent))
    import my_tool
    my_tool.register()
    try:
        ob = fx.cube("C")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        with bpy.context.temp_override(selected_objects=[ob], object=ob, active_object=ob):
            assert bpy.ops.my_tool.offset_selected(distance=2.0, axis="X") == {"FINISHED"}
        assert ob.location.x == 2.0
        assert abs(bpy.context.scene.my_tool.distance - 0.1) < 1e-6
    finally:
        my_tool.unregister()
    assert os.path.isdir(pkg)
