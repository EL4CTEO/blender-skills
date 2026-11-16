"""Install all Blender skills and conditionally bind named agent files.

Usage: python tools/install_bundle.py --project /project --agent all
       python tools/install_bundle.py --project /project --agent all --apply
       python tools/install_bundle.py --user --agent claude --agent codex --apply
       python tools/install_bundle.py --project /project --bind .claude/agents/artist.md --apply

Default: read-only plan. Never deletes files, installs hooks, changes tools,
edits model selections or sends conversations to other agents.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "<!-- BLENDER-ROUTER:BEGIN -->"
END = "<!-- BLENDER-ROUTER:END -->"
BINDING = """## Blender workflow routing

For Blender/bpy/.blend work, 3D asset production, rigs, materials, rendered 3D
motion, environments or mesh export/QA, load the installed blender-router skill
first, then the specialist skills it selects. Preserve this agent's role,
creative direction, tools, permissions and delivery gates. Use Blender only
when the deliverable needs it; ordinary 2D/CSS/UI motion keeps its current route.
Manual entry: $blender-router <command> <brief>; in Claude Code use
/blender-router <command> <brief> or the installed /blender alias.
Do not report a route plan as executed work. Do not grant new authority to
other agents or share conversation content as part of this integration.
"""
COMMAND = """---
description: Route Blender work through the complete Blender skill collection
argument-hint: "<command> <brief>"
---

Load the installed blender-router SKILL.md and interpret the following as a
workflow command. Load blender-core and the selected specialists. Preserve
current permissions and agent identity. `help`, `plan` and `inspect` are read-only.
Never treat this command as permission to install, publish or overwrite files.

$ARGUMENTS
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def within(path, base):
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def roots(base, agents, user=False):
    mapping = {"claude": ".claude/skills", "codex": ".agents/skills",
               "opencode": ".config/opencode/skills" if user else ".opencode/skills",
               "gemini": ".gemini/skills", "copilot": ".copilot/skills" if user else ".github/skills",
               "cursor": ".cursor/skills"}
    chosen = list(mapping) if "all" in agents else agents
    result = []
    for agent in chosen:
        if agent not in mapping:
            raise ValueError("Unknown agent host: " + agent)
        target = base / mapping[agent]
        if target not in result:
            result.append(target)
    return result


def related_bindings(base):
    """Discover relevant roles from agent frontmatter; never inspect conversations."""
    pattern = re.compile(
        r"\bblender\b|\b3d\b|technical artist|animation\s*(?:&|and)\s*motion|"
        r"creative (?:agent|director|intelligence)|architect\s*(?:&|and)\s*orchestrator|"
        r"game director|gaming unit", re.I)
    result = []
    for path in sorted((Path(base) / ".claude/agents").glob("*.md")):
        if path.is_symlink() or not within(path, Path(base)):
            continue
        text = path.read_text("utf-8-sig")
        parts = text.split("---", 2)
        if len(parts) != 3 or parts[0].strip():
            continue
        description = re.search(r"(?ms)^description:\s*(.*?)(?=\n[^ \t\n]|\Z)", parts[1])
        if not description:
            continue
        value = description.group(1)
        if pattern.search(value) and not re.search(r"\b(?:higgsfield only|2d only|no 3d)\b", value, re.I):
            result.append(str(path.relative_to(base)))
    return result


def make_plan(base, agents, bindings=(), user=False, state_dir=None):
    base = Path(base).resolve()
    state = Path(state_dir).resolve() if state_dir else base / ".blender-router-install"
    if not within(state, base):
        raise ValueError("Install state must remain inside the installation root")
    manifest = state / "manifest.json"
    prior = json.loads(manifest.read_text("utf-8")) if manifest.exists() else {"files": {}}
    targets = roots(base, agents, user)
    entries = []
    conflicts = []
    seen = set()

    def add(path, data, kind):
        path = Path(path).absolute()
        if path in seen:
            return
        seen.add(path)
        if not within(path, base):
            raise ValueError("Target escapes installation root (including links): " + str(path))
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Target is not an ordinary file: " + str(path))
        old = path.read_bytes() if path.exists() else None
        if old == data:
            action = "unchanged"
        elif old is None:
            action = "create"
        elif kind == "binding":
            action = "append"
        elif prior["files"].get(str(path)) == digest(old):
            action = "update"
        else:
            conflicts.append(str(path))
            action = "conflict"
        entries.append({"path": path, "data": data, "old": old, "action": action, "kind": kind})

    skill_dirs = sorted(p.parent for p in (ROOT / "skills").glob("*/SKILL.md"))
    if not any(p.name == "blender-router" for p in skill_dirs):
        raise ValueError("Router missing from source bundle")
    for target in targets:
        for skill in skill_dirs:
            for source in sorted(skill.rglob("*")):
                if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
                    continue
                if source.is_symlink():
                    raise ValueError("Refusing source symlink: " + str(source))
                add(target / skill.name / source.relative_to(skill), source.read_bytes(), "skill")
            # Each independently copied skill retains the MIT notice.
            add(target / skill.name / "LICENSE", (ROOT / "LICENSE").read_bytes(), "license")
    if "all" in agents or "claude" in agents:
        add(base / ".claude/commands/blender.md", COMMAND.encode(), "command")
    for relative in bindings:
        path = base / relative
        if not within(path, base) or path.suffix.lower() != ".md" or not path.is_file():
            raise ValueError("Binding must name an existing Markdown file inside the installation root: " + str(relative))
        old = path.read_bytes()
        text = old.decode("utf-8-sig")
        newline = "\r\n" if b"\r\n" in old else "\n"
        block = (BEGIN + "\n" + BINDING + END + "\n").replace("\n", newline).encode("utf-8")
        if BEGIN in text or END in text:
            if old.count(BEGIN.encode()) != 1 or old.count(END.encode()) != 1 or block not in old:
                raise ValueError("Existing router binding was edited or is malformed: " + str(path))
            add(path, old, "binding")
        else:
            add(path, old + (newline * 2).encode() + block, "binding")
    return {"base": base, "state": state, "targets": targets, "entries": entries,
            "conflicts": conflicts, "skill_count": len(skill_dirs), "prior": prior}


def summary(plan, applied=False):
    changes = [e for e in plan["entries"] if e["action"] != "unchanged"]
    return {"status": "blocked" if plan["conflicts"] else ("installed" if applied else "planned"),
            "applied": applied, "skills": plan["skill_count"],
            "target_roots": [str(p) for p in plan["targets"]], "files_to_change": len(changes),
            "bindings": [str(e["path"]) for e in plan["entries"] if e["kind"] == "binding"],
            "conflicts": plan["conflicts"], "state": str(plan["state"])}


def apply_plan(plan):
    if plan["conflicts"]:
        raise ValueError("Existing unmanaged or locally modified files would be overwritten; no changes applied")
    changes = [e for e in plan["entries"] if e["action"] != "unchanged"]
    if not changes:
        return summary(plan, True)
    # Check the whole plan for stale content before touching any destination.
    for e in plan["entries"]:
        actual = e["path"].read_bytes() if e["path"].exists() else None
        if actual != e["old"]:
            raise ValueError("Input changed after plan: " + str(e["path"]))
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    state = plan["state"]
    backup = state / "backups" / run
    backup.mkdir(parents=True, exist_ok=False)
    report = summary(plan)
    report["authorization"] = "Explicit --apply; named skill targets and agent bindings only"
    report["changes"] = [{"path": str(e["path"]), "action": e["action"],
                           "before_sha256": digest(e["old"]) if e["old"] is not None else None,
                           "after_sha256": digest(e["data"])} for e in changes]
    (backup / "plan.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # If the project uses this governance location, record the review before edits.
    governance = plan["base"] / "99_SYSTEM/REPORTS"
    if governance.is_dir():
        (governance / ("BLENDER_ROUTER_APPROVAL_" + run + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
    for i, e in enumerate(changes):
        if e["old"] is not None:
            (backup / (str(i) + ".bak")).write_bytes(e["old"])
            report["changes"][i]["backup"] = str(backup / (str(i) + ".bak"))
    (backup / "plan.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    written = []
    try:
        for e in changes:
            path = e["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            current = path.read_bytes() if path.exists() else None
            if current != e["old"]:
                raise ValueError("Input changed during install: " + str(path))
            # Write through a same-directory temporary file, then atomic replace.
            temp = path.with_name(path.name + ".blender-router-" + run + ".tmp")
            with temp.open("xb") as stream:
                stream.write(e["data"])
            temp.replace(path)
            written.append(str(path))
            if path.read_bytes() != e["data"]:
                raise OSError("Verification failed: " + str(path))
        files = dict(plan["prior"]["files"])
        files.update({str(e["path"]): digest(e["data"]) for e in plan["entries"]})
        manifest = {"files": files, "last_run": run, "verified": True}
        temp_manifest = state / ("manifest-" + run + ".tmp")
        temp_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        temp_manifest.replace(state / "manifest.json")
    except Exception as exc:
        (backup / "failure.json").write_text(json.dumps({"error": str(exc), "written": written}, indent=2), encoding="utf-8")
        raise RuntimeError("Install incomplete; preserve files and consult receipt " + str(backup) + ": " + str(exc)) from exc
    result = summary(plan, True)
    result["receipt"] = str(backup / "plan.json")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project", type=Path)
    scope.add_argument("--user", action="store_true")
    parser.add_argument("--agent", action="append", choices=["all", "claude", "codex", "opencode", "gemini", "copilot", "cursor"])
    parser.add_argument("--bind", action="append", default=[], help="Exact agent Markdown path relative to project/home")
    parser.add_argument("--bind-related", action="store_true", help="Suggest/bind relevant roles from .claude/agents descriptions")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        base = Path.home() if args.user else args.project
        bindings = args.bind + (related_bindings(base) if args.bind_related else [])
        plan = make_plan(base, args.agent or ["claude", "codex"], bindings, args.user, args.state_dir)
        result = apply_plan(plan) if args.apply else summary(plan)
        print(json.dumps(result, indent=2))
        return 2 if plan["conflicts"] else 0
    except RuntimeError as exc:
        print(json.dumps({"status": "incomplete", "error": str(exc), "may_have_changes": True}))
        return 1
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "applied": False}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
