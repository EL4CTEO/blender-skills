# Blender Agent Skills

Professional Blender workflows packaged as **Agent Skills** for AI coding agents: Claude Code, Codex, OpenCode, Gemini CLI, GitHub Copilot and Cursor.

There are 20 skills covering the full 3D pipeline (modeling, UVs, PBR, baking, rigging, animation, optimization, export, rendering, simulation and QA), built for **Blender 5.2 LTS+**. Every script is tested in a real Blender.

## Install

**Claude Code** (plugin):
```
/plugin marketplace add EL4CTEO/blender-skills
/plugin install blender-agent-skills@blender-agent-skills
```

**Any agent** (clone, then run the installer):
```bash
git clone https://github.com/EL4CTEO/blender-skills
./blender-skills/install/install.sh          # macOS / Linux
.\blender-skills\install\install.ps1         # Windows
```
The default installs into `~/.claude/skills` and `~/.agents/skills`. `.agents/skills` is read by Codex, OpenCode, Gemini CLI, Copilot and Cursor. Options: `--agent claude|codex|opencode|gemini|copilot|cursor|all`, `--project DIR` for a single project, `--uninstall`.

**Requirements:** Blender 5.2+. Optional: a Blender MCP server lets agents work in your open Blender. Without one, agents run Blender in the background.

## Skills

| Skill | What it does |
|---|---|
| `blender-core` | Start here: runs code, routes tasks, 5.x API rules |
| `blender-scene-setup` | Units, naming, collections, asset libraries |
| `blender-hardsurface-modeling` | Bevels, booleans, weighted normals |
| `blender-sculpting` | Organic sculpting workflow |
| `blender-retopology-uv` | Retopology, UVs, texel density |
| `blender-pbr-materials` | Correct PBR materials from textures |
| `blender-texture-baking` | Normal, AO and curvature maps, ORM |
| `blender-geometry-nodes` | Procedural modeling from simple JSON |
| `blender-character-rigging` | Rigify, skinning, game skeletons |
| `blender-facial-shapekeys` | ARKit 52 blendshapes, visemes |
| `blender-animation` | Actions, NLA, mocap, root motion |
| `blender-game-optimization` | Budgets, LODs, draw calls |
| `blender-export-pipelines` | Roblox, Unity, Unreal, Godot, web, USD |
| `blender-rendering` | Cycles and EEVEE, batch rendering |
| `blender-lighting-lookdev` | Studio lighting, HDRI, turntables |
| `blender-simulation` | Rigid bodies, cloth, fluids |
| `blender-addon-development` | Blender extensions |
| `blender-pipeline-automation` | Batch jobs and file conversion |
| `blender-asset-qa` | Catches z-fighting, floating parts, bad normals and weights |
| `blender-workflow-recipes` | Complete asset playbooks |

## Try it

> "Make a game-ready crate for Unreal with baked normals and LODs."
> "Rig this character with Rigify and export it to Unity with a walk cycle."
> "Check this model for z-fighting and floating parts, then export it for Roblox."

## Development

```bash
python tools/validate_skills.py   # spec + token budget checks
python tools/run_tests.py         # 43 headless Blender tests (BLENDER_EXE to override)
```

MIT License
