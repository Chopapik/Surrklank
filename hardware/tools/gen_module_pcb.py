#!/usr/bin/env python3
"""Module PCB steps for the FDD and LSM/HDD boards (run with KiCad's Python).

  KIPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
  $KIPY gen_module_pcb.py <board> place  <netlist.xml> <x.kicad_pcb>  # footprints, nets, outline, zones
  $KIPY gen_module_pcb.py <board> dsn    <x.kicad_pcb> <out.dsn>      # Specctra export (power planes only)
  $KIPY gen_module_pcb.py <board> import <x.kicad_pcb> <in.ses>       # import routes, fill zones
  $KIPY gen_module_pcb.py <board> brand  <x.kicad_pcb> -              # (re)place logo and text only

<board> is `fdd`, `lsm-hdd`, `mainboard` or `panel`. Routing itself is done by Freerouting between
`dsn` and `import` (see hardware/README.md). This script never draws tracks.
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
STD = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
LIBS = {"surrklank": os.path.join(HERE, "..", "lib", "surrklank.pretty")}
OX, OY = 100.0, 100.0       # board origin on the page
PLANE = "dsn-plane"         # zone name: exported to Freerouting as a power plane


# ---------------------------------------------------------------- FDD module
def fdd_board():
    place = {
        "J1": (6.0, 20.0, 0), "J2": (91.5, 20.0, 0),
        "J5": (30.0, 7.0, 0), "C6": (55.0, 4.5, 0), "U6": (64.0, 8.0, 0), "C7": (73.0, 4.5, 0),
        "JP1": (16.0, 44.0, 0),
        "RN1": (15.5, 15.0, 0), "RN2": (20.5, 15.0, 0),
        "U1": (24.0, 28.0, 0), "C1": (24.0, 37.5, 0),
        "U2": (40.0, 28.0, 0), "C2": (40.0, 36.0, 0),
        "U3": (52.0, 28.0, 0), "C3": (52.0, 36.0, 0),
        "U4": (64.0, 28.0, 0), "C4": (64.0, 36.0, 0),
        "U5": (76.0, 28.0, 0), "C5": (76.0, 36.0, 0),
        "RN3": (84.0, 15.0, 0), "RN4": (84.0, 21.0, 0),
        "J3": (25.0, 61.0, 90), "J4": (25.0, 74.0, 90),
        "H1": (4.0, 4.0, 0), "H2": (96.0, 4.0, 0), "H3": (4.0, 76.0, 0), "H4": (96.0, 76.0, 0),
    }
    for i, ref in enumerate(["RN10", "RN11", "RN12", "RN13", "RN14", "RN15", "RN16", "RN17", "RN18", "RN19"]):
        place[ref] = (27.0 + i * 5.5, 46.0, 90)
    return {
        "size": (100.0, 80.0),
        "place": place,
        "logo": (91.0, 56.0),          # about 8 mm right of the drive headers
        "brand_text": [("SURRKLANK", 63.0, 1.3), ("FDD MODULE v0.1", 65.6, 1.0)],
        "by_text": ("by", 86.6, 52.0, 3.0),  # italic Times New Roman at the logo's top-left corner
        "ref_at": {},
        "power_zones": [],
        "keepouts": [],
    }


# ------------------------------------------------------------ LSM/HDD module
# DRV8833 slots are rotated 90 degrees: the top row holds IN1..IN4, VCC (pin 9)
# and GND (pin 10); the bottom row holds EEP, OUT1..OUT4 and ULT, so the
# JST-XH motor connectors sit straight below it at the board edge.
SLOT_X = (29.5, 49.0, 68.5, 88.0)   # x of pin 1 (and pin 12) per slot
ROW_TOP, ROW_BOT = 50.76, 66.0      # y of pins 7..12 and 1..6
BAND = (3.5, 44.5, 116.5, 52.4)     # +5V copper band on B_Cu (x1, y1, x2, y2)


def lsm_hdd_zones():
    """+5V band and lower GND plane on B_Cu; both are exported to Freerouting
    as planes, so the router keeps signals off B_Cu there."""
    x1, y1, x2, y2 = BAND
    pin10 = [x + 5.08 for x in SLOT_X]          # GND pin of each slot
    band = [(x1, y1), (x2, y1), (x2, y2)]
    for nx in reversed(pin10):                   # notch around each GND pin
        band += [(nx + 1.5, y2), (nx + 1.5, 49.2), (nx - 1.5, 49.2), (nx - 1.5, y2)]
    band.append((x1, y2))
    gnd = [(0.5, 52.8)]
    for nx in pin10:                             # tab up to each GND pin
        gnd += [(nx - 1.1, 52.8), (nx - 1.1, 49.6), (nx + 1.1, 49.6), (nx + 1.1, 52.8)]
    gnd += [(119.5, 52.8), (119.5, 79.5), (0.5, 79.5)]
    return [("+5V", pcbnew.B_Cu, band, 2), ("GND", pcbnew.B_Cu, gnd, 1)]


# Freerouting connects pads through the planes but does not treat them as
# obstacles, so B_Cu tracks and vias are forbidden below the band's top edge.
# The top 0.8 mm strip of the band stays open for feeds into the plane.
LSM_HDD_KEEPOUT = (0.0, BAND[1] + 0.8, 120.0, 80.0)


def lsm_hdd_board():
    place = {
        "J1": (6.0, 20.0, 0), "J2": (111.5, 20.0, 0),
        "RN1": (15.5, 15.0, 0), "RN2": (20.5, 15.0, 0),
        "RN3": (104.0, 15.0, 0), "RN4": (104.0, 21.0, 0),
        "JP1": (17.0, 40.0, 0),
        "U1": (24.0, 28.0, 0), "C1": (24.0, 37.5, 0),
        "U2": (44.0, 28.0, 0), "C2": (44.0, 36.0, 0),
        "U3": (60.0, 28.0, 0), "C3": (60.0, 36.0, 0),
        "U4": (76.0, 28.0, 0), "C4": (76.0, 36.0, 0),
        "U5": (92.0, 28.0, 0), "C5": (92.0, 36.0, 0),
        "RN10": (60.0, 41.0, 90), "RN11": (84.0, 41.0, 90),
        "C6": (60.0, 4.5, 0), "U6": (69.0, 8.0, 0), "C7": (78.0, 4.5, 0),
        # Molex: pin 4 (+5V) in the band, pins 2-3 (GND) on the lower plane
        "J5": (7.5, ROW_BOT, 90), "J10": (112.5, ROW_BOT, 90),
        "C8": (20.5, ROW_TOP, 270),            # + in the band, - on the GND plane
        "H1": (4.0, 4.0, 0), "H2": (116.0, 4.0, 0), "H3": (4.0, 76.0, 0), "H4": (116.0, 76.0, 0),
    }
    for m, x in enumerate(SLOT_X, start=1):
        place[f"M{m}"] = (x, ROW_BOT, 90)
        place[f"J{5 + m}"] = (x + 2.6, 74.5, 0)   # OUT1..OUT4 straight down
    return {
        "size": (120.0, 80.0),
        "place": place,
        "logo": (40.0, 6.0),
        "brand_text": [("SURRKLANK", 13.0, 1.3), ("LSM/HDD MODULE v0.1", 15.6, 1.0)],
        "by_text": ("by", 35.6, 2.0, 3.0),
        "ref_at": {"C8": (20.5, 60.0)},       # keep the label off the M1 outline
        "power_zones": lsm_hdd_zones(),
        "keepouts": [((pcbnew.B_Cu,), LSM_HDD_KEEPOUT, True)],
    }


# ---------------------------------------------------------------- mainboard
def mainboard_board():
    # ESP32 board with its antenna end flush with the top edge (pin 1 at y 5);
    # no copper on either layer under the antenna end.
    place = {
        "A1": (8.0, 5.0, 0),
        "J1": (44.0, 59.5, 0),                    # ATX terminal, plug side to the bottom edge
        "J2": (100.0, 8.0, 0), "J3": (100.0, 40.0, 0),
        "C2": (48.0, 5.0, 0),
        "J6": (58.0, 6.5, 90),                    # remote panel cable at the top edge
        "R7": (78.0, 6.0, 0), "R8": (82.0, 6.0, 0), "R9": (78.0, 10.0, 0), "R10": (82.0, 10.0, 0),
        "RN1": (46.0, 14.0, 0), "RN2": (54.0, 14.0, 0), "RN3": (62.0, 14.0, 0),
        "RN4": (74.0, 16.0, 0), "RN5": (82.0, 16.0, 0), "R5": (84.0, 26.0, 0), "JP2": (84.0, 30.0, 0),
        "RN6": (74.0, 46.0, 0), "RN7": (82.0, 46.0, 0), "R6": (84.0, 58.0, 0), "JP3": (84.0, 62.0, 0),
        "C1": (44.0, 50.0, 0), "JP1": (40.0, 49.0, 0),
        "R1": (50.0, 50.0, 0), "R2": (50.0, 55.0, 0),
        "R3": (56.0, 50.0, 0), "R4": (56.0, 55.0, 0), "Q1": (64.0, 53.0, 0),
        "J4": (76.0, 66.0, 0), "C3": (84.0, 66.0, 0),
        "H1": (40.0, 4.0, 0), "H2": (88.0, 4.0, 0), "H3": (4.0, 68.0, 0), "H4": (106.0, 68.0, 0),
    }
    return {
        "size": (110.0, 72.0),
        "place": place,
        "logo": (62.0, 30.0),
        "brand_text": [("SURRKLANK", 37.0, 1.3), ("MAINBOARD v0.1", 39.6, 1.0)],
        "by_text": ("by", 57.6, 26.0, 3.0),
        "ref_at": {},
        "power_zones": [],
        # Below the USB end (y > 56, x 6-36) stays free for the USB plug.
        "notes": [("REMOVE JP1 BEFORE USB", 20.7, 62.0, 1.0)],
        "keepouts": [((pcbnew.F_Cu, pcbnew.B_Cu), (5.0, 0.0, 37.0, 3.6), False)],
    }


# -------------------------------------------------------------- remote panel
def panel_board():
    # U1 is rotated so GPA (buttons) faces down and GPB/I2C faces up.
    # Everything on the front: cable header top left, OLED module on a socket
    # top middle (its 27 x 27 mm body covers the area below the socket),
    # LEDs top right, buttons in a row near the bottom.
    sw_y = 42.0
    place = {
        "J1": (16.0, 6.5, 90),
        "J4": (44.0, 6.0, 90),                    # OLED module x 34-61, y 3-31
        "D1": (64.0, 8.0, 0), "D2": (71.0, 8.0, 0), "D3": (78.0, 8.0, 0), "D4": (85.0, 8.0, 0),
        "R1": (79.3, 16.0, 0), "R2": (86.3, 16.0, 0),
        "U1": (80.0, 28.0, 270), "C1": (66.0, 22.0, 0), "C2": (66.0, 34.0, 0), "R3": (95.0, 28.0, 90),
        "SW1": (8.0, sw_y, 0),
        "SW2": (36.0, sw_y, 0), "SW3": (48.0, sw_y, 0), "SW4": (60.0, sw_y, 0), "SW5": (72.0, sw_y, 0),
        "J3": (20.0, 55.0, 0), "J2": (66.0, 55.0, 0),          # JST-XH, latch side to the edge
        "H1": (4.0, 4.0, 0), "H2": (96.0, 4.0, 0), "H3": (4.0, 55.0, 0), "H4": (96.0, 55.0, 0),
    }
    label_y = sw_y + 8.2
    notes = [(t, x + 3.25, label_y, 1.0) for t, x in
             (("POWER", 8.0), ("PREV", 36.0), ("PLAY", 48.0), ("STOP", 60.0), ("NEXT", 72.0))]
    notes += [(t, x + 1.27, 11.6, 0.8) for t, x in
              (("STBY", 64.0), ("RAILS", 71.0), ("ATX ON", 78.0), ("ESP", 85.0))]
    notes += [("OLED GND VCC SCL SDA", 47.8, 9.4, 0.8)]
    return {
        "size": (100.0, 59.0),
        "place": place,
        "logo": (16.0, 23.0),
        "brand_text": [("SURRKLANK", 30.0, 1.3), ("PANEL v0.1", 32.6, 1.0)],
        "by_text": ("by", 11.6, 19.0, 3.0),
        "ref_at": {},
        "power_zones": [],
        "notes": notes,
        "keepouts": [],
    }


BOARDS = {"fdd": fdd_board, "lsm-hdd": lsm_hdd_board, "mainboard": mainboard_board, "panel": panel_board}
B = None   # selected board configuration


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def apply_rules(board):
    """Rules on the in-memory board (used by this process)."""
    board.GetDesignSettings().m_TrackMinWidth = mm(0.15)  # low-cost fab limit is 0.127 mm


def set_project_rules(board_path):
    """Write the rule into the .kicad_pro, which KiCad may have rewritten with defaults."""
    pro = os.path.splitext(board_path)[0] + ".kicad_pro"
    with open(pro, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})["min_track_width"] = 0.15
    with open(pro, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


def add_text(board, text, x, y, size):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(pt(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    board.Add(t)


def brand(board):
    """Logo footprint, short text and notes on the front silkscreen; replaces old ones."""
    # Collect first: SWIG item lists become unusable after a Remove() in this process.
    texts = {t for t, *_ in B["brand_text"]} | {t for t, *_ in B.get("notes", [])} | {B["by_text"][0]}
    old = [fp for fp in board.GetFootprints() if fp.GetReference() == "LOGO1"]
    old += [d for d in board.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetText() in texts]
    for item in old:
        board.Remove(item)
    logo = load_footprint("surrklank:Surrklank_Logo_8mm")
    logo.SetReference("LOGO1")
    logo.SetPosition(pt(*B["logo"]))
    board.Add(logo)
    for text, y, size in B["brand_text"]:
        add_text(board, text, B["logo"][0], y, size)
    for text, x, y, size in B.get("notes", []):
        add_text(board, text, x, y, size)
    text, x, y, size = B["by_text"]
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetUnresolvedFontName("Times New Roman")   # system TrueType font; outlined in Gerbers
    t.SetItalic(True)
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    t.SetPosition(pt(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    board.Add(t)


def set_by_font(board_path):
    """KiCad's Python API cannot set a TrueType face; add it to the saved file."""
    with open(board_path, encoding="utf-8") as f:
        text = f.read()
    start = text.index(f'(gr_text "{B["by_text"][0]}"')
    font = text.index("(font", start)
    if '(face "Times New Roman")' not in text[font:font + 200]:
        text = text[:font + 5] + ' (face "Times New Roman")' + text[font + 5:]
        with open(board_path, "w", encoding="utf-8") as f:
            f.write(text)


def save(board, board_path):
    apply_rules(board)
    pcbnew.SaveBoard(board_path, board)
    set_by_font(board_path)
    set_project_rules(board_path)


def brand_file(board_path, _unused):
    board = pcbnew.LoadBoard(board_path)
    brand(board)
    save(board, board_path)


def load_footprint(fpid):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(LIBS.get(lib, f"{STD}/{lib}.pretty"), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def add_rect(board, layer, x1, y1, x2, y2, width=0.1):
    pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(a, b))
        s.SetEnd(pt(c, d))
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        board.Add(s)


def add_zone(board, net, layer, points, priority=0, name=""):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in points:
        outline.Append(mm(OX + x), mm(OY + y))
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetAssignedPriority(priority)
    z.SetZoneName(name)
    # Solid connection: dense connector pins leave no room for thermal spokes,
    # and power pins carry motor current.
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    board.Add(z)


def add_keepout(board, layers, rect, allow_pours):
    """Rule area forbidding tracks and vias (and pours unless allowed); pads stay allowed."""
    x1, y1, x2, y2 = rect
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    ls = pcbnew.LSET()
    for layer in layers:
        ls.AddLayer(layer)
    z.SetLayerSet(ls)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowZoneFills(not allow_pours)
    z.SetDoNotAllowFootprints(False)
    z.SetZoneName("keepout")
    outline = z.Outline()
    outline.NewOutline()
    for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        outline.Append(mm(OX + x), mm(OY + y))
    board.Add(z)


def place(netlist, out):
    root = ET.parse(netlist).getroot()
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(2)

    nets, pad_net = {}, {}
    for n in root.iter("net"):
        info = pcbnew.NETINFO_ITEM(board, n.get("name"))
        board.Add(info)
        nets[n.get("name")] = info
        for node in n.iter("node"):
            pad_net[(node.get("ref"), node.get("pin"))] = info

    for comp in root.iter("comp"):
        ref = comp.get("ref")
        fpid = comp.findtext("footprint")
        if not fpid:
            continue
        fp = load_footprint(fpid)
        fp.SetReference(ref)
        fp.SetValue(comp.findtext("value") or "")
        fp.SetField("Datasheet", comp.findtext("datasheet") or "")
        fp.SetField("Description", comp.findtext("description") or "")
        stamp = (comp.findtext("tstamps") or "").split()[0]
        fp.SetPath(pcbnew.KIID_PATH("/" + stamp))
        for prop in comp.iter("property"):
            if prop.get("name") == "dnp":
                fp.SetDNP(True)
            elif prop.get("name").startswith("Sim."):   # schematic parity checks these
                fp.SetField(prop.get("name"), prop.get("value") or "")
                fp.GetField(prop.get("name")).SetVisible(False)
        if ref.startswith("H"):
            fp.Reference().SetVisible(False)
        x, y, rot = B["place"][ref]
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        if ref in B["ref_at"]:
            fp.Reference().SetPosition(pt(*B["ref_at"][ref]))
        for pad in fp.Pads():
            info = pad_net.get((ref, pad.GetNumber()))
            if info is not None:
                pad.SetNet(info)
        board.Add(fp)

    w, h = B["size"]
    add_rect(board, pcbnew.Edge_Cuts, 0, 0, w, h)
    brand(board)
    for net, layer, points, priority in B["power_zones"]:
        add_zone(board, nets[net], layer, points, priority, PLANE)
    for layers, rect, allow_pours in B["keepouts"]:
        add_keepout(board, layers, rect, allow_pours)
    full = [(0.5, 0.5), (w - 0.5, 0.5), (w - 0.5, h - 0.5), (0.5, h - 0.5)]
    add_zone(board, nets["GND"], pcbnew.F_Cu, full)
    add_zone(board, nets["GND"], pcbnew.B_Cu, full)
    save(board, out)


def dsn(board_path, out):
    """Export for Freerouting; only the power-plane zones are kept."""
    board = pcbnew.LoadBoard(board_path)
    for z in [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetZoneName() != PLANE]:
        board.Remove(z)
    if not pcbnew.ExportSpecctraDSN(board, out):
        raise SystemExit("DSN export failed")


def import_ses(board_path, ses):
    board = pcbnew.LoadBoard(board_path)
    for t in list(board.GetTracks()):
        board.Remove(t)
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise SystemExit("SES import failed")
    pcbnew.SaveBoard(board_path, board)
    # The SWIG track list is unusable after an import in the same process,
    # so cleanup and zone fill run in a fresh interpreter.
    subprocess.run([sys.executable, __file__, sys.argv[1], "finish", board_path, "-"], check=True)


def finish(board_path, _unused):
    board = pcbnew.LoadBoard(board_path)
    # Freerouting can leave zero-length stubs; they carry no connection.
    stubs = [t for t in board.GetTracks()
             if t.GetClass() == "PCB_TRACK" and t.GetLength() < pcbnew.FromMM(0.001)]
    for t in stubs:
        board.Remove(t)
    # Fabrication floor: widen any neck-down below 0.15 mm; DRC then checks clearance.
    narrow = [t for t in board.GetTracks()
              if t.GetClass() == "PCB_TRACK" and t.GetWidth() < pcbnew.FromMM(0.15)]
    for t in narrow:
        t.SetWidth(pcbnew.FromMM(0.15))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save(board, board_path)
    vias = sum(t.GetClass() == "PCB_VIA" for t in board.GetTracks())
    print(f"tracks {len(board.GetTracks()) - vias}, vias {vias}, removed stubs {len(stubs)}, widened {len(narrow)}")


if __name__ == "__main__":
    B = BOARDS[sys.argv[1]]()
    {"place": place, "dsn": dsn, "import": import_ses, "finish": finish,
     "brand": brand_file}[sys.argv[2]](sys.argv[3], sys.argv[4])
