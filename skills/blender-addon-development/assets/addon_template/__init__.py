"""My Tool - Blender extension template (4.2+ extension format, verified on 5.2)."""
import bpy

from . import operators, ui

classes = (
    operators.MYTOOL_PG_settings,
    operators.MYTOOL_OT_offset_selected,
    ui.MYTOOL_PT_main,
    ui.MYTOOL_AP_preferences,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.my_tool = bpy.props.PointerProperty(type=operators.MYTOOL_PG_settings)
    bpy.types.VIEW3D_MT_object.append(ui.menu_func)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(ui.menu_func)
    del bpy.types.Scene.my_tool
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
