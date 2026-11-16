"""Interconnect cables from docs/WIRING.md, laid out flat for planning.

    build_cables(origin=(x, y, z), cables=CABLES) -> [Empty]

Each cable lies straight along +Y with its first connector at Y = 0, the
cables side by side along +X. Real routing comes later. Ribbons are cut from
recycled 40-wire IDE cables, so every ribbon is shown at the stock length.
Tags:
  [MEAS]     measured by the user (about +-40 mm)
  [STD]      IDC / JST-XH standard dimension
  [TYP]      typical part, not measured
  [ASSUMED]  estimate for appearance only
"""
import bpy
import bmesh

from fdd_model import _box, _cyl, _v

IDE_LEN = 370.0          # [MEAS] recycled 40-wire IDE ribbon length
LSM_LEN = 440.0          # [MEAS] 4-wire LSM lead to its DRV8833 slot
PITCH = 1.27             # [STD] ribbon wire pitch
RIBBON_T = 0.9           # [TYP]
IDC_DEPTH, IDC_H = 6.0, 9.0      # [TYP] socket body along the cable and height
IDC_END = 2.55           # [TYP] socket body beyond the outer contacts, each side
SPLIT_LEN = 150.0        # [ASSUMED] split length of a drive ribbon = arm length of the T
WIRE_D = 1.4             # [TYP] 26 AWG hook-up wire
XH = (2.5, 5.75, 7.0)    # [STD] JST-XH pitch, housing depth along the cable, height
GAP = 15.0               # spacing between laid-out cables

# name: (kind, wires, length, note) -- kinds: ribbon (IDC both ends),
# drive (40-pin IDE header end, split into two 20-wire halves on 34-pin FDD
# sockets), lsm (loose wires with a JST-XH housing at the driver end)
CABLES = [
    ("ribbon_mainboard_fdd1", "ribbon", 16, IDE_LEN, "mainboard -> FDD module 1 IN"),
    ("ribbon_fdd1_fdd2", "ribbon", 16, IDE_LEN, "FDD module 1 OUT -> FDD module 2 IN"),
    ("ribbon_mainboard_act1", "ribbon", 16, IDE_LEN, "mainboard -> actuator module 1 IN"),
    ("ribbon_act1_leds", "ribbon", 16, IDE_LEN, "actuator module 1 OUT -> LED board (proposed)"),
    ("ribbon_panel", "ribbon", 10, IDE_LEN, "mainboard J6 -> panel J1 (optional, 1-2 m planned)"),
    ("drive_fdd1_a", "drive", 40, IDE_LEN, "FDD module 1, drives 1-2"),
    ("drive_fdd1_b", "drive", 40, IDE_LEN, "FDD module 1, drives 3-4"),
    ("drive_fdd2_a", "drive", 40, IDE_LEN, "FDD module 2, drives 5-6"),
    ("drive_fdd2_b", "drive", 40, IDE_LEN, "FDD module 2, drives 7-8"),
    ("lsm1", "lsm", 4, LSM_LEN, "LSM1 -> actuator slot"),
    ("lsm2", "lsm", 4, LSM_LEN, "LSM2 -> actuator slot"),
    ("lsm3", "lsm", 4, LSM_LEN, "LSM3 -> actuator slot"),
    ("lsm4", "lsm", 4, LSM_LEN, "LSM4 -> actuator slot"),
]

COLORS = {
    "ribbon": (0.72, 0.72, 0.70, 1),
    "red": (0.7, 0.05, 0.05, 1),
    "idc": (0.04, 0.04, 0.04, 1),
    "xh": (0.92, 0.9, 0.85, 1),
    # [ASSUMED] lead colours, pin 1 first
    "w1": (0.7, 0.05, 0.05, 1), "w2": (0.05, 0.15, 0.7, 1),
    "w3": (0.05, 0.5, 0.1, 1), "w4": (0.04, 0.04, 0.04, 1),
}


def _material(key):
    name = "cable_" + key
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = COLORS[key]
    return m


def _add(name, fill, key, root, coll):
    bm = bmesh.new()
    fill(bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(_material(key))
    obj = bpy.data.objects.new(name, me)
    coll.objects.link(obj)
    obj.parent = root


def _strip(bm, x0, n, y0, y1):
    _box(bm, x0, y0, 0, x0 + n * PITCH, y1, RIBBON_T)


def _quad(bm, pts, z0):
    """Flat ribbon piece over the plan quad pts (counter-clockwise), from z0 up."""
    vs = [bm.verts.new(_v(x, y, z)) for z in (z0, z0 + RIBBON_T) for x, y in pts]
    for f in ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([vs[i] for i in f])


def _socket(bm, x_first, contacts, y0):
    """2-row IDC socket; x_first is the left edge of contact 1's wire."""
    _box(bm, x_first - IDC_END, y0, 0, x_first + contacts * PITCH + IDC_END, y0 + IDC_DEPTH, IDC_H)


def _ribbon(name, n, length, root, coll):
    _add(f"{name}.ribbon", lambda bm: _strip(bm, PITCH, n - 1, 0, length), "ribbon", root, coll)
    _add(f"{name}.red", lambda bm: _strip(bm, 0, 1, 0, length), "red", root, coll)
    _add(f"{name}.idc", lambda bm: (_socket(bm, 0, n, 0), _socket(bm, 0, n, length - IDC_DEPTH)),
         "idc", root, coll)
    return IDC_END, n * PITCH + IDC_END        # extent left and right of wire 1


def _drive(name, n, length, root, coll):
    """40-wire ribbon: IDE end whole, far end split into two 20-wire halves
    folded flat along 45-degree creases into a T: the first half turns to -X,
    the second to +X, both the same length (centre wire = length). Each half
    lands on contacts 10-29 of a 34-pin socket (WIRING.md)."""
    w = n // 2 * PITCH                  # half width
    ys = length - SPLIT_LEN             # creases start here
    xl, xr = w - SPLIT_LEN, w + SPLIT_LEN   # arm ends
    up = RIBBON_T                       # folded arm lies on the lower layer

    def grey(bm):
        _quad(bm, ((PITCH, 0), (w, 0), (w, ys + w), (PITCH, ys + PITCH)), 0)        # half 1
        _quad(bm, ((xl, ys + PITCH), (PITCH, ys + PITCH), (w, ys + w), (xl, ys + w)), up)
        _quad(bm, ((w, 0), (2 * w, 0), (2 * w, ys), (w, ys + w)), 0)                # half 2
        _quad(bm, ((2 * w, ys), (xr, ys), (xr, ys + w), (w, ys + w)), up)

    def red(bm):                        # wire 1 ends on the arm's lower edge
        _quad(bm, ((0, 0), (PITCH, 0), (PITCH, ys + PITCH), (0, ys)), 0)
        _quad(bm, ((xl, ys), (0, ys), (PITCH, ys + PITCH), (xl, ys + PITCH)), up)

    def sockets(bm):
        _socket(bm, 0, n, 0)                                   # 40-pin IDE header end
        y1 = ys - 9 * PITCH - IDC_END                          # wire 1 on contact 10
        _box(bm, xl, y1, 0, xl + IDC_DEPTH, y1 + 34 * PITCH + 2 * IDC_END, IDC_H)
        y2 = ys + w + 9 * PITCH + IDC_END                      # wire 21 on contact 10
        _box(bm, xr - IDC_DEPTH, y2 - 34 * PITCH - 2 * IDC_END, 0, xr, y2, IDC_H)
    _add(f"{name}.ribbon", grey, "ribbon", root, coll)
    _add(f"{name}.red", red, "red", root, coll)
    _add(f"{name}.idc", sockets, "idc", root, coll)
    return max(-xl, IDC_END), xr   # the arms set the width


def _lsm(name, n, length, root, coll):
    for k in range(n):
        x = k * WIRE_D + WIRE_D / 2
        _add(f"{name}.w{k + 1}",
             lambda bm, x=x: _cyl(bm, x, length / 2, WIRE_D / 2, WIRE_D, length, axis="Y", seg=10),
             f"w{k + 1}", root, coll)
    w = n * XH[0] + 2.4                 # [STD] XH housing width for n poles
    c = n * WIRE_D / 2
    _add(f"{name}.xh", lambda bm: _box(bm, c - w / 2, 0, 0, c + w / 2, XH[1], XH[2]), "xh", root, coll)
    return w / 2 - c, c + w / 2


BUILD = {"ribbon": _ribbon, "drive": _drive, "lsm": _lsm}


def build_cables(origin=(0.0, 0.0, 0.0), cables=None, collection=None):
    coll = collection or bpy.context.scene.collection
    roots, x = [], origin[0]
    for name, kind, n, length, note in (CABLES if cables is None else cables):
        root = bpy.data.objects.new(f"cable_{name}", None)
        root.empty_display_size = 0.005
        root["note"] = note
        coll.objects.link(root)
        left, right = BUILD[kind](f"cable_{name}", n, length, root, coll)
        root.location = _v(x + left, origin[1], origin[2])
        x += left + right + GAP
        roots.append(root)
    return roots
