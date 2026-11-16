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
    _box("table", TABLE, (0, 0, -TABLE[2]), (0.8, 0.7, 0.5, 1))
    for i in range(FDD_COUNT):  # row 1: on the table from the origin
        build_fdd(f"fdd_a{i + 1}", (i * FDD_W, 0, 0))
    row_w = FDD_COUNT * FDD_W
    by = FDD_D                              # board directly behind row 1
    bx = (row_w - BOARD[0]) / 2
    for k, rx in enumerate((bx + ROLL_D / 2 + 10, bx + BOARD[0] - ROLL_D / 2 - 10)):
        _cyl(f"roll{k + 1}", ROLL_D, ROLL_H, (rx, by + BOARD[1] / 2), 0, (0.85, 0.8, 0.3, 1))
    _box("board", BOARD, (bx, by, ROLL_H), (0.6, 0.4, 0.2, 1))
    z2 = ROLL_H + BOARD[2]
    y2 = by + BOARD[1] - FDD_D              # rear-aligned with the board's back edge
    for i in range(FDD_COUNT):
        build_fdd(f"fdd_b{i + 1}", (i * FDD_W, y2, z2))


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
