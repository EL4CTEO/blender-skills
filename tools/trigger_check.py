#!/usr/bin/env python3
"""Heuristic trigger check: do skill descriptions win for prompts they should own?

Scores each prompt against every description (token overlap, IDF weighted) and checks that the
expected skill is in the top 2. A cheap regression guard when editing descriptions; real agents
use richer matching.
Usage: python tools/trigger_check.py
"""
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = [
    ("rig my character with rigify and fix the weight painting", "blender-character-rigging"),
    ("bake a normal map from the high poly sculpt onto the low poly", "blender-texture-baking"),
    ("export this skeletal mesh to unreal engine", "blender-export-pipelines"),
    ("my model has z-fighting and floating parts, review it", "blender-asset-qa"),
    ("make LODs and reduce draw calls for mobile", "blender-game-optimization"),
    ("unwrap the uvs and set texel density to 512 px/m", "blender-retopology-uv"),
    ("set up a PBR material from these texture maps, metal roughness", "blender-pbr-materials"),
    ("scatter rocks on the terrain procedurally with geometry nodes", "blender-geometry-nodes"),
    ("create ARKit blendshapes for lip-sync visemes", "blender-facial-shapekeys"),
    ("bake the walk cycle with root motion and export clips", "blender-animation"),
    ("render a turntable with studio lighting and an HDRI", "blender-lighting-lookdev"),
    ("render the animation with cycles on the GPU and denoise", "blender-rendering"),
    ("cloth draping over a table and rigid body crates falling", "blender-simulation"),
    ("write a blender add-on with an operator and a panel", "blender-addon-development"),
    ("batch convert a folder of fbx files to glb headless", "blender-pipeline-automation"),
    ("bevel and boolean a hard-surface weapon with weighted normals", "blender-hardsurface-modeling"),
    ("sculpt a creature with multires and voxel remesh", "blender-sculpting"),
    ("organize collections, naming conventions and asset library", "blender-scene-setup"),
    ("make a complete game-ready character from an AI generated mesh", "blender-workflow-recipes"),
    ("run bpy code in blender headless via the cli", "blender-core"),
    ("roblox layered clothing cage and R15 export", "blender-export-pipelines"),
    ("golden hour sunset lighting with volumetric fog", "blender-time-of-day"),
    ("make it a moonlit night scene with stars", "blender-time-of-day"),
    ("rainy street with puddles, wet surfaces and lightning", "blender-weather-fx"),
    ("snow falling and snow cover on the roofs", "blender-weather-fx"),
]


def toks(s):
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2]


def main():
    descs = {}
    for md in sorted((ROOT / "skills").glob("*/SKILL.md")):
        m = re.search(r"^description: (.*)$", md.read_text("utf-8"), re.M)
        descs[md.parent.name] = set(toks(m.group(1)) + toks(md.parent.name))
    n = len(descs)
    idf = {}
    for d in descs.values():
        for t in d:
            idf[t] = idf.get(t, 0) + 1
    idf = {t: math.log(n / c) + 0.1 for t, c in idf.items()}
    fails = 0
    for prompt, want in CASES:
        q = set(toks(prompt))
        ranked = sorted(descs, key=lambda k: -sum(idf.get(t, 0) for t in q & descs[k]))
        ok = want in ranked[:2]
        fails += not ok
        print(f"{'ok ' if ok else 'MISS'} {want:<30} top: {ranked[0]}, {ranked[1]}  <- {prompt}")
    print(f"{len(CASES) - fails}/{len(CASES)} in top-2")
    return 1 if fails > len(CASES) // 10 else 0


if __name__ == "__main__":
    sys.exit(main())
