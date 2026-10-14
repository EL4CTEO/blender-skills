import bpy
from bpy.props import EnumProperty, FloatProperty


class MYTOOL_PG_settings(bpy.types.PropertyGroup):
    distance: FloatProperty(name="Distance", default=0.1, min=0.0, soft_max=10.0, unit="LENGTH")
    axis: EnumProperty(name="Axis", items=(("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")), default="Z")


class MYTOOL_OT_offset_selected(bpy.types.Operator):
    """Move selected objects along an axis"""  # tooltip
    bl_idname = "my_tool.offset_selected"
    bl_label = "Offset Selected"
    bl_options = {"REGISTER", "UNDO"}  # UNDO: one undo step; REGISTER: redo panel

    distance: FloatProperty(name="Distance", default=0.1, unit="LENGTH")
    axis: EnumProperty(name="Axis", items=(("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")), default="Z")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(context.selected_objects)

    def invoke(self, context, event):
        s = context.scene.my_tool  # start from the panel settings
        self.distance, self.axis = s.distance, s.axis
        return self.execute(context)

    def execute(self, context):
        i = "XYZ".index(self.axis)
        for ob in context.selected_objects:
            ob.location[i] += self.distance
        self.report({"INFO"}, f"Moved {len(context.selected_objects)} objects")
        return {"FINISHED"}
