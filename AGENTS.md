# Blender Agent Skills: agent instructions

This repo contains Agent Skills (`skills/<name>/SKILL.md`, agentskills.io format) for **Blender 5.2 LTS+**. Codex, OpenCode, Gemini CLI, Copilot and Cursor read them from `.agents/skills`; Claude Code reads them from `.claude/skills` (see `install/`).

## Using the skills
- Start any Blender task with `skills/blender-core/SKILL.md`. It routes to the specialized skill and defines how to run code: live through the blender-mcp `execute_blender_code`, or headless with `python skills/blender-core/scripts/run_in_blender.py <script.py> -- <args>`.
- Run scripts; don't read them. Every `skills/*/scripts/*.py` documents its flags in its docstring and prints one compact JSON result.
- Load a skill's `references/*.md` only when the SKILL.md points you there.
- Always finish geometry work with `skills/blender-asset-qa` (numbers + a visual check).

| Skill | Use for |
|---|---|
| blender-core | execution, 5.x API rules, routing (start here) |
| blender-scene-setup | units, naming, collections, linking, asset libraries |
| blender-hardsurface-modeling | bevels, booleans, weighted normals, props |
| blender-sculpting | organic forms, multires, procedural sculpt ops |
| blender-retopology-uv | retopo, UVs, texel density |
| blender-pbr-materials | Principled BSDF, texture sets, color spaces |
| blender-texture-baking | normal/AO/curvature/ID bakes, ORM |
| blender-geometry-nodes | procedural modeling, JSON node-tree builder |
| blender-character-rigging | Rigify, skinning, game skeletons |
| blender-facial-shapekeys | ARKit 52, visemes, correctives |
| blender-animation | actions/slots, NLA, mocap, bake, root motion |
| blender-game-optimization | budgets, LODs, draw calls |
| blender-export-pipelines | Roblox, Unity, Unreal, Godot, web, USD |
| blender-rendering | Cycles/EEVEE, color management, batch |
| blender-lighting-lookdev | lights, HDRI, cameras, turntables |
| blender-simulation | rigid body, cloth (classic + 5.2 nodes), fluids |
| blender-addon-development | extensions, operators, UI |
| blender-pipeline-automation | headless batch, conversion, CI |
| blender-asset-qa | review gate: z-fighting, floating parts, normals, UVs, weights |
| blender-workflow-recipes | end-to-end playbooks |

## Working on this repo
- Shared helper: edit `shared/_bpyx.py` only, then run `python tools/sync_shared.py`.
- Validate: `python tools/validate_skills.py` (spec, token budgets, links, script contract).
- Test: `python tools/run_tests.py [filter]` (needs Blender 5.2; set `BLENDER_EXE` if it isn't found). Set `BAS_SKIP_GPU=1` on machines without a GPU.
- Keep each SKILL.md ≤ ~2.5k tokens and each description ≤ 400 chars. Verify every API claim against a running Blender 5.2 before writing it.
