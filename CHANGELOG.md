# Changelog

## [1.2.0] - 2026-10-30
- New skills: `blender-texturing` (wear/grime/dust, decals), `blender-stylized-npr` (toon shading, outlines), `blender-hair-grooming` (hair, fur, hair cards), `blender-environment-kits` (terrain, scatter, modular kits), `blender-clothing` (garments, no clipping), `blender-video-editing` (VSE edits, camera tracking).
- Animation: mocap retargeting with auto bone maps (`retarget.py`), loop pop/hitch checker (`loop_check.py`).
- Asset QA: catches faces on empty material slots, missing textures, and data maps set to sRGB.
- Sculpting: proportions, hard-surface and bake-source reference.
- Fix: re-running `surface_weather.py` no longer disconnects the weather layer.
- Validator flags script names that don't exist. Verified on Blender 5.2.3.

## [1.1.0] - 2026-10-16
- New `blender-time-of-day`: sky + sun measured from Blender's sky model, night with moon/stars, fog from visibility, moods (cyberpunk, horror, underwater, desert).
- New `blender-weather-fx`: looping rain/snow/dust/embers, wet surfaces, puddles with ripples, snow cover, lightning.
- With vs without skills comparison page, README banner and icon.

## [0.1.0] - 2026-10-14
- 20 Blender 5.2 skills for AI agents (Claude Code, Codex, OpenCode, Gemini CLI, Copilot, Cursor).
- 26 tested scripts (MCP + headless): QA, baking, UV/texel density, retopo, LODs, export presets, Rigify, skinning, animation bake, GN builder, render, lookdev, simulation, batch.
- Installers for every agent, Claude Code plugin/marketplace, validator, headless test suite, CI.
