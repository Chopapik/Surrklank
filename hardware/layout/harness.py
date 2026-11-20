"""Board placement and cable routes for the Surrklank stack (pure Python).

    plan(geo) -> (placements, cables)

geo comes from layout.py: drive origins per row, the VCR cover origin and the
stepper and wall-hole positions. All values are millimetres in the layout
frame (X right, Y away from the viewer, Z up, origin at the table's
left-front corner).

Placement is (board, min_corner, axes): axes maps the board's local X, Y and
Z (Z = component side) to layout axes, e.g. ("-X", "-Y", "+Z") turns a board
180 degrees, ("-Y", "+Z", "-X") stands it on edge facing -X. Local board
coordinates follow KiCad with Y flipped: origin at the left-front-bottom
corner of the board's bounding box, board top at Z = 3.

Every cable keeps its stock length: a route may be shorter, never longer;
the rest is folded flat (ribbons) or bundled (LSM leads) in one pack. A route
whose wire 1 would arrive on the wrong side gets a twist on its longest
straight run. Tags as in the other modules; [PLAN] marks a proposed position.
"""
import math

IDE_LEN = 370.0         # [MEAS] recycled 40-wire IDE ribbon, about +-40 mm
LSM_LEN = 440.0         # [MEAS] 4-wire LSM lead, about +-40 mm
PITCH = 1.27            # [STD] ribbon pitch
WIRE_D = 1.4            # [TYP] LSM lead wire
SOCKET_TOP = 15.5       # [ASSUMED] ribbon face of a plugged IDC socket above the board bottom
JST_TOP = 15.0          # [ASSUMED] top of a plugged JST-XH housing above the board bottom
LIFT = 2.5              # one ribbon crossing over another socket or ribbon

# board stem: (size x, y, z) of the exported GLB bounding box [MEAS from the export]
BOARDS = {
    "surrklank-fdd-module": (100.0, 80.0, 12.1),
    "surrklank-mainboard": (100.0, 80.0, 13.0),
    "surrklank-actuator-module": (120.0, 80.0, 13.0),
    "surrklank-panel": (100.0, 59.0, 13.0),
}
# connectors from the .kicad_pcb files: local ribbon-face centre (x, y),
# wire-1-to-last direction in board coordinates, wire count
CONN = {
    "surrklank-fdd-module": {
        "IN": ((7.27, 51.11), "-Y", 16), "OUT": ((92.77, 51.11), "-Y", 16),
        "IDE1": ((49.13, 7.27), "+X", 40), "IDE2": ((49.13, 20.27), "+X", 40)},
    "surrklank-mainboard": {
        "FDD": ((92.27, 63.11), "-Y", 16), "ACT": ((92.27, 31.11), "-Y", 16),
        "PANEL": ((63.08, 74.77), "+X", 10)},
    "surrklank-actuator-module": {
        "IN": ((7.27, 52.61), "-Y", 16), "OUT": ((112.77, 51.11), "-Y", 16),
        "M1": ((35.85, 5.5), "+X", 4), "M2": ((55.35, 5.5), "+X", 4),
        "M3": ((74.85, 5.5), "+X", 4), "M4": ((94.35, 5.5), "+X", 4)},
    "surrklank-panel": {"IN": ((21.72, 53.77), "+X", 10)},
}
FLAT = ("+X", "+Y", "+Z")
TURN = ("-X", "-Y", "+Z")
# [PLAN] FDD modules sit centred on the rows (x = 208.5 - 49.1), so every
# drive cable runs straight back from the middle of its row
PLACEMENTS = {
    "fdd_a": ("surrklank-fdd-module", (159.4, 230.0, 0.0), FLAT),    # floor, under trays B/C
    "fdd_b": ("surrklank-fdd-module", (159.4, 417.0, 40.0), FLAT),   # cavity under the shelf
    "fdd_c": ("surrklank-fdd-module", (159.4, 417.0, 100.0), FLAT),
    "mainboard": ("surrklank-mainboard", (357.0, 401.0, 25.0), ("-Y", "+Z", "-X")),  # on ATX 2
    "actuator": ("surrklank-actuator-module", (167.5, 445.0, 160.0), TURN),  # in the VCR cover
    "panel": ("surrklank-panel", (448.3, 234.0, 0.0), FLAT),          # right of the frame
}
# [PLAN] proposed LED perfboard (WIRING.md), drawn as a placeholder
LED_BOARD = {"min": (60.0, 405.0, 160.0), "size": (70.0, 50.0, 1.6),
             "in": (95.0, 450.0), "w": "-X"}

AX = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0),
      "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


# ---- vectors -----------------------------------------------------------------
def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, k): return tuple(x * k for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def unit(a): return mul(a, 1.0 / norm(a))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def rotate(v, axis, ang):
    """Rodrigues rotation of v about the unit axis."""
    c, s = math.cos(ang), math.sin(ang)
    return add(add(mul(v, c), mul(cross(axis, v), s)), mul(axis, dot(axis, v) * (1 - c)))


# ---- boards ------------------------------------------------------------------
def board_frame(inst):
    """(origin, axes vectors) mapping local board mm to the layout."""
    board, mn, axes = PLACEMENTS[inst]
    size = BOARDS[board]
    a = [AX[s] for s in axes]
    corners = [add(add(mul(a[0], cx), mul(a[1], cy)), mul(a[2], cz))
               for cx in (0, size[0]) for cy in (0, size[1]) for cz in (0, size[2])]
    lo = tuple(min(c[k] for c in corners) for k in range(3))
    return sub(mn, lo), a


def to_layout(inst, local):
    o, a = board_frame(inst)
    return add(o, add(add(mul(a[0], local[0]), mul(a[1], local[1])), mul(a[2], local[2])))


def to_layout_dir(inst, local_axis):
    _, a = board_frame(inst)
    v = AX[local_axis]
    return tuple(sum(v[i] * a[i][k] for i in range(3)) for k in range(3))


def conn(inst, ref):
    """Endpoint of a connector: ribbon-face centre, wire direction, plug
    direction (into the board) and wire count."""
    board = PLACEMENTS[inst][0]
    (x, y), w, n = CONN[board][ref]
    top = JST_TOP if ref.startswith("M") and board.endswith("actuator-module") else SOCKET_TOP
    return {"p": to_layout(inst, (x, y, top)), "w": to_layout_dir(inst, w),
            "plug": to_layout_dir(inst, "-Z"), "n": n, "first": 0,
            "kind": "jst" if top == JST_TOP else "idc"}


def drive_end(origin):
    """34-pin socket on the drive's rear header; the half lands on contacts
    10-29 (WIRING.md). Pin 1 is at the header's left end [ASSUMED]."""
    x0, y0, z0 = origin
    return {"p": (x0 + 44.13, y0 + 149.1, z0 + 4.14), "w": (1, 0, 0), "plug": (0, -1, 0),
            "n": 20, "contacts": 34, "first": 9, "kind": "idc"}


# ---- routes ------------------------------------------------------------------
def frames(points, w0, w_end=None, d_prev=None):
    """Wire-1-to-last direction per segment. A turn towards the ribbon's own
    width is a flat 45-degree fold; any other turn is a bend. d_prev is the
    direction arriving at points[0] (a T arm continues its stem). If w_end is
    given and not met, the longest segment gets a twist. Returns (ws, twist)
    with twist = (segment index, angle) or None."""
    def turn(w, dp, d):
        if abs(dot(d, w)) > 0.99:
            return mul(dp, -dot(d, w))          # fold
        return unit(sub(w, mul(d, dot(w, d))))  # bend

    def run(twist):
        ws, w, dp = [], w0, d_prev
        for i in range(len(points) - 1):
            d = unit(sub(points[i + 1], points[i]))
            w = turn(w, dp, d) if dp is not None else unit(sub(w, mul(d, dot(w, d))))
            ws.append(w)
            if twist and twist[0] == i:
                w = rotate(w, d, twist[1])
            dp = d
        return ws

    ws = run(None)
    if w_end is None or dot(ws[-1], w_end) > 0.99:
        return ws, None
    segs = [norm(sub(points[i + 1], points[i])) for i in range(len(points) - 1)]
    k = max(range(len(segs)), key=lambda i: segs[i])
    for ang in (math.pi, math.pi / 2, -math.pi / 2):
        ws2 = run((k, ang))
        if dot(ws2[-1], w_end) > 0.99:
            return ws2, (k, ang)
    return ws, None


def clean(points):
    """Drop repeated points (zero-length segments)."""
    out = [points[0]]
    for q in points[1:]:
        if norm(sub(q, out[-1])) > 1e-6:
            out.append(q)
    return out


def path_len(points):
    return sum(norm(sub(points[i + 1], points[i])) for i in range(len(points) - 1))


def ribbon(name, n, length, a, b, mids, note, lead=False):
    pts = clean([a["p"], *mids, b["p"]])
    return {"name": name, "kind": "lead" if lead else "ribbon", "n": n, "length": length,
            "ends": [a, b], "paths": [pts], "note": note}


def drive_cable(name, module, header, origins, pair, y_t=None, z_t=None, plane_y=None):
    """40-wire ribbon from an FDD module header to two drives of one row.
    pair = indices of the two drives (first gets wires 1-20). Rows A and B
    use a horizontal T at y_t; row C a vertical T in the plane plane_y at z_t."""
    s = conn(module, header)
    e = [drive_end(origins[i]) for i in pair]
    p, xc = s["p"], (e[0]["p"][0] + e[1]["p"][0]) / 2
    z_run = p[2] + (LIFT if header == "IDE2" else 0.0)
    stem = [p]
    if z_run != p[2]:
        stem += [(p[0], p[1] - 4.0, p[2]), (p[0], p[1] - 4.0, z_run)]
    if plane_y is None:                         # horizontal T
        stem += [(xc, y_t, z_run)]
        arms = [[stem[-1], (q["p"][0], y_t, z_run), (q["p"][0], q["p"][1], z_run), q["p"]]
                for q in e]
    else:                                       # vertical T in front of row C
        stem += [(xc, plane_y, z_run), (xc, plane_y, z_t)]
        arms = [[stem[-1], (q["p"][0], plane_y, z_t), (q["p"][0], plane_y, q["p"][2] - 8.0),
                 (q["p"][0], q["p"][1], q["p"][2] - 8.0), q["p"]] for q in e]
    return {"name": name, "kind": "drive", "n": 40, "length": IDE_LEN, "ends": [s, *e],
            "paths": [clean(stem), *[clean(a) for a in arms]], "note": f"{module} {header} -> drives {pair[0] + 1} and {pair[1] + 1}"}


def plan(geo):
    """Return the placements and the routed cables."""
    rows = geo["rows"]
    c = []
    # drive cables: inner pair (2, 3) and outer pair (1, 4) share the row's
    # centre line; the T arms are 50.8 and 152.4 mm long
    c.append(drive_cable("drive_a_outer", "fdd_a", "IDE1", rows["a"], (0, 3), y_t=185.0))
    c.append(drive_cable("drive_a_inner", "fdd_a", "IDE2", rows["a"], (1, 2), y_t=185.0))
    c.append(drive_cable("drive_b_outer", "fdd_b", "IDE1", rows["b"], (0, 3), y_t=295.0))
    c.append(drive_cable("drive_b_inner", "fdd_b", "IDE2", rows["b"], (1, 2), y_t=290.0))
    c.append(drive_cable("drive_c_outer", "fdd_c", "IDE1", rows["c"], (0, 3), z_t=92.0, plane_y=369.6))
    c.append(drive_cable("drive_c_inner", "fdd_c", "IDE2", rows["c"], (1, 2), z_t=105.0, plane_y=368.1))

    # FDD branch: mainboard -> C -> B -> A, every hop over the next board
    mb_fdd, c_in, c_out = conn("mainboard", "FDD"), conn("fdd_c", "IN"), conn("fdd_c", "OUT")
    b_in, b_out, a_in = conn("fdd_b", "IN"), conn("fdd_b", "OUT"), conn("fdd_a", "IN")
    zc = c_in["p"][2] + 2 * LIFT
    c.append(ribbon("ribbon_mainboard_fdd_c", 16, IDE_LEN, mb_fdd, c_in, [
        (mb_fdd["p"][0], c_in["p"][1], mb_fdd["p"][2]), (mb_fdd["p"][0], c_in["p"][1], zc),
        (c_in["p"][0], c_in["p"][1], zc)], "mainboard J2 -> FDD module C IN"))
    xg = 262.0                                  # gap right of the module stack
    zb = b_in["p"][2] + LIFT
    c.append(ribbon("ribbon_fdd_c_b", 16, IDE_LEN, c_out, b_in, [
        (xg, c_out["p"][1], c_out["p"][2]), (xg, c_out["p"][1], zb), (b_in["p"][0], b_in["p"][1], zb)],
        "FDD module C OUT -> B IN"))
    za = 33.0                                   # over the rear stretcher (30 mm)
    c.append(ribbon("ribbon_fdd_b_a", 16, IDE_LEN, b_out, a_in, [
        (xg, b_out["p"][1], b_out["p"][2]), (xg, 335.0, b_out["p"][2]), (xg, 335.0, za),
        (xg, a_in["p"][1], za), (a_in["p"][0], a_in["p"][1], za)], "FDD module B OUT -> A IN"))

    # actuator branch: out of the cavity, up in front of the shelf, into the cover
    mb_act, act_in, act_out = conn("mainboard", "ACT"), conn("actuator", "IN"), conn("actuator", "OUT")
    p = mb_act["p"]
    zt = act_in["p"][2] + 4.5
    c.append(ribbon("ribbon_mainboard_act", 16, IDE_LEN, mb_act, act_in, [
        (p[0], 390.0, p[2]), (p[0], 390.0, zt), (p[0], act_in["p"][1], zt),
        (act_in["p"][0], act_in["p"][1], zt)], "mainboard J3 -> actuator IN"))
    led = {"p": (*LED_BOARD["in"], LED_BOARD["min"][2] + SOCKET_TOP), "w": AX[LED_BOARD["w"]],
           "plug": (0, 0, -1), "n": 16, "first": 0, "kind": "idc"}
    q = act_out["p"]
    c.append(ribbon("ribbon_act_leds", 16, IDE_LEN, act_out, led, [
        (led["p"][0], q[1], q[2] + LIFT), (led["p"][0], led["p"][1], q[2] + LIFT)],
        "actuator OUT -> LED board (proposed)"))

    # panel: down the mainboard, along the gap behind row C, out to the right
    mb_pan, pan = conn("mainboard", "PANEL"), conn("panel", "IN")
    p, zp = mb_pan["p"], 40.0
    c.append(ribbon("ribbon_panel", 10, IDE_LEN, mb_pan, pan, [
        (p[0], p[1], zp), (p[0], 380.0, zp), (pan["p"][0], 380.0, zp), (pan["p"][0], pan["p"][1], zp)],
        "mainboard J6 -> panel J1"))

    # LSM leads: down outside the cover wall, through its foot hole, to a slot
    z_over = 185.0                              # above the actuator board and plugs
    for name, slot, (motor, hole, inner_x) in zip(("lsm1", "lsm2", "lsm3", "lsm4"),
                                                ("M4", "M3", "M2", "M1"), geo["leads"]):
        e = conn("actuator", slot)
        e["n"] = 4
        s = {"p": motor, "w": (1, 0, 0), "plug": (0, 0, 1), "n": 4, "first": 0, "kind": "none"}
        mids = [(motor[0], motor[1], hole[2]), (motor[0], hole[1], hole[2]), (inner_x, hole[1], hole[2]),
                (inner_x, hole[1], z_over), (e["p"][0], e["p"][1], z_over)]
        c.append(ribbon(name, 4, LSM_LEN, s, e, mids, f"{name} -> actuator {slot}", lead=True))
    return c


def _arms(cab, stem, stem_ws):
    d = unit(sub(stem[-1], stem[-2]))
    return [frames(arm, stem_ws[-1], end["w"], d) for arm, end in zip(cab["paths"][1:], cab["ends"][1:])]


def finish(cables):
    """Lengths, slack, twists; raises if a route is longer than its cable."""
    for cab in cables:
        if cab["kind"] == "drive":
            stem = path_len(cab["paths"][0])
            used = stem + max(path_len(a) for a in cab["paths"][1:])
        else:
            used = path_len(cab["paths"][0])
        cab["used"], cab["slack"] = used, cab["length"] - used
        if cab["slack"] < 0:
            raise ValueError(f"{cab['name']}: route {used:.0f} mm > cable {cab['length']:.0f} mm")
        a = cab["ends"][0]
        w_end = cab["ends"][1]["w"] if cab["kind"] == "ribbon" else None
        stem = cab["paths"][0]
        stem_ws, tw = frames(stem, a["w"], w_end)
        twists = [tw]
        if cab["kind"] == "drive":
            arms = _arms(cab, stem, stem_ws)
            if all(t and abs(t[1]) > 3 for _, t in arms):   # both halves flipped:
                segs = [norm(sub(stem[i + 1], stem[i])) for i in range(len(stem) - 1)]
                k = max(range(len(segs)), key=lambda i: segs[i])
                flipped = frames(stem, a["w"])[0]           # twist the stem once instead
                stem_ws = flipped[:k] + [flipped[k]] + [mul(w, -1) for w in flipped[k + 1:]]
                twists = [(k, math.pi)]
                arms = _arms(cab, stem, stem_ws)
            cab["ws"] = [stem_ws, *[ws for ws, _ in arms]]
            cab["twists"] = twists + [t for _, t in arms]
        else:
            cab["ws"], cab["twists"] = [stem_ws], twists
    return cables


def report(cables):
    lines = [f"{'cable':24s} {'length':>6s} {'route':>6s} {'slack':>6s}  twist  note"]
    for c in cables:
        tw = "yes" if any(c["twists"]) else "-"
        lines.append(f"{c['name']:24s} {c['length']:6.0f} {c['used']:6.0f} {c['slack']:6.0f}  {tw:5s}  {c['note']}")
    return "\n".join(lines)
