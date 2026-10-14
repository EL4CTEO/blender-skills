import os
import pathlib
import re

import bpy
from run_all import ROOT, fresh, skill_module

FENCE = re.compile(r"```python\n(.*?)```", re.S)


def _run_md_blocks(md):
    """Execute every ```python block of a reference doc on a fresh scene."""
    blocks = FENCE.findall(pathlib.Path(md).read_text("utf-8"))
    assert blocks, f"no python blocks in {md}"
    for i, code in enumerate(blocks):
        if "render.render(" in code and os.environ.get("BAS_SKIP_GPU") == "1":
            continue  # needs a GPU context (CI without GPU)
        fresh()
        try:
            exec(compile(code, f"{pathlib.Path(md).name}[{i}]", "exec"), {"__name__": "__snippet__"})
        except Exception as e:
            raise AssertionError(f"{md} block {i} failed: {e}\n{code}") from e


def test_bpy_patterns_snippets_run():
    _run_md_blocks(ROOT / "skills/blender-core/references/bpy-patterns.md")


def test_env_report():
    r = skill_module("blender-core", "env_report").run()
    assert r["ok"] and r["blender"].startswith(("5.", "6."))
    assert "CYCLES" in r["engines"] and "BLENDER_EEVEE" in r["engines"]


def test_snippet_docs_across_skills():
    """Any reference doc tagged '(runs standalone)' must execute cleanly."""
    for md in sorted((ROOT / "skills").glob("*/references/*.md")):
        if "bpy-patterns" in md.name:
            continue
        head = md.read_text("utf-8").splitlines()[0]
        if "runs standalone" in head:
            _run_md_blocks(md)
    fresh()
    assert bpy.data.filepath == ""
