"""Suggest a bounded Blender workflow; never run Blender or write files.

Usage: python route.py --prompt "Render a Blender product turntable"
       python route.py --command web --prompt "a lightweight GLB"
       python route.py --command help
       python route.py --skills-root /installed/skills --prompt "rig my mesh"
"""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def catalog():
    return json.loads((ROOT / "references/routes.json").read_text("utf-8"))


def matches(pattern, text):
    return re.search(pattern, text, re.IGNORECASE) is not None


def installed_skills(root):
    found = {}
    for md in sorted(Path(root).glob("*/SKILL.md")):
        text = md.read_text("utf-8-sig")
        header = text.split("---", 2)
        if len(header) != 3 or header[0].strip():
            continue
        match = re.search(r"^name:\s*[\"']?([a-z0-9-]+)[\"']?\s*$", header[1], re.M)
        if match:
            name = match.group(1)
            if name in found:
                raise ValueError("Duplicate skill name: " + name)
            found[name] = str(md.resolve())
    return found


def run(prompt="", command="auto", skills_root=None):
    data = catalog()
    text = prompt.strip()
    invocation = re.match(r"^(?:/blender(?:-router)?|[@$]blender-router)\b\s*(.*)$", text, re.I)
    explicit = command not in ("auto", "plan") or invocation is not None
    if invocation:
        text = invocation.group(1)
        first, _, rest = text.partition(" ")
        first = first.lower()
        if first in data["commands"] or first in ("help", "auto", "plan"):
            command, text = first, rest
    if command == "help":
        return {"status": "help", "execution_performed": False, "read_only": True,
                "missing_dependencies": [],
                "commands": ["help", "auto", "plan", *data["commands"]]}
    if command not in data["commands"] and command not in ("auto", "plan"):
        raise ValueError("Unknown command: " + command)
    result = {"status": "routed", "command": command, "execution_performed": False,
              "mode": "plan" if command == "plan" else "suggestion", "reason": [], "stages": [],
              "read_only": True, "missing_dependencies": [],
              "requested_workflow_read_only": command in ("plan", "inspect")}
    if matches(data["exclude"], text):
        result.update(status="outside_scope", reason=["Request explicitly avoids Blender or names a non-3D use"])
        return result
    domain = explicit or matches(data["domain"], text)
    if not domain:
        result.update(status="outside_scope", reason=["No clear Blender or 3D-asset context; keep existing workflow"])
        return result
    selected = set(data["commands"].get(command, []))
    if command in ("auto", "plan"):
        for item in data["workflows"]:
            if matches(item["pattern"], text):
                selected.add(item["name"])
                result["reason"].append(item["name"])
        for rule in data.get("combinations", []):
            if matches(rule["pattern"], text):
                selected.update(rule["skills"])
        if len(selected - {"blender-core", "blender-asset-qa"}) >= 3:
            selected.add("blender-workflow-recipes")
    selected.add("blender-core")
    # Prerequisites are guidance stages, not permission to rebuild existing data.
    for name in list(selected):
        selected.update(data.get("prerequisites", {}).get(name, []))
    if selected == {"blender-core"}:
        result["reason"].append("Start with scene/runtime inspection; refine the brief before mutation")
    if any(name in data["qa_required"] for name in selected):
        selected.add("blender-asset-qa")
    available = installed_skills(skills_root or ROOT.parent)
    missing = []
    for name in data["order"]:
        if name in selected:
            path = available.get(name)
            result["stages"].append({"skill": name, "path": path, "available": bool(path)})
            if not path:
                missing.append(name)
    result["missing_dependencies"] = missing
    if missing:
        result["status"] = "missing_dependencies"
    result["read_only"] = True  # this helper never mutates Blender or files
    result["requested_workflow_read_only"] = command in ("plan", "inspect")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--command", default="auto")
    parser.add_argument("--skills-root", type=Path)
    args = parser.parse_args()
    try:
        result = run(**vars(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result["status"] == "missing_dependencies" else 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc), "execution_performed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
