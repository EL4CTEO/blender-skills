"""In-Blender test runner. Discovers tests/test_*.py, runs each test_* on a fresh empty scene.

Usage: blender -b --factory-startup --python-exit-code 1 -P tests/run_all.py -- [name-filter]
       (or: python tools/run_tests.py [name-filter])
"""
import importlib.util
import os
import pathlib
import sys
import tempfile
import time
import traceback

import bpy

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "shared"))


def skill_module(skill, script):
    """Import skills/<skill>/scripts/<script>.py fresh (tests call run() directly)."""
    path = ROOT / "skills" / skill / "scripts" / f"{script}.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(f"{skill}.{script}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


TMP = pathlib.Path(tempfile.mkdtemp(prefix="bas_tests_"))


class Skip(Exception):
    pass


def requires_gpu():
    """Skip when BAS_SKIP_GPU=1 (CI runners without GPU/EGL: EEVEE, Workbench renders)."""
    if os.environ.get("BAS_SKIP_GPU") == "1":
        raise Skip("needs GPU context")


def main():
    flt = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv and sys.argv[-1] != "--" else ""
    passed, failed, skipped = 0, [], 0
    for f in sorted(HERE.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            full = f"{f.stem}::{name}"
            if flt and flt not in full:
                continue
            fresh()
            t = time.time()
            try:
                getattr(mod, name)()
                passed += 1
                print(f"PASS {full} ({time.time() - t:.1f}s)")
            except Exception as e:
                if type(e).__name__ == "Skip":  # tests import run_all as a 2nd module: match by name
                    skipped += 1
                    print(f"SKIP {full} ({e})")
                    continue
                failed.append(full)
                print(f"FAIL {full}\n{traceback.format_exc(limit=4)}")
    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
