#!/usr/bin/env python3
"""Run a skill script in headless Blender and print only its JSON result.

Host-side (system Python 3.9+, no bpy). Finds Blender automatically:
$BLENDER_EXE > PATH > standard install dirs (newest version wins).

Usage:
  python run_in_blender.py [--blend FILE] [--user-prefs] SCRIPT.py [-- script args]
  python run_in_blender.py --expr "import bpy; print(bpy.app.version_string)"
  python run_in_blender.py --which          # print the Blender path it would use
Exit code: 0 ok, 1 script error, 2 Blender not found.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

MARK = "@@JSON@@"


def _ver(path):
    m = re.search(r"(\d+)\.(\d+)", path)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_blender():
    env = os.environ.get("BLENDER_EXE")
    if env and os.path.isfile(env):
        return env
    hit = shutil.which("blender")
    if hit:
        return hit
    pats = {
        "win32": [r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
                  os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender *\blender.exe"),
                  r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"],
        "darwin": ["/Applications/Blender*.app/Contents/MacOS/Blender",
                   os.path.expanduser("~/Applications/Blender*.app/Contents/MacOS/Blender")],
    }.get(sys.platform, ["/usr/bin/blender", "/opt/blender*/blender", "/snap/bin/blender",
                         os.path.expanduser("~/blender*/blender")])
    found = [p for pat in pats for p in glob.glob(pat) if os.path.isfile(p)]
    return max(found, key=_ver) if found else None


def main():
    a = sys.argv[1:]
    rest = []
    if "--" in a:
        i = a.index("--")
        a, rest = a[:i], a[i + 1:]
    exe = find_blender()
    if not exe:
        print(json.dumps({"ok": False, "error": "Blender not found; set BLENDER_EXE"}))
        return 2
    if "--which" in a:
        print(exe)
        return 0
    cmd = [exe, "-b"]
    if "--blend" in a:
        cmd.append(a[a.index("--blend") + 1])
    if "--user-prefs" not in a:
        cmd.append("--factory-startup")
    cmd += ["--python-exit-code", "1"]
    if "--expr" in a:
        cmd += ["--python-expr", a[a.index("--expr") + 1]]
    else:
        scripts = [x for x in a if x.endswith(".py")]
        if not scripts:
            print(__doc__)
            return 1
        cmd += ["-P", scripts[0]]
    cmd += ["--"] + rest
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = [ln[len(MARK):] for ln in p.stdout.splitlines() if ln.startswith(MARK)]
    if out:
        print("\n".join(out))
    elif "--expr" in a:
        # free-form expression: show stdout minus Blender banner noise
        noise = ("Blender ", "Read prefs", "Read blend", "Blender quit", "Color management")
        print("\n".join(ln for ln in p.stdout.splitlines() if ln and not ln.startswith(noise)))
    if p.returncode != 0 and not out:
        tail = (p.stderr or p.stdout).strip().splitlines()[-15:]
        print(json.dumps({"ok": False, "returncode": p.returncode, "log_tail": tail}))
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
