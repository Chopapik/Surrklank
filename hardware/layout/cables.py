"""Draw the routed cables from harness.py in Blender.

    build_cables(cables, collection=None) -> [Empty]

A ribbon is swept along its route as flat boxes: a turn towards its own
width is drawn as a flat 45-degree fold (the two runs overlap in a square),
other turns as bends, a twist as short rotated pieces. Wire 1 is the red
stripe. IDC sockets sit on both ends, JST-XH housings on the LSM leads at the
actuator. The unused length of every cable is one folded pack on its longest
straight run (ribbon: flat accordion folds; LSM lead: a bundle). The LED
board of WIRING.md is a placeholder perfboard.
"""
import math

import bpy
import bmesh

from fdd_model import _v
import harness as H

RIBBON_T = 0.9           # [TYP]
IDC_DEPTH, IDC_H = 6.0, 9.6      # [TYP] socket body across the ribbon and its height
IDC_END = 2.55           # [TYP] body beyond the outer contacts
XH = (2.5, 5.75, 9.0)    # [STD] JST-XH pitch and housing depth; plugged height [ASSUMED]
PACK_LEN = 60.0          # longest fold of a slack pack
TWIST_STEPS = 32
BEND_R = 4.0             # [ASSUMED] inside radius of a ribbon bend

COLORS = {
    "ribbon": (0.72, 0.72, 0.70, 1), "pack": (0.6, 0.6, 0.58, 1),
    "red": (0.7, 0.05, 0.05, 1), "idc": (0.04, 0.04, 0.04, 1), "crease": (0.3, 0.3, 0.3, 1),
    "xh": (0.92, 0.9, 0.85, 1), "perf": (0.75, 0.6, 0.35, 1), "dip": (0.05, 0.05, 0.05, 1),
    "led": (0.9, 0.15, 0.1, 1),
    # [ASSUMED] LSM lead colours, wire 1 first
    "w1": (0.7, 0.05, 0.05, 1), "w2": (0.05, 0.15, 0.7, 1),
    "w3": (0.05, 0.5, 0.1, 1), "w4": (0.04, 0.04, 0.04, 1),
}


def _material(key):
    name = "cable_" + key
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = COLORS[key]
    return m


class _Mesh:
    """Collects oriented boxes per colour, one object per colour."""

    def __init__(self):
        self.bms = {}

    def box(self, key, c, ax, half):
        """Box centred at c with unit axes ax[0..2] and half sizes half[0..2]."""
        bm = self.bms.setdefault(key, bmesh.new())
        vs = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    p = c
                    for a, h, s in zip(ax, half, (sx, sy, sz)):
                        p = H.add(p, H.mul(a, h * s))
                    vs.append(bm.verts.new(_v(*p)))
        for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
            bm.faces.new([vs[i] for i in f])

    def prism(self, key, bot, top):
        """Solid between two matching convex polygons."""
        bm = self.bms.setdefault(key, bmesh.new())
        vb = [bm.verts.new(_v(*p)) for p in bot]
        vt = [bm.verts.new(_v(*p)) for p in top]
        bm.faces.new(vb[::-1])
        bm.faces.new(vt)
        k = len(vb)
        for i in range(k):
            j = (i + 1) % k
            bm.faces.new((vb[i], vb[j], vt[j], vt[i]))

    def link(self, name, root, coll):
        for key, bm in self.bms.items():
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            me = bpy.data.meshes.new(f"{name}.{key}")
            bm.to_mesh(me)
            bm.free()
            me.materials.append(_material(key))
            o = bpy.data.objects.new(f"{name}.{key}", me)
            coll.objects.link(o)
            o.parent = root


def _side(n):
    """Normal with a positive dominant component (stable stacking offset)."""
    k = max(range(3), key=lambda i: abs(n[i]))
    return n if n[k] > 0 else H.mul(n, -1)


def _segments(pts, ws, twist, fold0=None, roof=False):
    """Split a route into drawable pieces: (a, b, w at a, w at b, start, end)
    where start/end is None, ("fold", sigma) or "roof". A fold turns the
    strip by 90 degrees over a 45-degree crease; sigma = +1 when it turns
    towards its last wire. Bends become arcs of radius BEND_R, a twist
    becomes TWIST_STEPS pieces whose ends rotate continuously."""
    n = len(pts) - 1
    ds = [H.unit(H.sub(pts[i + 1], pts[i])) for i in range(n)]
    w_e = [H.rotate(ws[i], ds[i], twist[1]) if twist and twist[0] == i else ws[i] for i in range(n)]
    joint = [fold0] + [("fold", round(H.dot(ds[i], w_e[i - 1])))
                       if abs(H.dot(ds[i], w_e[i - 1])) > 0.99 else "bend" for i in range(1, n)]
    a = [pts[i] for i in range(n)]
    b = [pts[i + 1] for i in range(n)]
    arcs = {}
    for i in range(1, n):                       # trim straight runs for the bend arcs
        if joint[i] != "bend":
            continue
        th = math.acos(max(-1.0, min(1.0, H.dot(ds[i - 1], ds[i]))))
        if th < 1e-3:
            continue
        lt = min(BEND_R * math.tan(th / 2), 0.45 * H.norm(H.sub(b[i - 1], a[i - 1])),
                 0.45 * H.norm(H.sub(b[i], a[i])))
        r = lt / math.tan(th / 2)
        p0 = H.sub(pts[i], H.mul(ds[i - 1], lt))
        b[i - 1], a[i] = p0, H.add(pts[i], H.mul(ds[i], lt))
        axis = H.unit(H.cross(ds[i - 1], ds[i]))
        u = H.unit(H.cross(axis, ds[i - 1]))
        c = H.add(p0, H.mul(u, r))
        k = max(2, int(math.degrees(th) / 15))
        arcs[i] = [H.sub(c, H.mul(H.rotate(u, axis, th * j / k), r)) for j in range(k + 1)]
    out = []
    for i in range(n):
        if i in arcs:
            q = arcs[i]
            out += [(q[j], q[j + 1], w_e[i - 1], w_e[i - 1], None, None) for j in range(len(q) - 1)]
        start = joint[i] if joint[i] != "bend" else None
        end = (joint[i + 1] if i + 1 < n and joint[i + 1] != "bend" else None) if i + 1 < n else \
            ("roof" if roof else None)
        steps = TWIST_STEPS if twist and twist[0] == i else 1
        for j in range(steps):
            pa = H.add(a[i], H.mul(H.sub(b[i], a[i]), j / steps))
            pb = H.add(a[i], H.mul(H.sub(b[i], a[i]), (j + 1) / steps))
            wa = H.rotate(ws[i], ds[i], twist[1] * j / steps) if steps > 1 else ws[i]
            wb = H.rotate(ws[i], ds[i], twist[1] * (j + 1) / steps) if steps > 1 else w_e[i]
            out.append((pa, pb, wa, wb, start if j == 0 else None, end if j == steps - 1 else None))
    return out


def _edge_t(joint, s, width, at_end):
    """Offset along the run of the strip edge at s (from the centre line) at
    a joint: on the 45-degree crease of a fold, on the two creases of a T."""
    if joint == "roof":
        return width / 4 - abs(s)
    if joint:
        return -joint[1] * s if at_end else joint[1] * s
    return 0.0


def _sweep(m, pts, ws, twist, width, stripes, t=RIBBON_T, fold0=None, roof=False, layer=0):
    """Flat strip along pts. stripes: (colour, offset from the wire-1 edge,
    width). Runs after an odd number of folds lie one thickness higher, as
    the folded-over layer does."""
    for a, b, wa, wb, start, end in _segments(pts, ws, twist, fold0, roof):
        if start and start != "roof":
            layer += 1
        d = H.unit(H.sub(b, a))
        na, nb = _side(H.cross(d, wa)), _side(H.cross(d, wb))
        lift = (layer % 2) * t * 1.1
        for key, off, sw in stripes:
            s0, s1 = off - width / 2, off + sw - width / 2
            ss = [s0, s1] if not (end == "roof" and s0 < 0 < s1) else [s0, 0.0, s1]
            th = t / 2 + (0.05 if key != "ribbon" else 0.0)
            bot, top = [], []
            for p, w, nn, joint, at_end, seq in ((a, wa, na, start, False, ss), (b, wb, nb, end, True, ss[::-1])):
                for sv in seq:
                    q = H.add(H.add(p, H.mul(w, sv)), H.mul(d, _edge_t(joint, sv, width, at_end)))
                    q = H.add(q, H.mul(nn, lift))
                    bot.append(H.sub(q, H.mul(nn, th)))
                    top.append(H.add(q, H.mul(nn, th)))
            m.prism(key, bot, top)
        if start and start != "roof":           # crease line on the folded-over layer
            c = H.add(a, H.mul(na, lift + t / 2 + 0.05))
            cr = H.unit(H.add(wa, H.mul(d, start[1])))
            m.box("crease", c, (cr, H.cross(na, cr), na), (width * 0.7071, 0.35, 0.06))


def _socket(m, end, width):
    w, plug = end["w"], end["plug"]
    across = H.cross(plug, w)
    if end["kind"] == "jst":
        c = H.add(end["p"], H.mul(plug, XH[2] / 2))
        m.box("xh", c, (w, across, plug), ((4 * XH[0] + 2.4) / 2, XH[1] / 2, XH[2] / 2))
    elif end["kind"] == "idc":
        contacts = end.get("contacts", end["n"])
        lo = -width / 2 - end["first"] * H.PITCH - IDC_END
        hi = lo + contacts * H.PITCH + 2 * IDC_END
        c = H.add(H.add(end["p"], H.mul(w, (lo + hi) / 2)), H.mul(plug, IDC_H / 2))
        m.box("idc", c, (w, across, plug), ((hi - lo) / 2, IDC_DEPTH / 2, IDC_H / 2))


def _pack(m, pts, ws, twist, width, slack, key, t):
    """Folded slack on the longest untwisted straight run."""
    if slack < 5:
        return
    segs = [(H.norm(H.sub(pts[i + 1], pts[i])), i) for i in range(len(pts) - 1)
            if not (twist and twist[0] == i)]
    seg, i = max(segs)
    a = min(PACK_LEN, max(seg - width, 10.0))
    k = math.ceil(slack / (2 * a))
    a = slack / (2 * k)
    d, w = H.unit(H.sub(pts[i + 1], pts[i])), ws[i]
    n = _side(H.cross(d, w))
    h = 2 * k * (t + 0.3)
    c = H.add(H.mul(H.add(pts[i], pts[i + 1]), 0.5), H.mul(n, t * 1.6 + h / 2))
    m.box(key, c, (d, w, n), (a / 2, width / 2, h / 2))


def _led_board(m):
    (x, y, z), (sx, sy, sz) = H.LED_BOARD["min"], H.LED_BOARD["size"]
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    m.box("perf", (x + sx / 2, y + sy / 2, z + sz / 2), (X, Y, Z), (sx / 2, sy / 2, sz / 2))
    for k in range(2):                                   # 74HC595, DIP-16
        m.box("dip", (x + 22 + k * 26, y + 25, z + sz + 2), (X, Y, Z), (10.2, 3.3, 2))
    for k in range(8):                                   # LEDs along the front edge
        m.box("led", (x + 8 + k * 7.5, y + 6, z + sz + 3), (X, Y, Z), (1.5, 1.5, 3))
    ix, iy = H.LED_BOARD["in"]                           # 2x8 box header
    m.box("idc", (ix, iy, z + sz + 3), (X, Y, Z), (12.7, 4.4, 3))


def build_cables(cables, collection=None):
    coll = collection or bpy.context.scene.collection
    roots = []
    for cab in cables:
        root = bpy.data.objects.new(f"cable_{cab['name']}", None)
        root.empty_display_size = 0.005
        root["note"] = cab["note"]
        root["slack_mm"] = round(cab["slack"], 1)
        coll.objects.link(root)
        m = _Mesh()
        lead = cab["kind"] == "lead"
        n = cab["n"]
        t = H.WIRE_D if lead else RIBBON_T
        width = n * (H.WIRE_D if lead else H.PITCH)
        if lead:
            stripes = [(f"w{k + 1}", k * H.WIRE_D, H.WIRE_D) for k in range(n)]
        else:
            stripes = [("ribbon", 0.0, width), ("red", 0.0, H.PITCH)]
        stem, ws, tw = cab["paths"][0], cab["ws"][0], cab["twists"][0]
        drive = cab["kind"] == "drive"
        _sweep(m, stem, ws, tw, width, stripes, t, roof=drive)
        _pack(m, stem, ws, tw, width, cab["slack"], "w4" if lead else "pack", t)
        _socket(m, cab["ends"][0], width)
        if drive:
            for arm, aws, atw, end in zip(cab["paths"][1:], cab["ws"][1:], cab["twists"][1:], cab["ends"][1:]):
                sigma = round(H.dot(H.unit(H.sub(arm[1], arm[0])), ws[-1]))   # -1: wires 1-20
                half = width / 2
                arm = [H.add(arm[0], H.mul(ws[-1], sigma * width / 4)), *arm[1:]]
                st = [("ribbon", 0.0, half)] + ([("red", 0.0, H.PITCH)] if sigma < 0 else [])
                _sweep(m, arm, aws, atw, half, st, t, fold0=("fold", sigma))
                _socket(m, end, half)
        else:
            _socket(m, cab["ends"][1], width)
        m.link(f"cable_{cab['name']}", root, coll)
        roots.append(root)
    m = _Mesh()
    _led_board(m)
    root = bpy.data.objects.new("led_board", None)
    coll.objects.link(root)
    m.link("led_board", root, coll)
    return roots
