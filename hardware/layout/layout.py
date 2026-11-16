"""Surrklank stack layout built from fdd_model.build_fdd.

Origin (0,0,0) = left-front corner of the table top; X right, Y back, Z up.
Dimensions in millimetres, Blender units are metres (MM = 0.001).

Headless:  Blender -b --python layout.py -- <out_dir>
Live (GUI, via live_server.py):  exec(open(".../layout.py").read()); build_scene()
"""
import math
import os
import sys

import bpy
from mathutils import Vector

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # exec() from the live server has no __file__
    _HERE = os.environ.get("SURRKLANK_LAYOUT_DIR", os.getcwd())
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import importlib

import fdd_model
importlib.reload(fdd_model)  # pick up edits in a long-running GUI session
from fdd_model import MM, DEPTH as FDD_D, WIDTH as FDD_W, build_fdd

TABLE = (550, 550, 50)         # IKEA table, X, Y, Z
BOARD = (400, 73, 28)          # X, Y, Z
ROLL_D, ROLL_H = 70, 50        # [ASSUMED] diameter; height from layout
FDD_COUNT = 4
ATX = (85, 149, 140)           # ATX PSU case standing upright, X, Y, Z (plain box)
SHELF = (455, 285, 15)         # black shelf on the two ATX cases, X, Y, Z
BLACK = (0.03, 0.03, 0.03, 1)
# Riser for rows 2 and 3: "rolls" = tape rolls under the boards (current real
# setup), "cheeks" = proposed stepped side plates outside the rows, so nothing
# stands behind the drives' rear connectors
SUPPORT = "cheeks"
CHEEK_T = 12                   # plywood side plate; 12 mm leaves 3 mm walls round a 6 mm dowel
STEP_Z = 64                    # equal row-to-row height step with cheeks
WOOD = (0.6, 0.4, 0.2, 1)
STEEL = (0.55, 0.57, 0.6, 1)
BEECH = (0.9, 0.8, 0.6, 1)
DOWEL = (6, 20)                # [TYP] beech dowel d x length: 10 mm in each part
STRETCHER = (18, 30)           # rear stretcher between the cheeks, depth x height
SCREW_D, SCREW_HEAD = 3.5, (7, 1.5)   # [TYP] wood screw shank d, head d x h
SCREW_L_CHEEK, SCREW_L_STRETCHER = 10, 30  # plate into cheek; through cheek into stretcher end
FLAT = (60, 15, 2)             # [TYP] flat mending plate across the cheek seam: length, width, t


def _mat(name, color):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = color
    return m


def _box(name, size, min_corner, color):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.name = name
    o.scale = [s * MM for s in size]
    o.location = [(min_corner[i] + size[i] / 2) * MM for i in range(3)]
    o.data.materials.append(_mat(name, color))
    return o


def _screw(name, at, axis, sign, length):
    """Screw whose head sits on a metal face at `at`; it points along `axis`
    (0 = X, 2 = Z) in direction `sign` into the wood. Returns nothing."""
    rot = {0: (0, math.pi / 2, 0), 2: (0, 0, 0)}[axis]
    for part, d, a, b in (("shank", SCREW_D, 0, length), ("head", SCREW_HEAD[0], -SCREW_HEAD[1], 0)):
        c = list(at)
        c[axis] += sign * (a + b) / 2
        bpy.ops.mesh.primitive_cylinder_add(radius=d / 2 * MM, depth=(b - a) * MM,
                                            vertices=16, location=[v * MM for v in c], rotation=rot)
        o = bpy.context.object
        o.name = f"{name}_{part}"
        o.data.materials.append(_mat("screw", (0.85, 0.75, 0.3, 1)))


def _cyl(name, d, h, centre_xy, z0, color):
    bpy.ops.mesh.primitive_cylinder_add(radius=d / 2 * MM, depth=h * MM, vertices=64)
    o = bpy.context.object
    o.name = name
    o.location = (centre_xy[0] * MM, centre_xy[1] * MM, (z0 + h / 2) * MM)
    o.data.materials.append(_mat(name, color))
    return o


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def build_scene(clear=True):
    if clear:
        clear_scene()
    _box("table", TABLE, (0, 0, -TABLE[2]), BLACK)
    # shelf bridge in the left-rear corner: left ATX flush with the table's
    # left and rear edges, shelf front and left edges flush with it (the shelf
    # overhangs the table's rear edge), right ATX mirrored under its right end
    ay = TABLE[1] - ATX[1]
    sy = ay
    _box("atx1", ATX, (0, ay, 0), BLACK)
    _box("atx2", ATX, (SHELF[0] - ATX[0], ay, 0), BLACK)
    _box("shelf", SHELF, (0, sy, ATX[2]), BLACK)
    row_w = FDD_COUNT * FDD_W
    cheeks = SUPPORT == "cheeks"
    x0 = CHEEK_T if cheeks else 0           # rows sit between the cheeks
    for i in range(FDD_COUNT):  # row 1: on the table
        build_fdd(f"fdd_a{i + 1}", (x0 + i * FDD_W, 0, 0))
    by2 = FDD_D                             # row 2 board directly behind row 1
    y2 = by2 + (BOARD[1] - FDD_D) / 2       # row 2 centred on its board in depth
    y3 = 2 * y2                             # row 3 set back by the same step;
    by3 = y3 + (FDD_D - BOARD[1]) / 2       # must stay in front of the ATX/shelf
    if cheeks:
        z2, z3 = _cheeks(row_w, by2, by3)
    else:
        bx = (row_w - BOARD[0]) / 2
        z2 = _riser("", bx, by2, 1)
        z3 = _riser("c", bx, by3, 2)
    for i in range(FDD_COUNT):
        build_fdd(f"fdd_b{i + 1}", (x0 + i * FDD_W, y2, z2))
    for i in range(FDD_COUNT):
        build_fdd(f"fdd_c{i + 1}", (x0 + i * FDD_W, y3, z3))


def _cheeks(row_w, by2, by3):
    """Two stepped side plates outside the rows carrying full-width boards.

    Board tops at STEP_Z and 2 * STEP_Z, so the rows rise in equal steps.
    Returns both board tops.
    """
    h2, h3 = STEP_Z - BOARD[2], 2 * STEP_Z - BOARD[2]   # board undersides
    blen = row_w + 2 * CHEEK_T
    for k, cx in enumerate((0, CHEEK_T + row_w)):
        _box(f"cheek{k + 1}_low", (CHEEK_T, by3 + BOARD[1] - by2, h2), (cx, by2, 0), WOOD)
        _box(f"cheek{k + 1}_high", (CHEEK_T, BOARD[1], h3 - h2), (cx, by3, h2), WOOD)
    # boards are lift-off trays: they lie on the cheeks, located by dowels
    _box("board", (blen, BOARD[1], BOARD[2]), (0, by2, h2), WOOD)
    _box("boardc", (blen, BOARD[1], BOARD[2]), (0, by3, h3), WOOD)
    dd, dl = DOWEL
    for k, cx in enumerate((CHEEK_T / 2, CHEEK_T * 1.5 + row_w)):   # cheek mid-planes
        for tray, by, h in (("b", by2, h2), ("c", by3, h3)):
            for j, y in enumerate((by + 15, by + BOARD[1] - 15)):
                _cyl(f"dowel_{tray}{k + 1}_{j + 1}", dd, dl, (cx, y), h - dl / 2, BEECH)
        for j, y in enumerate((by2 + 20, by3 + BOARD[1] - 20)):          # into the table
            _cyl(f"dowel_t{k + 1}_{j + 1}", dd, dl, (cx, y), -dl / 2, BEECH)
    # permanent rear stretcher between the cheeks keeps the frame square
    sw, sh = STRETCHER
    sy = by3 + BOARD[1] - sw
    _box("stretcher", (row_w, sw, sh), (CHEEK_T, sy, 0), WOOD)
    for x_out, d in ((0, 1), (2 * CHEEK_T + row_w, -1)):
        for j, z in enumerate((sh * 0.3, sh * 0.7)):
            _screw(f"stretcher_s{'lr'[d < 0]}{j + 1}", (x_out, sy + sw / 2, z), 0, d, SCREW_L_STRETCHER)
    # flat plates join the upper cheek part to the lower one (inner faces)
    for x_in, d in ((CHEEK_T, 1), (CHEEK_T + row_w, -1)):
        for k, y in enumerate((by3 + 8, by3 + BOARD[1] - 8 - FLAT[1])):
            xf = x_in if d > 0 else x_in - FLAT[2]
            _box(f"plate{1 if d > 0 else 2}_{k + 1}", (FLAT[2], FLAT[1], FLAT[0]),
                 (xf, y, h2 - FLAT[0] / 2), STEEL)
            for j, o in enumerate((-22, -10, 10, 22)):  # two holes each side of the seam
                _screw(f"plate{1 if d > 0 else 2}_{k + 1}_s{j + 1}",
                       (x_in + d * FLAT[2], y + FLAT[1] / 2, h2 + o), 0, -d, SCREW_L_CHEEK)
    return h2 + BOARD[2], h3 + BOARD[2]


def _riser(tag, bx, by, stack):
    """Board BOARD at (bx, by) on two piles of `stack` tape rolls; returns its top z."""
    for k, rx in enumerate((bx + ROLL_D / 2 + 10, bx + BOARD[0] - ROLL_D / 2 - 10)):
        for j in range(stack):
            _cyl(f"roll{tag}{k + 1}" + (f"_{j + 1}" if stack > 1 else ""), ROLL_D, ROLL_H,
                 (rx, by + BOARD[1] / 2), j * ROLL_H, (0.85, 0.8, 0.3, 1))
    _box(f"board{tag}", BOARD, (bx, by, stack * ROLL_H), WOOD)
    return stack * ROLL_H + BOARD[2]

def setup_render(res=(1400, 1000)):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.render.resolution_x, sc.render.resolution_y = res
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 1))
    bpy.context.object.data.energy = 3
    bpy.context.object.rotation_euler = (math.radians(50), 0, math.radians(30))
    return sc


def render_view(name, loc_mm, target_mm, out_dir, ortho_scale=None):
    sc = bpy.context.scene
    cam_data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cam_data)
    sc.collection.objects.link(cam)
    cam.location = [c * MM for c in loc_mm]
    cam.rotation_euler = (Vector([c * MM for c in target_mm]) - cam.location).to_track_quat("-Z", "Y").to_euler()
    if ortho_scale:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho_scale * MM
    cam_data.clip_end = 20
    sc.camera = cam
    sc.render.filepath = os.path.join(out_dir, f"{name}.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__" or "--" in sys.argv:
    if "--" in sys.argv and len(sys.argv) > sys.argv.index("--") + 1:
        out = sys.argv[-1]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build_scene(clear=False)
        setup_render()
        render_view("iso", (-350, -450, 450), (200, 250, 30), out)
        render_view("top", (203, 190, 1200), (203, 190, 0), out, ortho_scale=700)
        render_view("front", (203, -1500, 50), (203, 0, 50), out, ortho_scale=650)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "layout.blend"))
