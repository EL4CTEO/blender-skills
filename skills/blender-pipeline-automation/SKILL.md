---
name: blender-pipeline-automation
description: Automate Blender 5.2 at scale - headless CLI flags, batch convert/inventory/run-any-skill-script over folders of .blend/.fbx/.glb/.obj/.usd, sharding, bpy pip module, library linking, path management, render-farm and CI patterns. Use for batch jobs, format conversion, library maintenance and pipeline tooling.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.1.0"
---

# Pipeline Automation

The execution model is in `blender-core` (`run_in_blender.py` finds Blender and prints only the JSON results).

## Batch one-liners
```
blender -b -P scripts/batch_process.py -- --in "assets/**/*.fbx" --op convert --to glb --out export/
blender -b -P scripts/batch_process.py -- --in library/ --op report                      # inventory JSON lines
blender -b -P scripts/batch_process.py -- --in "src/*.blend" --op script \
    --script ../blender-asset-qa/scripts/qa_check.py --kwargs '{"profile":"game"}'       # QA a whole library
blender -b -P scripts/batch_process.py -- --in src/ --op script --script ../blender-game-optimization/scripts/make_lods.py \
    --kwargs '{"rename":true}' --save-to processed/                                      # LODs for every file
```
Each file is streamed as one JSON line with `ok`, timing and results. Failures don't stop the batch, and the summary lists them. **Parallel**: start N processes with `--shard 0/N` … `--shard N-1/N` (Blender uses one core for Python, so processes scale with CPU/GPU count).

## Headless CLI essentials
| Flag | Meaning |
|---|---|
| `-b` | background, no UI. Put it **first** |
| `file.blend` | open before running scripts. Order matters: args run left to right |
| `-P script.py` / `--python-expr "..."` | run Python |
| `--python-exit-code 1` | non-zero exit if the script raises (CI) |
| `--factory-startup` | ignore user prefs/add-ons (reproducible). Bundled add-ons still load |
| `--addons rigify,io_scene_fbx` | enable specific add-ons |
| `-E CYCLES -o //out/#### -F PNG -s 1 -e 10 -a` / `-f 5` | render (`blender-rendering`) |
| `--command extension build/validate/install-file` | extension tooling (`blender-addon-development`) |
| `-- --my args` | everything after `--` goes to the script (`sys.argv[sys.argv.index("--")+1:]`) |
| `--log "*"`, `--debug-python` | debugging. 5.0 changed the log format, so don't regex progress lines |
Environment variables: `BLENDER_USER_SCRIPTS`, `BLENDER_USER_EXTENSIONS`, `BLENDER_SYSTEM_PYTHON`. Use `OCIO` for custom color configs.

## bpy as a Python module
`pip install bpy==5.2.*` (Python 3.13, matching the Blender release) gives `import bpy` in plain Python, which is handy for pytest/CI/web services. It has no UI and no GPU module by default, and it's large (~300 MB). Version-lock it with the Blender you target. The `bpy` wheel and the CLI behave the same for data API work.

## Library patterns
- **Append/link**: `bpy.data.libraries.load(path, link=...)` (see `blender-core/references/bpy-patterns.md`). 5.2: `data_from.libraries` exposes nested library paths when loading.
- **Write a subset**: `bpy.data.libraries.write(path, {datablocks}, fake_user=True, path_remap="RELATIVE_ALL")` builds asset/library files from a session.
- **Find files**: `bpy.data.file_path_foreach(...)` (5.2 flags: `EXPAND_TOKENS` for UDIMs, `EXPAND_SEQUENCES`, `EXPAND_CACHES`), and `bpy.utils.blend_paths(absolute=True)` lists every external path.
- **Remap/relocate**: `bpy.ops.file.find_missing_files(directory=...)`, `make_paths_relative`, `pack_all`. Libraries: `lib.filepath = new; lib.reload()`.
- **Iterate every ID**: `bpy.data.all_ids` (5.2), and `bpy.data.orphans_purge(do_recursive=True)` for cleanup.

## Robustness rules
- One task per process where possible. Long Blender sessions leak (images, undo). `batch_process.py` reuses the process but resets with `read_factory_settings(use_empty=True)` / `open_mainfile`.
- Never write into the source folder by default. Use separate `--out`/`--save-to`, and write with `copy=True`.
- Make scripts idempotent: re-running replaces their own outputs (named prefixes, `exist_ok`).
- Log JSON, not prose: one object per file/job, so agents and CI can parse it cheaply.
- Pin the Blender version (5.2 LTS) for a project. Record `bpy.app.version_string` + hash (`bpy.app.build_hash`) in the outputs.
- Paths: `bpy.path.abspath("//x")` is relative to the **opened** .blend. In headless batches use absolute paths, or set them after `open_mainfile`.
- GPU in containers: Cycles CUDA/OptiX needs the NVIDIA container runtime. Otherwise use CPU. EEVEE needs a GPU/EGL even headless.

## CI recipe (GitHub Actions)
Download the Linux tarball (`https://download.blender.org/release/Blender5.2/blender-5.2.2-linux-x64.tar.xz`), cache it, then `blender -b --factory-startup --python-exit-code 1 -P tests/run_all.py`. This repo's `.github/workflows/ci.yml` is a working example.
