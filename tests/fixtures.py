"""Procedural test fixtures (no binary .blend files in the repo)."""
import bmesh
import bpy
from mathutils import Matrix


def mesh_object(name, build, location=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = location
    bpy.context.scene.collection.objects.link(ob)
    return ob


def cube(name="Cube", size=2.0, location=(0, 0, 0)):
    return mesh_object(name, lambda bm: bmesh.ops.create_cube(bm, size=size), location)


def uv_sphere(name="Sphere", radius=1.0, segs=32, rings=16, location=(0, 0, 0)):
    return mesh_object(name, lambda bm: bmesh.ops.create_uvsphere(
        bm, u_segments=segs, v_segments=rings, radius=radius), location)


def plane(name="Plane", size=2.0, location=(0, 0, 0)):
    return mesh_object(name, lambda bm: bmesh.ops.create_grid(
        bm, x_segments=1, y_segments=1, size=size / 2), location)


def zfight_pair():
    """Two coplanar overlapping planes in different objects + one inside a single mesh."""
    a = plane("ZF_A")
    b = plane("ZF_B", location=(0.5, 0, 0))

    def two_layers(bm):
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1)
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5,
                              matrix=Matrix.Translation((0.2, 0, 0)))
    c = mesh_object("ZF_Self", two_layers, location=(5, 0, 0))
    return a, b, c


def detached_part():
    """A body with a floating island and a separate floating object."""
    def build(bm):
        bmesh.ops.create_cube(bm, size=2)
        bmesh.ops.create_cube(bm, size=0.3, matrix=Matrix.Translation((0, 0, 1.6)))
    body = mesh_object("Body", build)
    floater = cube("Floater", size=0.3, location=(3, 0, 3))
    return body, floater


def unwrap(ob):
    """Smart-project UVs so bake/texel tests have a UV map."""
    from _bpyx import select_only
    select_only([ob])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def street():
    """Ground slab (top at z=0), two buildings, a grey sphere, each with a Principled material, and a
    camera looking down the street. Returns the object names."""
    def mat(ob, rgb):
        m = bpy.data.materials.new("M_" + ob.name)
        b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*rgb, 1)
        ob.data.materials.append(m)
        return ob
    mat(cube("Ground", size=1, location=(0, 0, -0.05)), (0.18, 0.18, 0.18)).scale = (30, 30, 0.1)
    mat(cube("BldA", size=1, location=(-5, 6, 4)), (0.45, 0.4, 0.35)).scale = (4, 4, 8)
    mat(cube("BldB", size=1, location=(5, 8, 5)), (0.3, 0.32, 0.35)).scale = (4, 4, 10)
    mat(uv_sphere("Ball", radius=1, location=(0, 0, 1)), (0.18, 0.18, 0.18))
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location, cam.rotation_euler = (0, -14, 3), (1.48, 0, 0)
    bpy.context.scene.camera = cam
    bpy.context.view_layer.update()
    return ["Ground", "BldA", "BldB", "Ball"]


def simple_character():
    """Capsule-ish mesh + 3-bone chain armature, auto-weighted. Returns (mesh, armature)."""
    def build(bm):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.3, radius2=0.3,
                              depth=2.0, matrix=Matrix.Translation((0, 0, 1)))
    body = mesh_object("Char", build)
    me = body.data
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.subdivide(number_cuts=8)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm_data = bpy.data.armatures.new("CharRig")
    arm = bpy.data.objects.new("CharRig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    prev = None
    for i, nm in enumerate(("root", "spine", "chest")):
        b = arm_data.edit_bones.new(nm)
        b.head, b.tail = (0, 0, i * 0.66), (0, 0, (i + 1) * 0.66)
        if prev:  # spine (hips) unconnected from root so it can translate; chest connected
            b.parent, b.use_connect = prev, nm == "chest"
        prev = b
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    body.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    assert me.vertices
    return body, arm
