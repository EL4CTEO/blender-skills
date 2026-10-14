#!/usr/bin/env python3
"""Run the headless Blender test suite.

Usage: python tools/run_tests.py [name-filter]     (BLENDER_EXE overrides discovery)
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "blender-core" / "scripts"))
from run_in_blender import find_blender  # noqa: E402


def main():
    exe = find_blender()
    if not exe:
        print("Blender not found; set BLENDER_EXE")
        return 2
    cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "1",
           "-P", str(ROOT / "tests" / "run_all.py"), "--", *sys.argv[1:]]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout.splitlines()
    start = next((i for i, ln in enumerate(out) if ln.startswith(("PASS", "FAIL", "SKIP"))), len(out))
    keep = ("PASS", "FAIL", "SKIP", "Traceback", "  ", "AssertionError", "KeyError", "ValueError", "RuntimeError")
    lines = [ln for ln in out[start:] if ln.startswith(keep) or " passed, " in ln]
    print("\n".join(lines))
    if p.returncode and not lines:
        print(p.stderr[-3000:])
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
