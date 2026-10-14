# gn_builder recipes (specs verified on 5.2)

Pass these as `spec=` (MCP) or save them as JSON for `--spec`. Run `--describe` to check socket names when you change node types.

## Scatter instances on a surface
```json
{"name": "GN_Scatter",
 "inputs": [["Geometry","GEOMETRY"], ["Density","FLOAT",10,{"min":0}], ["Seed","INT",0],
            ["Instance","OBJECT"], ["Scale Min","FLOAT",0.8], ["Scale Max","FLOAT",1.2]],
 "outputs": [["Geometry","GEOMETRY"]],
 "nodes": {
   "dist": ["GeometryNodeDistributePointsOnFaces", {"distribute_method":"RANDOM"}],
   "obj":  ["GeometryNodeObjectInfo", {"transform_space":"RELATIVE"}],
   "rnd":  ["FunctionNodeRandomValue", {"data_type":"FLOAT"}],
   "inst": ["GeometryNodeInstanceOnPoints"],
   "join": ["GeometryNodeJoinGeometry"]},
 "links": [["in.Geometry","dist.Mesh"], ["in.Density","dist.Density"], ["in.Seed","dist.Seed"],
           ["in.Instance","obj.Object"], ["dist.Points","inst.Points"], ["obj.Geometry","inst.Instance"],
           ["dist.Rotation","inst.Rotation"],
           ["in.Scale Min","rnd.Min"], ["in.Scale Max","rnd.Max"], ["in.Seed","rnd.Seed"], ["rnd.Value","inst.Scale"],
           ["inst.Instances","join.Geometry"], ["in.Geometry","join.Geometry"], ["join.Geometry","out.Geometry"]]}
```
5.2: Random Value has dynamic sockets (`Min`, `Max`, `ID`, `Seed` → `Value`) whose type follows `data_type`. Older tutorials use index-based duplicates, which no longer exist. Distribute Points outputs `Rotation` (aligned to the normal) directly.

## Pipe / cable along a curve
```json
{"name": "GN_Pipe",
 "inputs": [["Geometry","GEOMETRY"], ["Radius","FLOAT",0.05], ["Resolution","INT",12]],
 "outputs": [["Geometry","GEOMETRY"]],
 "nodes": {"circle": ["GeometryNodeCurvePrimitiveCircle"],
           "c2m": ["GeometryNodeCurveToMesh", {}, {"Fill Caps": true}],
           "smooth": ["GeometryNodeSetShadeSmooth"]},
 "links": [["in.Resolution","circle.Resolution"], ["in.Radius","circle.Radius"],
           ["in.Geometry","c2m.Curve"], ["circle.Curve","c2m.Profile Curve"],
           ["c2m.Mesh","smooth.Geometry"], ["smooth.Geometry","out.Geometry"]]}
```
Apply to a curve object (`bpy.data.curves.new(..., "CURVE")`). Add `Resample Curve` for even segments.

## Repeat zone (iterative subdivide)
```json
{"name": "GN_Repeat", "inputs": [["Geometry","GEOMETRY"], ["Count","INT",3]], "outputs": [["Geometry","GEOMETRY"]],
 "nodes": {"rin": ["GeometryNodeRepeatInput"], "rout": ["GeometryNodeRepeatOutput"],
           "sub": ["GeometryNodeSubdivideMesh", {}, {"Level": 1}]},
 "pairs": [["rin","rout"]],
 "links": [["in.Count","rin.Iterations"], ["in.Geometry","rin.Geometry"], ["rin.Geometry","sub.Mesh"],
           ["sub.Mesh","rout.Geometry"], ["rout.Geometry","out.Geometry"]]}
```
The repeat output starts with one `Geometry` item. Add more state with the 4th node field: `{"repeat_items": [["GEOMETRY","Geometry"], ["FLOAT","Value"]]}`.

## Store a mask attribute for shaders/export
```json
{"name": "GN_HeightMask", "inputs": [["Geometry","GEOMETRY"]], "outputs": [["Geometry","GEOMETRY"]],
 "nodes": {"pos": ["GeometryNodeInputPosition"], "sep": ["ShaderNodeSeparateXYZ"],
           "store": ["GeometryNodeStoreNamedAttribute", {"data_type":"FLOAT","domain":"POINT"}, {"Name":"_height"}]},
 "links": [["in.Geometry","store.Geometry"], ["pos.Position","sep.Vector"], ["sep.Z","store.Value"],
           ["store.Geometry","out.Geometry"]]}
```
Read it in a material with an Attribute node (`attribute_name="_height"`). glTF exports `_`-prefixed attributes with `export_attributes=True`.

## Shader tree with the same builder
```json
{"tree": "shader", "material": "M_Rust",
 "nodes": {"out": ["ShaderNodeOutputMaterial"], "bsdf": ["ShaderNodeBsdfPrincipled"],
           "noise": ["ShaderNodeTexNoise", {}, {"Scale": 8.0}], "ramp": ["ShaderNodeValToRGB"]},
 "links": [["noise.Fac","ramp.Fac"], ["ramp.Color","bsdf.Base Color"], ["bsdf.BSDF","out.Surface"]]}
```
