"""Small helpers that write KiCad 10 schematics from Python.

Symbols are copied from the KiCad standard libraries installed with KiCad and
embedded in the schematic. Nets are made with short wire stubs ending in local
labels or power symbols, so connectivity does not depend on drawing long wires.
"""
import copy
import math
import os
import re
import uuid

LIBDIR = os.environ.get(
    "KICAD_SYMBOL_DIR", "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
)
SCH_VERSION = 20260306
POWER_NETS = {"GND", "+3V3", "+5V", "+5VSB"}
# Screen direction of a pin pointing from its connection point toward the body.
DIR = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}


class Q(str):
    """Quoted S-expression string (raw contents, escapes preserved)."""


def parse(text):
    stack = [[]]
    for m in re.finditer(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            e = stack.pop()
            stack[-1].append(e)
        elif t[0] == '"':
            stack[-1].append(Q(t[1:-1]))
        else:
            stack[-1].append(t)
    return stack[0][0]


def ser(e, d=0):
    if isinstance(e, Q):
        return '"' + e + '"'
    if not isinstance(e, list):
        if isinstance(e, float):
            s = f"{e:.4f}".rstrip("0").rstrip(".")
            return "0" if s in ("-0", "") else s
        return str(e)
    if all(not isinstance(x, list) for x in e):
        return "(" + " ".join(ser(x) for x in e) + ")"
    s = "(" + ser(e[0])
    for x in e[1:]:
        s += ("\n" + "\t" * (d + 1) + ser(x, d + 1)) if isinstance(x, list) else " " + ser(x)
    return s + "\n" + "\t" * d + ")"


def uid(seed):
    """Deterministic UUID so regenerated files diff cleanly."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "surrklank/" + seed))


def child(e, key):
    return next((x for x in e if isinstance(x, list) and x and x[0] == key), None)


_libs = {}


def _lib(name):
    if name not in _libs:
        with open(f"{LIBDIR}/{name}.kicad_sym", encoding="utf-8") as f:
            _libs[name] = parse(f.read())
    return _libs[name]


def flatten(libname, name):
    sym = next(x for x in _lib(libname) if isinstance(x, list) and x[0] == "symbol" and x[1] == name)
    ext = child(sym, "extends")
    if not ext:
        return copy.deepcopy(sym)
    parent = flatten(libname, str(ext[1]))
    pname = str(parent[1])
    out = [x for x in parent if not (isinstance(x, list) and x[0] == "property")]
    out[1] = Q(name)
    props = [x for x in sym if isinstance(x, list) and x[0] == "property"]
    keys = {str(p[1]) for p in props}
    pprops = [x for x in parent if isinstance(x, list) and x[0] == "property" and str(x[1]) not in keys]
    for x in out:
        if isinstance(x, list) and x[0] == "symbol" and str(x[1]).startswith(pname + "_"):
            x[1] = Q(name + str(x[1])[len(pname):])
    return out[:2] + pprops + props + out[2:]


def rot(x, y, a):
    r = math.radians(a)
    return (round(x * math.cos(r) - y * math.sin(r), 4), round(x * math.sin(r) + y * math.cos(r), 4))


def r4(v):
    return round(v, 4)


class Part:
    def __init__(self, ref, pins):
        self.ref, self.pins = ref, pins

    def pin(self, key):
        if key in self.pins:
            return self.pins[key]
        return self.pins["name:" + key]


class Sheet:
    def __init__(self, project, title, rev, paper="A3", comments=()):
        self.project, self.title, self.rev, self.paper = project, title, rev, paper
        self.comments = comments
        self.root = uid(project + "/root")
        self.lib_symbols, self.items = {}, []
        self.n = 0
        self.pwr = 0

    def _id(self, kind):
        self.n += 1
        return uid(f"{self.project}/{kind}/{self.n}")

    def symbol(self, lib_id, ref, value, x, y, angle=0, footprint="", fields=None, mirror=None):
        libname, name = lib_id.split(":")
        if lib_id not in self.lib_symbols:
            s = flatten(libname, name)
            s[1] = Q(lib_id)
            self.lib_symbols[lib_id] = s
        s = self.lib_symbols[lib_id]
        pins = {}
        for sub in (x for x in s if isinstance(x, list) and x[0] == "symbol"):
            for p in (x for x in sub if isinstance(x, list) and x[0] == "pin"):
                at = child(p, "at")
                px, py = rot(float(at[1]), float(at[2]), angle)
                pa = (int(float(at[3])) + angle) % 360
                num, nm = str(child(p, "number")[1]), str(child(p, "name")[1])
                info = {"pos": (r4(x + px), r4(y - py)), "out": tuple(-v for v in DIR[pa]), "name": nm}
                pins[num] = info
                pins.setdefault("name:" + nm, info)
        virtual = ref.startswith("#")
        inst = ["symbol", ["lib_id", Q(lib_id)], ["at", x, y, angle], ["unit", 1],
                ["exclude_from_sim", "no"], ["in_bom", "no" if virtual else "yes"],
                ["on_board", "no" if virtual else "yes"], ["dnp", "no"], ["uuid", self._id("sym")]]
        values = {"Reference": ref, "Value": value}
        if footprint:
            values["Footprint"] = footprint
        for p in (x for x in s if isinstance(x, list) and x[0] == "property"):
            key = str(p[1])
            if key.startswith("ki_"):
                continue
            at = child(p, "at")
            px, py = rot(float(at[1]), float(at[2]), angle)
            prop = ["property", Q(key), Q(values.get(key, str(p[2]))),
                    ["at", r4(x + px), r4(y - py), (int(float(at[3])) + angle) % 180]]
            prop += [copy.deepcopy(e) for e in p[3:] if isinstance(e, list) and e[0] != "at"]
            inst.append(prop)
        for key, val in (fields or {}).items():
            inst.append(["property", Q(key), Q(val), ["at", x, y, 0],
                         ["hide", "yes"], ["effects", ["font", ["size", 1.27, 1.27]]]])
        for num in (k for k in pins if not k.startswith("name:")):
            inst.append(["pin", Q(num), ["uuid", self._id("pin")]])
        inst.append(["instances", ["project", Q(self.project),
                     ["path", Q("/" + self.root), ["reference", Q(ref)], ["unit", 1]]]])
        self.items.append(inst)
        return Part(ref, pins)

    def wire(self, a, b):
        self.items.append(["wire", ["pts", ["xy", *a], ["xy", *b]],
                           ["stroke", ["width", 0], ["type", "default"]], ["uuid", self._id("wire")]])

    def junction(self, p):
        self.items.append(["junction", ["at", *p], ["diameter", 0], ["color", 0, 0, 0, 0],
                           ["uuid", self._id("junction")]])

    def no_connect(self, part, pin):
        self.items.append(["no_connect", ["at", *part.pin(pin)["pos"]], ["uuid", self._id("nc")]])

    def label(self, name, p, out):
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[out]
        just = ["justify", "left" if ang in (0, 90) else "right", "bottom"]
        self.items.append(["label", Q(name), ["at", *p, ang],
                           ["effects", ["font", ["size", 1.27, 1.27]], just], ["uuid", self._id("label")]])

    def text(self, body, p, size=1.27):
        self.items.append(["text", Q(body.replace("\n", "\\n")), ["exclude_from_sim", "no"], ["at", *p, 0],
                           ["effects", ["font", ["size", size, size]], ["justify", "left", "bottom"]],
                           ["uuid", self._id("text")]])

    def power(self, net, p, out):
        self.pwr += 1
        down = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}
        up = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}
        ang = (down if net == "GND" else up)[out]
        self.symbol(f"power:{net}", f"#PWR{self.pwr:03d}", net, p[0], p[1], ang)

    def flag(self, net, p):
        """Power symbol plus PWR_FLAG: tells ERC the net is supplied here."""
        self.pwr += 1
        if net == "GND":
            self.power("GND", p, (0, 1))
            q = (p[0], r4(p[1] - 5.08))
            self.symbol("power:PWR_FLAG", f"#FLG{self.pwr:03d}", "PWR_FLAG", q[0], q[1], 0)
        else:
            self.power(net, p, (0, -1))
            q = (p[0], r4(p[1] + 5.08))
            self.symbol("power:PWR_FLAG", f"#FLG{self.pwr:03d}", "PWR_FLAG", q[0], q[1], 180)
        self.wire(p, q)

    def connect(self, part, pin, net, stub=2.54):
        """Short wire from the pin, ending in a label or a power symbol."""
        info = part.pin(pin)
        (x, y), (dx, dy) = info["pos"], info["out"]
        end = (r4(x + dx * stub), r4(y + dy * stub))
        self.wire((x, y), end)
        if net in POWER_NETS:
            self.power(net, end, (dx, dy))
        else:
            self.label(net, end, (dx, dy))
        return end

    def save(self, path):
        tb = ["title_block", ["title", Q(self.title)], ["rev", Q(self.rev)]]
        tb += [["comment", i + 1, Q(c)] for i, c in enumerate(self.comments)]
        doc = ["kicad_sch", ["version", SCH_VERSION], ["generator", Q("surrklank_gen")],
               ["generator_version", Q("10.0")], ["uuid", self.root], ["paper", Q(self.paper)], tb,
               ["lib_symbols", *self.lib_symbols.values()], *self.items,
               ["sheet_instances", ["path", Q("/"), ["page", Q("1")]]], ["embedded_fonts", "no"]]
        with open(path, "w", encoding="utf-8") as f:
            f.write(ser(doc) + "\n")
