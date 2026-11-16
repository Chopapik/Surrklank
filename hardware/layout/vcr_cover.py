"""Samsung VCR top cover used as a resonance box for stepper motors.

    build_vcr_cover(name, origin=(0, 0, 0), collection=None) -> object

An inverted U: a flat top plate with two side walls on the short sides; front
and back are open, and only the rear long edge has a folded lip. origin is the min corner (left-front-bottom) in millimetres;
X = long side, Y = wall length, Z = height. With steppers=True the four corner linear steppers
(linear_stepper.py) are added on top.
Tags:
  [MEAS]     measured by the user with a tape measure
  [PHOTO]    read from photos, roughly +-3 mm
  [ASSUMED]  estimate for appearance only
"""
import bpy
import bmesh

from fdd_model import MM, _box, _cyl, _boolean, _v
import importlib
import linear_stepper
importlib.reload(linear_stepper)
from linear_stepper import build_linear_stepper

LENGTH = 398.0     # [MEAS] long side of the top plate
TOP_W = 284.0      # [MEAS] short side of the top plate
WALL_L = 290.0     # [MEAS] side wall length (along Y)
HEIGHT = 90.0      # [MEAS] side wall height = overall height
T = 0.5            # [MEAS] sheet thickness
LIP = 10.0         # [PHOTO] lip folded down along the rear long edge only
TAB_W, TAB_H = 40.0, 20.0             # [PHOTO] deeper screw tabs in the lips
TAB_X = (60.0, LENGTH / 2, LENGTH - 60.0)   # [PHOTO] tab centres
TAB_HOLE_D, TAB_HOLE_Z = 4.0, 15.0    # [ASSUMED] hole d, depth below the top
WALL_HOLE_D, WALL_HOLE_Z = 4.0, 12.0  # [PHOTO] screw holes near the foot
WALL_HOLE_Y = (25.0, WALL_L - 25.0)   # [PHOTO]
COLOR = (0.06, 0.06, 0.065, 1)
# four linear steppers, one per corner: brackets start at the short edges and
# run inward along X, cans overhang the edges outward
STEPPER_IN_FROM_FRONT = 20.0   # [PHOTO] screw axis from the front long edge
STEPPER_IN_FROM_REAR = 25.0    # [MEAS] screw axis from the rear long edge

_Y0 = (WALL_L - TOP_W) / 2            # top plate is centred on the walls
_LIP_Y = _Y0 + TOP_W - T              # the front edge (Y = _Y0) has no lip


def _parts():
    """(name, build, cut) per sheet piece. Pieces are kept separate because a
    single Boolean over touching 0.5 mm boxes drops the thin lip faces."""
    parts = [("top", lambda bm: _box(bm, 0, _Y0, HEIGHT - T, LENGTH, _Y0 + TOP_W, HEIGHT), None)]
    for side, x0 in (("left", 0), ("right", LENGTH - T)):
        def wall(bm, x0=x0):
            _box(bm, x0, 0, 0, x0 + T, WALL_L, HEIGHT - T)

        def wall_cut(bm, x0=x0):
            for y in WALL_HOLE_Y:
                _cyl(bm, x0 + T / 2, y, WALL_HOLE_Z, WALL_HOLE_D, T + 2, axis="X", seg=20)
        parts.append((f"wall_{side}", wall, wall_cut))
    parts.append(("lip", lambda bm: _box(bm, T, _LIP_Y, HEIGHT - LIP, LENGTH - T, _LIP_Y + T, HEIGHT - T), None))
    for k, xc in enumerate(TAB_X):
        def tab(bm, xc=xc):
            _box(bm, xc - TAB_W / 2, _LIP_Y, HEIGHT - TAB_H, xc + TAB_W / 2, _LIP_Y + T, HEIGHT - LIP)

        def tab_cut(bm, xc=xc):
            _cyl(bm, xc, _LIP_Y + T / 2, HEIGHT - TAB_HOLE_Z, TAB_HOLE_D, T + 2, axis="Y", seg=20)
        parts.append((f"tab{k + 1}", tab, tab_cut))
    return parts


def build_vcr_cover(name, origin=(0.0, 0.0, 0.0), collection=None, steppers=True):
    """Create the cover as an Empty with one child per sheet piece."""
    coll = collection or bpy.context.scene.collection
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = 0.01
    root.location = _v(*origin)
    coll.objects.link(root)
    mat = bpy.data.materials.get("vcr_cover") or bpy.data.materials.new("vcr_cover")
    mat.diffuse_color = COLOR
    for part, build, cut in _parts():
        bm = bmesh.new()
        build(bm)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        if cut is None:
            me = bpy.data.meshes.new(f"{name}.{part}")
            bm.to_mesh(me)
        else:
            cbm = bmesh.new()
            cut(cbm)
            bmesh.ops.recalc_face_normals(cbm, faces=cbm.faces[:])
            me = _boolean(bm, cbm, f"{name}.{part}")
            cbm.free()
        bm.free()
        me.materials.clear()
        me.materials.append(mat)
        obj = bpy.data.objects.new(f"{name}.{part}", me)
        coll.objects.link(obj)
        obj.parent = root
    if steppers:
        for side, x, facing in (("l", 0.0, 1), ("r", LENGTH, -1)):
            for end, y in (("f", _Y0 + STEPPER_IN_FROM_FRONT), ("r", _Y0 + TOP_W - STEPPER_IN_FROM_REAR)):
                build_linear_stepper(f"{name}.stepper_{side}{end}", (x, y, HEIGHT), facing,
                                     parent=root, collection=coll)
    return root
