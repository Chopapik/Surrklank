"""Procedural 3.5" floppy disk drive for Blender.

    build_fdd(name, origin=(0, 0, 0), open_top=True, track=40, bezel="beige",
              collection=None) -> parent Empty

origin is the min corner (left-front-bottom) of the body in millimetres. Axes:
X = width (left -> right seen from the front), Y = depth (bezel face at Y = 0),
Z = height (PCB underside at Z = 0). Blender units are metres; every constant
below is in millimetres and converted with MM. The eject button protrudes
BUTTON_PROTRUDE in front of Y = 0 (negative: recessed) and the LED rim 0.35 mm.

Reference: the bezel follows a photo of one of the orchestra's beige PC drives
- a large stepped recess with sloped walls, finger ramp, spring disk door, LED
with a ribbed lens lower left, eject button lower right. The rest is a Teac
FD-235HF-class drive: steel chassis; main PCB on the underside; flat spindle motor; can-stack stepper with
lead screw at the rear; 2x17 pin header, drive-select jumpers and a 4-pin mini
power connector at the rear. No drawing or physical drive was used. Tags:
  [PHOTO]    read from a front photo of an orchestra drive (+-0.5 mm, see Bezel)
  [STD]      published dimension (3.5" form factor, 3.5" disk, track pitch)
  [SFF-8301] 3.5" HDD mounting pattern recalled from memory; FDDs fit the same
             bays, but these positions were not checked on a floppy drive
  [TYP]      typical value for real drives
  [ASSUMED]  estimate for appearance only

Meshes (booleans included) are built once per module load and shared by every
drive, so eight drives cost eight sets of linked objects, not eight rebuilds.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

MM = 0.001

# ---- Envelope -----------------------------------------------------------------
WIDTH = 101.6    # [STD] 4.00 in
HEIGHT = 25.4    # [STD] 1.00 in
DEPTH = 146.0    # [TYP] bezel face to rear pin tips; real drives ~140-150 mm

# ---- Bezel --------------------------------------------------------------------
# [PHOTO] values were read from a front photo of an orchestra drive, scaled from
# the 101.6 mm bezel width (~14.3 px/mm, about +-0.5 mm). Coordinates are (x, z)
# on the face, x from the left edge, z from the bottom.
BEZEL_T = 7.0             # [ASSUMED] bezel depth
BEZEL_R = 1.0             # [ASSUMED] corner radius in the face plane
BEZEL_CHAMFER = 0.5       # [ASSUMED] small chamfer around the face
RECESS_D = 2.5            # [ASSUMED] depth of the large stepped recess
# Large recess with sloped walls: outline on the face and outline of its floor
# (same vertex order). It has a finger ramp below and a shallow lobe above
# the middle of the disk door.                                     [PHOTO]
RECESS_FACE = [(2.45, 11.4), (35.0, 11.4), (35.0, 2.6), (70.4, 2.6), (70.4, 11.4),
               (99.2, 11.4), (99.2, 22.6), (70.4, 22.6), (70.4, 23.9), (35.0, 23.9),
               (35.0, 22.6), (2.45, 22.6)]
RECESS_FLOOR = [(6.5, 13.0), (35.5, 13.0), (35.5, 12.6), (69.9, 12.6), (69.9, 13.0),
                (95.2, 13.0), (95.2, 19.6), (72.0, 19.6), (69.9, 19.65), (35.5, 19.65),
                (33.4, 19.6), (6.5, 19.6)]
# Disk door (spring flap, closed): narrow on the left, full height elsewhere.  [PHOTO]
DOOR = [(6.7, 14.8), (24.5, 14.8), (26.0, 12.8), (80.5, 12.8), (82.0, 13.8),
        (96.0, 13.8), (96.0, 19.4), (26.0, 19.4), (24.5, 18.6), (6.7, 18.6)]
DOOR_PROUD = 0.4          # [ASSUMED] door face in front of the recess floor
DOOR_GAP_Z = (12.3, 12.8)  # [PHOTO] dark gap under the door, x 26..80.5
DOOR_GROOVE = 0.3         # [PHOTO, approx.] dark groove around the door
BUTTON = (73.2, 3.7, 14.7, 5.5)   # [PHOTO] eject button x0, z0, width, height
BUTTON_GAP = 0.25         # [ASSUMED] clearance around the button
BUTTON_PROTRUDE = -0.3    # [PHOTO, approx.] button face 0.3 mm behind the bezel face
LED = (21.4, 4.9, 6.3, 2.1)       # [PHOTO] LED lens x0, z0, width, height
LED_RIM = 0.5             # [PHOTO, approx.] raised rim around the lens
LED_RIBS = 5              # [PHOTO] vertical ribs on the clear lens

# ---- Chassis and PCB ------------------------------------------------------------
STEEL_T = 0.8             # [ASSUMED] sheet thickness
PCB_T = 1.6               # [TYP]
PCB_X0, PCB_X1 = STEEL_T + 0.2, WIDTH - STEEL_T - 0.2   # [ASSUMED] between the side walls
PCB_Y0, PCB_Y1 = BEZEL_T + 2.0, 141.0   # [ASSUMED]
FLOOR_Z0 = 3.0            # [ASSUMED] chassis floor underside (room for PCB parts)
FLOOR_Y1 = 136.0          # [ASSUMED] floor ends before the rear connectors
WALL_Y1 = 140.0           # [ASSUMED]
WALL_Z0 = 0.0             # [ASSUMED] side walls reach the bottom and hide the PCB edge
COVER_T = 0.5             # [ASSUMED]
WALL_TOP = HEIGHT - COVER_T - 0.05  # cover sits on the walls, label on the cover

# ---- Mounting holes (M3) --------------------------------------------------------
HOLE_D = 2.6                          # [ASSUMED] tapped M3 shown at minor diameter
SIDE_HOLE_Z = 6.35                    # [SFF-8301]
SIDE_HOLE_Y = (28.5, 28.5 + 101.6)    # [SFF-8301]
BOTTOM_HOLE_X = (3.18, WIDTH - 3.18)  # [SFF-8301] 95.25 mm apart
BOTTOM_HOLE_Y = (41.28, 41.28 + 44.45)  # [SFF-8301]
PCB_CLEAR_D = 6.0                     # [ASSUMED] PCB cut-out around bottom holes

# ---- Disk and spindle -----------------------------------------------------------
DISK = (90.0, 94.0, 3.3)  # [STD] 3.5" cartridge W x L x T (only used for clearances)
SPINDLE_X = WIDTH / 2     # [ASSUMED] centred under the slot
SPINDLE_Y = 54.0          # [ASSUMED]
ROTOR_D, ROTOR_Z = 44.0, (2.0, 6.8)      # [ASSUMED] flat brushless rotor
TABLE_D, TABLE_Z = 30.0, (6.8, 7.4)      # [ASSUMED] turntable
CHUCK_D, CHUCK_Z = 25.0, (7.4, 10.4)     # [ASSUMED] magnetic chuck
HUB_Z = (10.4, 10.9)                     # [ASSUMED] hub plate
SHAFT_D, SHAFT_Z1 = 3.8, 12.0            # [ASSUMED]
DRIVE_PIN_R, DRIVE_PIN_D, DRIVE_PIN_Z1 = 7.0, 2.2, 11.6  # [ASSUMED]
FLOOR_SPINDLE_HOLE_D = 47.0              # [ASSUMED]

# ---- Head positioner --------------------------------------------------------------
TRACK0_R = 39.5           # [STD] track 0 radius, side 0 (recalled)
TRACK_PITCH = 0.1875      # [STD] 135 tpi
RAIL_Z = 11.5             # [ASSUMED] lead screw / guide rod axis height
SCREW_X, SCREW_D, SCREW_Y = 70.0, 3.0, (80.0, 112.0)    # [ASSUMED]
ROD_X, ROD_D, ROD_Y = 33.0, 2.5, (76.0, 120.0)          # [ASSUMED]
STEPPER_D, STEPPER_Y = 15.0, (112.0, 124.0)             # [ASSUMED] can-stack motor
HOLDER_Z = (17.0, 17.6)   # [ASSUMED] disk holder sheet above the slot

# ---- Rear connectors --------------------------------------------------------------
PIN_PITCH = 2.54          # [STD] 34-pin header
PIN_SQ = 0.64             # [STD] square pin
HEADER_X0 = 20.0          # [ASSUMED] position along the rear edge
HEADER_BODY_Y = (136.5, 139.5)   # [ASSUMED]
POWER_PITCH = 2.5         # [TYP] 4-pin mini (floppy) power connector
POWER_X0, POWER_W, POWER_H, POWER_Y0 = 78.0, 12.0, 6.0, 138.0  # [TYP outline, ASSUMED place]
JUMPER_X0, JUMPER_Y0 = 66.0, 137.0   # [ASSUMED] 2x3 drive-select jumpers

COLORS = {
    "bezel_black": (0.025, 0.025, 0.028, 1), "bezel_beige": (0.70, 0.68, 0.58, 1),
    "button_black": (0.07, 0.07, 0.075, 1), "button_beige": (0.66, 0.64, 0.55, 1),
    "steel": (0.58, 0.60, 0.62, 1), "steel_dark": (0.33, 0.34, 0.36, 1),
    "pcb": (0.03, 0.20, 0.07, 1), "black": (0.012, 0.012, 0.014, 1),
    "gold": (0.85, 0.62, 0.22, 1), "nylon": (0.86, 0.83, 0.72, 1),
    "led": (0.10, 0.75, 0.15, 1), "lens": (0.45, 0.47, 0.45, 1), "rotor": (0.14, 0.14, 0.15, 1),
    "brass": (0.72, 0.55, 0.25, 1), "label": (0.92, 0.92, 0.90, 1),
    "ferrite": (0.22, 0.18, 0.15, 1),
}


# ---- geometry helpers (all inputs in mm) ------------------------------------------
def _v(x, y, z):
    return Vector((x * MM, y * MM, z * MM))


def _box(bm, x0, y0, z0, x1, y1, z1):
    m = Matrix.Translation(_v((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) @ \
        Matrix.Diagonal(((x1 - x0) * MM, (y1 - y0) * MM, (z1 - z0) * MM, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


_AXIS = {"Z": Matrix.Identity(4),
         "X": Matrix.Rotation(math.pi / 2, 4, "Y"),
         "Y": Matrix.Rotation(math.pi / 2, 4, "X")}


def _cyl(bm, cx, cy, cz, d, length, axis="Z", seg=32):
    m = Matrix.Translation(_v(cx, cy, cz)) @ _AXIS[axis]
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=d / 2 * MM, radius2=d / 2 * MM, depth=length * MM, matrix=m)


def _rrect(x0, z0, x1, z1, r, y, seg=4):
    """Rounded rectangle loop in the XZ plane at depth y."""
    pts = []
    for cx, cz, a0 in ((x1 - r, z1 - r, 0), (x0 + r, z1 - r, 90), (x0 + r, z0 + r, 180), (x1 - r, z0 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), y, cz + r * math.sin(a)))
    return pts


def _loft(bm, loops):
    """Closed solid through equal-length loops (first and last capped)."""
    rings = [[bm.verts.new(_v(*p)) for p in loop] for loop in loops]
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))


def _rbox_y(bm, x0, z0, x1, z1, r, y0, y1):
    _loft(bm, [_rrect(x0, z0, x1, z1, r, y0), _rrect(x0, z0, x1, z1, r, y1)])


# ---- part builders ----------------------------------------------------------------
def _face(poly, y):
    return [(x, y, z) for x, z in poly]


def _offset(poly, d):
    """Mitred outward offset of a counter-clockwise (x, z) polygon."""
    out = []
    n = len(poly)
    for i in range(n):
        (ax, az), (bx, bz), (cx, cz) = poly[i - 1], poly[i], poly[(i + 1) % n]
        normals = []
        for (px, pz), (qx, qz) in (((ax, az), (bx, bz)), ((bx, bz), (cx, cz))):
            ex, ez = qx - px, qz - pz
            length = math.hypot(ex, ez)
            normals.append((ez / length, -ex / length))
        (n1x, n1z), (n2x, n2z) = normals
        k = d / (1 + n1x * n2x + n1z * n2z)
        out.append((bx + (n1x + n2x) * k, bz + (n1z + n2z) * k))
    return out


def _bezel(bm):
    c, r = BEZEL_CHAMFER, BEZEL_R
    _loft(bm, [_rrect(c, c, WIDTH - c, HEIGHT - c, max(r - c, 0.2), 0.0),
               _rrect(0, 0, WIDTH, HEIGHT, r, c),
               _rrect(0, 0, WIDTH, HEIGHT, r, BEZEL_T)])


def _bezel_cut(bm):
    _loft(bm, [_face(RECESS_FACE, -0.2), _face(RECESS_FACE, 0.0), _face(RECESS_FLOOR, RECESS_D)])
    bx, bz, bw, bh = BUTTON
    g = BUTTON_GAP
    _rbox_y(bm, bx - g, bz - g, bx + bw + g, bz + bh + g, 0.5, -0.2, BEZEL_T + 0.2)


def _door(bm):
    _loft(bm, [_face(DOOR, RECESS_D - DOOR_PROUD), _face(DOOR, RECESS_D + 0.2)])


def _dark_details(bm):
    z0, z1 = DOOR_GAP_Z
    _box(bm, 26.0, RECESS_D - 0.25, z0, 80.5, RECESS_D - 0.2, z1)     # gap under the door
    groove = _offset(DOOR, DOOR_GROOVE)                                # groove around the door
    _loft(bm, [_face(groove, RECESS_D - 0.1), _face(groove, RECESS_D + 0.1)])
    bx, bz, bw, bh = BUTTON
    _box(bm, bx - 1, BEZEL_T - 0.6, bz - 1, bx + bw + 1, BEZEL_T - 0.1, bz + bh + 1)  # button well
    lx, lz, lw, lh = LED
    for i in range(LED_RIBS):                                          # lens ribs
        x = lx + lw * (i + 0.5) / LED_RIBS
        _box(bm, x - 0.12, -0.37, lz + 0.25, x + 0.12, -0.3, lz + lh - 0.25)


def _button(bm):
    bx, bz, bw, bh = BUTTON
    p = BUTTON_PROTRUDE
    _loft(bm, [_rrect(bx + 0.3, bz + 0.3, bx + bw - 0.3, bz + bh - 0.3, 0.3, -p),
               _rrect(bx, bz, bx + bw, bz + bh, 0.5, -p + 0.3),
               _rrect(bx, bz, bx + bw, bz + bh, 0.5, BEZEL_T - 1.0)])


def _led_rim(bm):
    lx, lz, lw, lh = LED
    r = LED_RIM
    _box(bm, lx - r, -0.3, lz - r, lx + lw + r, 0.2, lz + lh + r)


def _led(bm):
    lx, lz, lw, lh = LED
    _box(bm, lx, -0.35, lz, lx + lw, 0.2, lz + lh)


def _pcb(bm):
    _box(bm, PCB_X0, PCB_Y0, 0, PCB_X1, PCB_Y1, PCB_T)


def _pcb_cut(bm):
    for x in BOTTOM_HOLE_X:
        for y in BOTTOM_HOLE_Y:
            _cyl(bm, x, y, PCB_T / 2, PCB_CLEAR_D, PCB_T + 2, seg=24)


def _floor(bm):
    _box(bm, STEEL_T, BEZEL_T, FLOOR_Z0, WIDTH - STEEL_T, FLOOR_Y1, FLOOR_Z0 + STEEL_T)


def _floor_cut(bm):
    zc = FLOOR_Z0 + STEEL_T / 2
    for x in BOTTOM_HOLE_X:
        for y in BOTTOM_HOLE_Y:
            _cyl(bm, x, y, zc, HOLE_D, 3, seg=20)
    _cyl(bm, SPINDLE_X, SPINDLE_Y, zc, FLOOR_SPINDLE_HOLE_D, 3, seg=64)


def _wall(x0):
    def build(bm):
        _box(bm, x0, BEZEL_T, WALL_Z0, x0 + STEEL_T, WALL_Y1, WALL_TOP)

    def cut(bm):
        for y in SIDE_HOLE_Y:
            _cyl(bm, x0 + STEEL_T / 2, y, SIDE_HOLE_Z, HOLE_D, 3, axis="X", seg=20)
    return build, cut


def _cover(bm):
    _box(bm, 0, BEZEL_T, WALL_TOP, WIDTH, FLOOR_Y1, HEIGHT - 0.05)


def _label(bm):
    _box(bm, 25, 70, HEIGHT - 0.05, 76, 110, HEIGHT)


def _rotor(bm):
    _cyl(bm, SPINDLE_X, SPINDLE_Y, sum(ROTOR_Z) / 2, ROTOR_D, ROTOR_Z[1] - ROTOR_Z[0], seg=64)


def _chuck(bm):
    _cyl(bm, SPINDLE_X, SPINDLE_Y, sum(CHUCK_Z) / 2, CHUCK_D, CHUCK_Z[1] - CHUCK_Z[0], seg=48)


def _spindle_steel(bm):
    x, y = SPINDLE_X, SPINDLE_Y
    _cyl(bm, x, y, sum(TABLE_Z) / 2, TABLE_D, TABLE_Z[1] - TABLE_Z[0], seg=48)
    _cyl(bm, x, y, sum(HUB_Z) / 2, CHUCK_D, HUB_Z[1] - HUB_Z[0], seg=48)
    _cyl(bm, x, y, (HUB_Z[1] + SHAFT_Z1) / 2, SHAFT_D, SHAFT_Z1 - HUB_Z[1], seg=16)
    _cyl(bm, x + DRIVE_PIN_R, y, (HUB_Z[1] + DRIVE_PIN_Z1) / 2, DRIVE_PIN_D,
         DRIVE_PIN_Z1 - HUB_Z[1], seg=12)


def _mech_steel(bm):
    f1 = FLOOR_Z0 + STEEL_T
    # guide rod with end brackets, lead-screw front bearing, stepper flange
    _cyl(bm, ROD_X, sum(ROD_Y) / 2, RAIL_Z, ROD_D, ROD_Y[1] - ROD_Y[0], axis="Y", seg=16)
    for y in (ROD_Y[0], ROD_Y[1] - 4):
        _box(bm, ROD_X - 2, y, f1, ROD_X + 2, y + 4, RAIL_Z + 1.5)
    _box(bm, SCREW_X - 2, SCREW_Y[0] - 3, f1, SCREW_X + 2, SCREW_Y[0], RAIL_Z + 2)
    _box(bm, SCREW_X - 8.5, STEPPER_Y[0] - 0.8, f1, SCREW_X + 8.5, STEPPER_Y[0], RAIL_Z + 8)
    # disk holder: two rails, front bar, four posts down to the floor
    z0, z1 = HOLDER_Z
    for xa, xb in ((2.0, 9.0), (WIDTH - 9.0, WIDTH - 2.0)):
        _box(bm, xa, BEZEL_T + 2, z0, xb, 104, z1)
    _box(bm, 2.0, BEZEL_T + 2, z0, WIDTH - 2.0, BEZEL_T + 6, z1)
    for xa in (2.0, WIDTH - 2.8):
        for y in (20, 90):
            _box(bm, xa, y, f1, xa + 0.8, y + 6, z0)
    # eject slider, its tab and the button stem
    bx, bz, bw, bh = BUTTON
    sx = bx + bw / 2
    _box(bm, sx - 2, BEZEL_T + 2, f1, 96, 88, f1 + 0.6)
    _box(bm, sx - 1, BEZEL_T - 1, bz + 1.5, sx + 1, BEZEL_T + 5, bz + 3)
    _box(bm, sx - 2, BEZEL_T + 3, f1, sx + 1, BEZEL_T + 5, bz + 3)


def _spring(bm):
    _cyl(bm, 93, 103, FLOOR_Z0 + STEEL_T + 1.8, 3.0, 30, axis="Y", seg=12)


def _screw(bm):
    _cyl(bm, SCREW_X, sum(SCREW_Y) / 2, RAIL_Z, SCREW_D, SCREW_Y[1] - SCREW_Y[0], axis="Y", seg=16)


def _stepper(bm):
    _cyl(bm, SCREW_X, sum(STEPPER_Y) / 2, RAIL_Z, STEPPER_D, STEPPER_Y[1] - STEPPER_Y[0], axis="Y", seg=40)


def _sensors(bm):
    f1 = FLOOR_Z0 + STEEL_T
    _box(bm, 6, 96, f1, 12, 102, f1 + 4)        # write-protect switch
    _box(bm, 84, 96, f1, 90, 102, f1 + 4)       # density (HD hole) switch
    for xa in (38, 43):                         # track-0 fork sensor
        _box(bm, xa, 111, f1, xa + 2, 115, 12)


# carriage parts are built around the head centre (y = 0) and placed per track
def _carriage(bm):
    _box(bm, 30, 6, 8.5, 74, 16, 14.5)


def _carriage_steel(bm):
    _box(bm, 47, -2.5, 8.6, 54.6, 7, 9.8)       # lower head arm
    _box(bm, 46, -3, 12.9, 55.6, 14, 13.5)      # upper (load) arm
    _box(bm, 41, 16, 9, 42, 20, 12)             # track-0 flag


def _heads(bm):
    hx = SPINDLE_X
    _box(bm, hx - 1.5, -2, 9.8, hx + 1.5, 2, 11.0)
    _box(bm, hx - 1.5, -2, 11.5, hx + 1.5, 2, 12.9)


def _header_body(bm):
    _box(bm, HEADER_X0, HEADER_BODY_Y[0], PCB_T, HEADER_X0 + 17 * PIN_PITCH, HEADER_BODY_Y[1], PCB_T + 2 * PIN_PITCH)
    _box(bm, JUMPER_X0, JUMPER_Y0, PCB_T, JUMPER_X0 + 3 * PIN_PITCH, JUMPER_Y0 + 2 * PIN_PITCH, PCB_T + 2.5)
    _box(bm, JUMPER_X0 + 0.1, JUMPER_Y0 - 0.1, PCB_T + 2.5,           # jumper cap
         JUMPER_X0 + PIN_PITCH - 0.1, JUMPER_Y0 + 2 * PIN_PITCH + 0.1, PCB_T + 8)


def _pins(bm):
    h = PIN_SQ / 2
    for i in range(17):
        x = HEADER_X0 + PIN_PITCH / 2 + i * PIN_PITCH
        for row in range(2):
            z = PCB_T + PIN_PITCH / 2 + row * PIN_PITCH
            _box(bm, x - h, HEADER_BODY_Y[1], z - h, x + h, DEPTH, z + h)
    for i in range(3):
        for j in range(2):
            x = JUMPER_X0 + PIN_PITCH / 2 + i * PIN_PITCH
            y = JUMPER_Y0 + PIN_PITCH / 2 + j * PIN_PITCH
            _box(bm, x - h, y - h, PCB_T + 2.5, x + h, y + h, PCB_T + 6)
    xc = POWER_X0 + POWER_W / 2
    for k in range(4):
        x = xc + (k - 1.5) * POWER_PITCH
        _box(bm, x - h, POWER_Y0 + 2, PCB_T + POWER_H / 2 - h, x + h, DEPTH - 0.8, PCB_T + POWER_H / 2 + h)


def _power(bm):
    _box(bm, POWER_X0, POWER_Y0, PCB_T, POWER_X0 + POWER_W, DEPTH, PCB_T + POWER_H)


def _power_cut(bm):
    _box(bm, POWER_X0 + 1, POWER_Y0 + 1.5, PCB_T + 1, POWER_X0 + POWER_W - 1, DEPTH + 1, PCB_T + POWER_H - 1)


_WALL_L = _wall(0.0)
_WALL_R = _wall(WIDTH - STEEL_T)

# part name -> (builder, cutter or None, material key, group)
# material "bezel"/"button" are resolved from the bezel colour per drive.
PARTS = {
    "bezel": (_bezel, _bezel_cut, "bezel", "static"),
    "disk_door": (_door, None, "bezel", "static"),
    "bezel_dark": (_dark_details, None, "black", "static"),
    "eject_button": (_button, None, "button", "static"),
    "led_rim": (_led_rim, None, "bezel", "static"),
    "led": (_led, None, "lens", "static"),
    "pcb": (_pcb, _pcb_cut, "pcb", "static"),
    "chassis_floor": (_floor, _floor_cut, "steel", "static"),
    "wall_L": (_WALL_L[0], _WALL_L[1], "steel", "static"),
    "wall_R": (_WALL_R[0], _WALL_R[1], "steel", "static"),
    "top_cover": (_cover, None, "steel", "cover"),
    "cover_label": (_label, None, "label", "cover"),
    "spindle_rotor": (_rotor, None, "rotor", "static"),
    "spindle_chuck": (_chuck, None, "black", "static"),
    "spindle_hub": (_spindle_steel, None, "steel", "static"),
    "mechanism": (_mech_steel, None, "steel", "static"),
    "eject_spring": (_spring, None, "steel_dark", "static"),
    "lead_screw": (_screw, None, "brass", "static"),
    "stepper": (_stepper, None, "steel_dark", "static"),
    "sensors": (_sensors, None, "black", "static"),
    "carriage": (_carriage, None, "black", "carriage"),
    "head_arms": (_carriage_steel, None, "steel", "carriage"),
    "heads": (_heads, None, "ferrite", "carriage"),
    "rear_plastic": (_header_body, None, "black", "static"),
    "rear_pins": (_pins, None, "gold", "static"),
    "power_conn": (_power, _power_cut, "nylon", "static"),
}


# ---- mesh / material cache ------------------------------------------------------------
_MESHES = {}


def _material(key):
    name = "fdd_" + key
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = COLORS[key]
        mat.roughness = 0.5
        try:
            mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = COLORS[key]
        except Exception:
            pass
    return mat


def _boolean(bm, cut_bm, name):
    """bm minus cut_bm, evaluated once through a temporary Boolean modifier."""
    a_me, b_me = bpy.data.meshes.new(name + "_tmp_a"), bpy.data.meshes.new(name + "_tmp_b")
    bm.to_mesh(a_me)
    cut_bm.to_mesh(b_me)
    a, b = bpy.data.objects.new(a_me.name, a_me), bpy.data.objects.new(b_me.name, b_me)
    coll = bpy.context.scene.collection
    coll.objects.link(a)
    coll.objects.link(b)
    mod = a.modifiers.new("cut", "BOOLEAN")
    mod.operation, mod.object, mod.solver = "DIFFERENCE", b, "EXACT"
    dg = bpy.context.evaluated_depsgraph_get()
    result = bpy.data.meshes.new_from_object(a.evaluated_get(dg))
    for o in (a, b):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.meshes.remove(a_me)
    bpy.data.meshes.remove(b_me)
    result.name = name
    return result


def _mesh(part):
    me = _MESHES.get(part)
    if me is not None:
        try:
            me.name  # raises ReferenceError if the mesh was deleted
            return me
        except ReferenceError:
            pass
    build, cut, _, _ = PARTS[part]
    bm = bmesh.new()
    build(bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if cut is None:
        me = bpy.data.meshes.new("fdd_" + part)
        bm.to_mesh(me)
    else:
        cbm = bmesh.new()
        cut(cbm)
        bmesh.ops.recalc_face_normals(cbm, faces=cbm.faces[:])
        me = _boolean(bm, cbm, "fdd_" + part)
        cbm.free()
    bm.free()
    me.materials.clear()
    me.materials.append(None)
    me.polygons.foreach_set("material_index", [0] * len(me.polygons))
    try:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(30))
    except Exception:
        pass
    _MESHES[part] = me
    return me


def build_fdd(name, origin=(0.0, 0.0, 0.0), open_top=True, track=40, bezel="beige", collection=None):
    """Create one drive and return its parent Empty (origin in mm, min corner).

    track: 0..79 positions the head carriage; bezel: "black" or "beige".
    """
    coll = collection or bpy.context.scene.collection
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.01
    root.location = _v(*origin)
    coll.objects.link(root)
    head_y = SPINDLE_Y + TRACK0_R - track * TRACK_PITCH
    for part, (_, _, mat_key, group) in PARTS.items():
        if group == "cover" and open_top:
            continue
        obj = bpy.data.objects.new(f"{name}.{part}", _mesh(part))
        coll.objects.link(obj)
        obj.parent = root
        if group == "carriage":
            obj.location.y = head_y * MM
        if mat_key in ("bezel", "button"):
            mat_key = f"{mat_key}_{bezel}"
        slot = obj.material_slots[0]
        slot.link = "OBJECT"
        slot.material = _material(mat_key)
    return root
