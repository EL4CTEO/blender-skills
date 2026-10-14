"""_bpyx - tiny shared helpers for blender-agent-skills scripts (Blender 5.2+).

Source of truth: shared/_bpyx.py. Copies in skills/*/scripts/ are synced by
tools/sync_shared.py - never edit a copy.

Every skill script follows one contract:
  run(**kwargs) -> dict          # call from MCP / Python (import the module)
  blender -b f.blend -P x.py -- --arg v   # CLI: prints one line "@@JSON@@{...}"
"""
import argparse
import json
import sys

import bpy

MARK = "@@JSON@@"


def argv():
    """Arguments after '--' (Blender ignores them)."""
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _default(o):
    if hasattr(o, "__len__") and not isinstance(o, str):
        try:
            return [round(v, 5) if isinstance(v, float) else v for v in o]
        except TypeError:
            pass
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


def emit(data):
    """Print compact JSON on one marked line (parsed by run_in_blender.py)."""
    print(MARK + json.dumps(data, separators=(",", ":"), default=_default), flush=True)
    return data


def parser(doc):
    """ArgumentParser whose help is the script docstring's first line."""
    return argparse.ArgumentParser(description=(doc or "").strip().splitlines()[0])


def cli(run, p):
    """CLI entry: parse args after '--', run, emit JSON. Exit 1 on failure."""
    args = p.parse_args(argv())
    try:
        result = run(**vars(args))
        save = getattr(args, "save", None)
        if save:
            bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(save))
            result["saved"] = save
        emit(result)
    except Exception as e:  # report, don't dump a traceback into agent context
        emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
        if bpy.app.background:
            sys.exit(1)


def add_common(p, save=True):
    """--objects / --save flags shared by most scripts."""
    p.add_argument("--objects", nargs="*", default=None,
                   help="object names (default: selected, else all meshes)")
    if save:
        p.add_argument("--save", default=None, help="save .blend to this path after run")
    return p


def objects(names=None, types=("MESH",)):
    """Resolve names -> objects. No names: selected of `types`, else all visible of `types`."""
    if names:
        missing = [n for n in names if n not in bpy.data.objects]
        if missing:
            raise KeyError(f"objects not found: {missing}")
        return [bpy.data.objects[n] for n in names]
    pool = [o for o in bpy.context.scene.objects if not types or o.type in types]
    sel = [o for o in pool if o.select_get()]
    return sel or [o for o in pool if o.visible_get()]


def object_mode():
    """Leave edit/sculpt/pose modes; most data API work needs OBJECT mode."""
    ob = bpy.context.view_layer.objects.active
    if ob and ob.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def select_only(objs, active=None):
    """Select exactly `objs` and make `active` (default first) active."""
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def node(tree, type_):
    """First node of `type_` (e.g. 'BSDF_PRINCIPLED'). Names are localized - never look up by name."""
    return next((n for n in tree.nodes if n.type == type_), None)


def enum_ids(owner, prop):
    """Valid identifiers of an enum property (works on types or instances)."""
    return [i.identifier for i in owner.bl_rna.properties[prop].enum_items]


def set_enum(owner, prop, value):
    """Assign an enum; on failure raise listing valid values (dynamic enums under-report)."""
    try:
        setattr(owner, prop, value)
    except TypeError as e:
        raise ValueError(f"{prop}={value!r} invalid: {e}") from None


def mesh_tris(ob, evaluated=True):
    """Triangle count (evaluated = with modifiers)."""
    if evaluated:
        eo = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = eo.to_mesh()
        try:
            me.calc_loop_triangles()
            return len(me.loop_triangles)
        finally:
            eo.to_mesh_clear()
    me = ob.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def r(v, n=4):
    """Round a float or a vector for compact JSON."""
    if isinstance(v, float):
        return round(v, n)
    return [round(x, n) for x in v]
