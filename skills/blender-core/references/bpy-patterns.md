# bpy patterns (Blender 5.2, each block runs standalone; CI executes them)

## Create a mesh from data (fastest, no operators)
```python
import bpy
verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
me = bpy.data.meshes.new("Quad")
me.from_pydata(verts, [], [(0, 1, 2, 3)])
me.validate(); me.update()
ob = bpy.data.objects.new("Quad", me)
bpy.context.scene.collection.objects.link(ob)
```

## bmesh edit (object mode) and write back
```python
import bpy, bmesh
me = bpy.data.meshes.new("BM"); ob = bpy.data.objects.new("BM", me)
bpy.context.scene.collection.objects.link(ob)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.bevel(bm, geom=bm.edges[:], offset=0.05, segments=2, affect="EDGES", profile=0.5)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
bm.to_mesh(me); bm.free()
```
In Edit Mode use `bm = bmesh.from_edit_mesh(me)` … `bmesh.update_edit_mesh(me)` and don't free it.

## numpy bulk read/write (100x faster than Python loops)
```python
import bpy, numpy as np
me = bpy.data.meshes.new("NP"); me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
co = np.empty(len(me.vertices) * 3, dtype=np.float32)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3); co[:, 2] += 0.5
me.vertices.foreach_set("co", co.ravel()); me.update()
```

## Generic attributes (float/int/bool/color on any domain)
```python
import bpy
me = bpy.data.meshes.new("Attr"); me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
a = me.attributes.get("mask") or me.attributes.new("mask", "FLOAT", "POINT")
a.data.foreach_set("value", [0.0, 0.5, 1.0])
col = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
me.color_attributes.active_color = col
```

## Operator with context override (works headless)
```python
import bpy
me = bpy.data.meshes.new("Ov"); me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
ob = bpy.data.objects.new("Ov", me); bpy.context.scene.collection.objects.link(ob)
ob.modifiers.new("Weld", "WELD")
with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                               selected_editable_objects=[ob]):
    assert bpy.ops.object.modifier_apply(modifier="Weld") == {"FINISHED"}
```

## Evaluated mesh (modifiers applied) without changing the object
```python
import bpy
me = bpy.data.meshes.new("Ev"); me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
ob = bpy.data.objects.new("Ev", me); bpy.context.scene.collection.objects.link(ob)
ob.modifiers.new("Sub", "SUBSURF").levels = 2
dg = bpy.context.evaluated_depsgraph_get()
eo = ob.evaluated_get(dg); tmp = eo.to_mesh()
n_faces = len(tmp.polygons)
eo.to_mesh_clear()
baked = bpy.data.meshes.new_from_object(eo)  # persistent copy, if you need one
```

## Materials: find nodes by type, link textures
```python
import bpy
mat = bpy.data.materials.new("M")            # already has Principled + Output (5.0+)
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.new("Base", 64, 64)
tex.image.colorspace_settings.name = "sRGB"   # data maps: "Non-Color"
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.6
```

## Geometry Nodes modifier inputs (5.2 RNA API)
```python
import bpy
ng = bpy.data.node_groups.new("GN", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
sock = ng.interface.new_socket("Scale", in_out="INPUT", socket_type="NodeSocketFloat")
gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
ng.links.new(gi.outputs["Geometry"], go.inputs["Geometry"])
me = bpy.data.meshes.new("G"); ob = bpy.data.objects.new("G", me)
bpy.context.scene.collection.objects.link(ob)
mod = ob.modifiers.new("GN", "NODES"); mod.node_group = ng
getattr(mod.properties.inputs, sock.identifier).value = 2.0
```

## Keyframes with slotted actions (5.0+)
```python
import bpy
from bpy_extras import anim_utils
ob = bpy.data.objects.new("Anim", None); bpy.context.scene.collection.objects.link(ob)
act = bpy.data.actions.new("Anim_Move")
ob.animation_data_create(); ob.animation_data.action = act
slot = ob.animation_data.action_slot or act.slots.new(id_type="OBJECT", name=ob.name)
ob.animation_data.action_slot = slot
cb = anim_utils.action_ensure_channelbag_for_slot(act, slot)
for i in range(3):
    fc = cb.fcurves.ensure("location", index=i, group_name="Object Transforms")
    fc.keyframe_points.insert(1, 0.0); fc.keyframe_points.insert(24, 2.0 if i == 0 else 0.0)
```
The simple route works too: `ob.keyframe_insert("location", frame=1)` creates the action and slot.

## Drivers
```python
import bpy
ob = bpy.data.objects.new("Drv", None); bpy.context.scene.collection.objects.link(ob)
ctl = bpy.data.objects.new("Ctl", None); bpy.context.scene.collection.objects.link(ctl)
fc = ob.driver_add("location", 2)
d = fc.driver; d.type = "SCRIPTED"
v = d.variables.new(); v.name = "x"; v.type = "TRANSFORMS"
v.targets[0].id = ctl; v.targets[0].transform_type = "LOC_X"; v.targets[0].transform_space = "LOCAL_SPACE"
d.expression = "x * 0.5"
```
Prefer simple expressions (`var`, `x*0.5`, `max(a,b)`), which run without Python auto-exec. Use `d.type="SUM"/"AVERAGE"` when possible.

## Append / link from another .blend
```python
import bpy, os, tempfile
src = os.path.join(tempfile.gettempdir(), "bas_lib.blend")
bpy.data.materials.new("LibMat").use_fake_user = True
bpy.data.libraries.write(src, {bpy.data.materials["LibMat"]}, fake_user=True)
with bpy.data.libraries.load(src, link=False) as (data_from, data_to):  # link=True to link
    data_to.materials = [n for n in data_from.materials if n == "LibMat"]
```
Linked objects need a library override to be edited: `ob.override_hierarchy_create(scene, view_layer)`.

## Collections and safe naming
```python
import bpy
def ensure_collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if col.name not in parent.children:
        parent.children.link(col)
    return col
ob = bpy.data.objects.new("SM_Crate", None)
ensure_collection("Export").objects.link(ob)
```

## Apply transforms without selection juggling
```python
import bpy
from mathutils import Matrix
me = bpy.data.meshes.new("T"); me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
ob = bpy.data.objects.new("T", me); bpy.context.scene.collection.objects.link(ob)
ob.scale = (2, 2, 2); ob.rotation_euler = (0, 0, 1.0)
bpy.context.view_layer.update()
loc, rot, sca = ob.matrix_basis.decompose()
ob.data.transform(Matrix.LocRotScale(None, rot, sca))   # bake rot+scale into mesh
ob.matrix_basis = Matrix.Translation(loc)
```
For multi-user mesh data, call `ob.data = ob.data.copy()` first, or every user gets transformed.

## Handlers and timers (live sessions / add-ons)
```python
import bpy
def on_frame(scene, depsgraph=None):
    pass
bpy.app.handlers.frame_change_post.append(on_frame)
bpy.app.handlers.frame_change_post.remove(on_frame)
bpy.app.timers.register(lambda: None, first_interval=0.5)  # return float to repeat, None to stop
```

## Render a still headless
```python
import bpy, os, tempfile
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.render.resolution_x = sc.render.resolution_y = 64
sc.render.image_settings.media_type = "IMAGE"; sc.render.image_settings.file_format = "PNG"
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam)
cam.location = (0, -5, 0); cam.rotation_euler = (1.5708, 0, 0); sc.camera = cam
sc.render.filepath = os.path.join(tempfile.gettempdir(), "bas_still.png")
bpy.ops.render.render(write_still=True)
```
