#!/usr/bin/env python3
"""Lint skills against the Agent Skills spec + this repo's token budgets.

Checks: frontmatter (name/description rules, name == dir), SKILL.md <= 500 lines and
token budget, relative links resolve, scripts compile, Blender scripts expose run()
and a Usage docstring, _bpyx copies in sync.
Usage: python tools/validate_skills.py [--strict]   (--strict: warnings fail too)
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DESC_TARGET, DESC_MAX = 400, 1024
TOK_WARN, TOK_MAX, LINES_MAX = 3000, 5000, 500
LINK_RE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def tokens(text):
    return len(text) // 4  # rough, model-agnostic


def frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    fm, body = {}, text[end + 4:].lstrip("\n")
    key = None
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key, val = m.group(1), m.group(2).strip()
            fm[key] = val.strip("\"'") if val not in (">", "|", ">-", "|-") else ""
        elif key and line.startswith(" ") and fm.get(key) is not None and key != "metadata":
            fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm, body


def check_skill(d, errs, warns):
    rel = d.relative_to(ROOT)
    md = d / "SKILL.md"
    if not md.exists():
        errs.append(f"{rel}: missing SKILL.md")
        return
    text = md.read_text("utf-8")
    fm, body = frontmatter(text)
    if fm is None:
        errs.append(f"{rel}: no YAML frontmatter")
        return
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not NAME_RE.match(name) or len(name) > 64:
        errs.append(f"{rel}: invalid name {name!r}")
    if name != d.name:
        errs.append(f"{rel}: name {name!r} != dir {d.name!r}")
    raw = next((ln for ln in text.splitlines() if ln.startswith("description:")), "")
    if ": " in raw[len("description: "):] or " #" in raw:
        errs.append(f"{rel}: description has ': ' or ' #' (breaks YAML plain scalars; quote it)")
    if not 1 <= len(desc) <= DESC_MAX:
        errs.append(f"{rel}: description length {len(desc)} (1-{DESC_MAX})")
    elif len(desc) > DESC_TARGET:
        warns.append(f"{rel}: description {len(desc)} chars > target {DESC_TARGET}")
    n_lines, n_tok = body.count("\n") + 1, tokens(body)
    if n_lines > LINES_MAX:
        errs.append(f"{rel}: SKILL.md body {n_lines} lines > {LINES_MAX}")
    if n_tok > TOK_MAX:
        errs.append(f"{rel}: SKILL.md ~{n_tok} tokens > {TOK_MAX}")
    elif n_tok > TOK_WARN:
        warns.append(f"{rel}: SKILL.md ~{n_tok} tokens > {TOK_WARN}")
    for f in [md, *d.glob("references/*.md")]:
        for link in LINK_RE.findall(f.read_text("utf-8")):
            if "://" in link or link.startswith("mailto:"):
                continue
            if not (f.parent / link).resolve().exists():
                errs.append(f"{f.relative_to(ROOT)}: broken link {link}")
    for py in d.glob("scripts/*.py"):
        src = py.read_text("utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            errs.append(f"{py.relative_to(ROOT)}: syntax error {e}")
            continue
        if py.name == "_bpyx.py":
            continue
        doc = ast.get_docstring(tree) or ""
        if "Usage" not in doc:
            errs.append(f"{py.relative_to(ROOT)}: docstring lacks 'Usage'")
        imports_bpy = any(isinstance(n, ast.Import) and any(a.name == "bpy" for a in n.names)
                          for n in tree.body)
        if imports_bpy and not any(
                isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
            errs.append(f"{py.relative_to(ROOT)}: Blender script without run()")
    return n_tok


def main():
    errs, warns, rows = [], [], []
    skills = sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir())
    for d in skills:
        rows.append((d.name, check_skill(d, errs, warns)))
    shared = (ROOT / "shared" / "_bpyx.py").read_bytes()
    for c in (ROOT / "skills").glob("*/scripts/_bpyx.py"):
        if c.read_bytes() != shared:
            errs.append(f"{c.relative_to(ROOT)}: out of sync (run tools/sync_shared.py)")
    total = sum(t or 0 for _, t in rows)
    print(f"{len(skills)} skills, SKILL.md bodies ~{total} tokens total")
    for n, t in rows:
        print(f"  {n:<32} ~{t} tok")
    for w in warns:
        print("WARN ", w)
    for e in errs:
        print("ERROR", e)
    fail = errs or ("--strict" in sys.argv and warns)
    print("FAIL" if fail else "OK")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
