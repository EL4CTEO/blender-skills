import bpy


class MYTOOL_PT_main(bpy.types.Panel):
    bl_label = "My Tool"
    bl_idname = "MYTOOL_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "My Tool"  # sidebar (N) tab

    def draw(self, context):
        s = context.scene.my_tool
        col = self.layout.column(align=True)
        col.use_property_split = True
        col.prop(s, "distance")
        col.prop(s, "axis")
        self.layout.operator("my_tool.offset_selected", icon="ORIENTATION_GLOBAL")


class MYTOOL_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__  # extensions: package name, never a hard-coded string

    verbose: bpy.props.BoolProperty(name="Verbose reports", default=False)

    def draw(self, context):
        self.layout.prop(self, "verbose")


def menu_func(self, context):
    self.layout.operator("my_tool.offset_selected")
