"""15 mm micro linear stepper on a bent steel bracket (as on the VCR cover).

    build_linear_stepper(name, origin=(0, 0, 0), facing=+1, parent=None) -> Empty

Local frame in millimetres: X along the lead screw, from the motor face
(X = 0) into the bracket; the can sits at X < 0. Y = 0 is the screw axis in
plan, Z = 0 the underside of the bracket base. facing=-1 turns the motor
180 degrees about Z (screw pointing to -X). Tags:
  [MEAS]     measured by the user from photos with a tape (about +-2 mm)
  [TYP]      typical for 15 mm can-stack linear steppers (CHIHAI SM15xx class:
             15 mm can, M3 x 0.5 lead screw)
  [ASSUMED]  estimate for appearance only
No carriage/slider is fitted, as on the real motors.
"""
import math

import bpy
import bmesh

from fdd_model import _box, _cyl, _v

BRACKET_L = 61.0        # [MEAS] motor face to the outside of the end flange
BRACKET_W = 10.0        # [ASSUMED] base strip width
BRACKET_T = 0.8         # [TYP] bent steel sheet
EAR = (6.0, 4.5)        # [ASSUMED] screw ear length (X) and reach beyond the base (Y)
EAR_X = (12.0, 47.0)    # [MEAS] screw positions along the bracket
END_FLANGE_H = 10.0     # [ASSUMED]
CAN_D, CAN_L = 15.0, 12.0          # [TYP] can-stack diameter, [MEAS] length
AXIS_Z = BRACKET_T + CAN_D / 2      # screw axis height above the cover
SCREW_D = 3.0           # [TYP] M3 lead screw
BUSH_D, BUSH_L = 5.0, 2.0          # [MEAS] black end bushing
SCREW_HEAD = (5.5, 1.8)            # [ASSUMED] mounting screw head d x h

COLORS = {
    "steel": (0.75, 0.76, 0.78, 1),
    "can": (0.8, 0.81, 0.83, 1),
    "brass": (0.8, 0.62, 0.25, 1),
    "black": (0.03, 0.03, 0.03, 1),
    "pcb": (0.75, 0.4, 0.1, 1),
    "screw": (0.85, 0.85, 0.87, 1),
}


def _bracket(bm):
    h = BRACKET_W / 2
    _box(bm, 0, -h, 0, BRACKET_L, h, BRACKET_T)                          # base
    _box(bm, 0, -CAN_D / 2, 0, BRACKET_T, CAN_D / 2, AXIS_Z + CAN_D / 2)  # motor flange
    _box(bm, BRACKET_L - BRACKET_T, -h - 1, 0, BRACKET_L, h + 1, END_FLANGE_H + BRACKET_T)
    for x in EAR_X:                                                        # screw ears
        _box(bm, x - EAR[0] / 2, h, 0, x + EAR[0] / 2, h + EAR[1], BRACKET_T)


def _can(bm):
    _cyl(bm, -CAN_L / 2, 0, AXIS_Z, CAN_D, CAN_L, axis="X")


def _screw(bm):
    _cyl(bm, (BRACKET_L - BRACKET_T) / 2, 0, AXIS_Z, SCREW_D, BRACKET_L - BRACKET_T, axis="X", seg=16)


def _bush(bm):
    _cyl(bm, BRACKET_L - BRACKET_T - BUSH_L / 2, 0, AXIS_Z, BUSH_D, BUSH_L, axis="X", seg=20)


def _pcb(bm):     # terminal board on the side of the can
    _box(bm, -CAN_L + 2, CAN_D / 2, AXIS_Z - 5, -2, CAN_D / 2 + 1.6, AXIS_Z + 5)


def _heads(bm):
    for x in EAR_X:
        _cyl(bm, x, BRACKET_W / 2 + EAR[1] / 2, BRACKET_T + SCREW_HEAD[1] / 2,
             SCREW_HEAD[0], SCREW_HEAD[1], seg=16)


PARTS = {"bracket": (_bracket, "steel"), "can": (_can, "can"), "screw": (_screw, "brass"),
         "bush": (_bush, "black"), "pcb": (_pcb, "pcb"), "heads": (_heads, "screw")}
_MESHES = {}


def _mesh(part):
    me = _MESHES.get(part)
    try:
        if me is not None:
            me.name
            return me
    except ReferenceError:
        pass
    bm = bmesh.new()
    PARTS[part][0](bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new("stepper_" + part)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(None)   # one slot, filled per object
    _MESHES[part] = me
    return me


def _material(key):
    name = "stepper_" + key
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = COLORS[key]
    return m


def build_linear_stepper(name, origin=(0.0, 0.0, 0.0), facing=1, parent=None, collection=None):
    coll = collection or bpy.context.scene.collection
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = 0.005
    coll.objects.link(root)
    if parent is not None:
        root.parent = parent
    root.location = _v(*origin)
    root.rotation_euler.z = 0.0 if facing > 0 else math.pi
    for part, (_, key) in PARTS.items():
        obj = bpy.data.objects.new(f"{name}.{part}", _mesh(part))
        coll.objects.link(obj)
        obj.parent = root
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = _material(key)
    return root
