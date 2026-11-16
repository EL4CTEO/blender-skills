# Workflow catalog

Load `blender-core` first, then only the workflows needed for the current stage. All original workflows are retained under their existing names. Resolve names against the installed skill catalog; do not assume internal directory IDs.

| Command | Skill | Use for |
| --- | --- | --- |
| `inspect` | `blender-core` | Runtime and code execution |
| `scene` | `blender-scene-setup` | Units, naming and collections |
| `model` | `blender-hardsurface-modeling` | Hard-surface geometry |
| `sculpt` | `blender-sculpting` | Organic forms and sculpting |
| `uv` | `blender-retopology-uv` | Retopology, UV and texel density |
| `material` | `blender-pbr-materials` | PBR materials and color spaces |
| `texture` | `blender-texturing` | Texture layers and surface details |
| `bake` | `blender-texture-baking` | High-to-low map baking |
| `nodes` | `blender-geometry-nodes` | Procedural node geometry |
| `rig` | `blender-character-rigging` | Rigify, skeletons and weights |
| `face` | `blender-facial-shapekeys` | Facial expressions and shape keys |
| `animate` | `blender-animation` | Animation, mocap and loops |
| `clothes` | `blender-clothing` | Garments and deformation |
| `hair` | `blender-hair-grooming` | Hair, fur and game cards |
| `optimize` | `blender-game-optimization` | Budgets and LODs |
| `export` | `blender-export-pipelines` | Game, web and AR delivery |
| `render` | `blender-rendering` | Rendering and compositing |
| `lookdev` | `blender-lighting-lookdev` | Lights, camera and turntables |
| `toon` | `blender-stylized-npr` | Stylized and toon looks |
| `environment` | `blender-environment-kits` | Environments and modular sets |
| `video` | `blender-video-editing` | Video editing and camera tracking |
| `simulate` | `blender-simulation` | Cloth, bodies and fluids |
| `mood` | `blender-time-of-day` | Time of day and atmosphere |
| `weather` | `blender-weather-fx` | Rain, snow and weather |
| `addon` | `blender-addon-development` | Blender add-ons and extensions |
| `batch` | `blender-pipeline-automation` | Batch processing and conversion |
| `qa` | `blender-asset-qa` | Asset checks and visual review |
| `recipe` | `blender-workflow-recipes` | Complete production recipes |

## Automatic examples

| Request | Main route |
| --- | --- |
| Game-ready crate for Unreal | Modeling, UV, materials, optimization, QA, export |
| Rig a character and retarget mocap | Rigging, animation, QA |
| Blender product turntable | Recipes, materials, lookdev, QA, rendering |
| Rainy Blender street at night | Mood, weather, rendering as requested |
| Blender campus arrival gate | Environment, hard surface, QA |
| Animate a CSS button | Keep web motion workflow |
| Edit a photo | Keep image editor workflow |

## Trigger behavior

The host selects the skill by its name and description. The local matcher is a transparent suggestion tool: it cannot understand every paraphrase, negation or prior scene context. Use semantic judgment, and never treat a match as authorization to mutate a scene. Explicit commands select a workflow. `plan` and `inspect` remain read-only.

## Source

Original 28 workflows: MIT-licensed EL4CTEO/blender-skills, accessed through the Garir-Mansour fork at revision `b1b21dfb73bc40b874ebf2aa12645931bfed3523`. Retain the root LICENSE and original author metadata.
