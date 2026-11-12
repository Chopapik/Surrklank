#!/usr/bin/env python3
"""FDD module PCB steps (run with KiCad's Python).

  KIPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
  $KIPY gen_fdd_pcb.py place  <netlist.xml> <board.kicad_pcb>   # footprints, nets, outline, GND zones
  $KIPY gen_fdd_pcb.py dsn    <board.kicad_pcb> <out.dsn>        # Specctra export without zones
  $KIPY gen_fdd_pcb.py import <board.kicad_pcb> <in.ses>         # import routes, fill zones
  $KIPY gen_fdd_pcb.py brand  <board.kicad_pcb> -                # (re)place logo and text only

Routing itself is done by Freerouting between `dsn` and `import`
(see hardware/README.md). This script never draws tracks.
"""
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
STD = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
LIBS = {"surrklank": os.path.join(HERE, "..", "lib", "surrklank.pretty")}

W, H = 100.0, 80.0          # board size, mm
OX, OY = 100.0, 100.0       # board origin on the page

# ref: (x, y, rotation degrees) in board millimetres, top side
PLACE = {
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
    PLACE[ref] = (27.0 + i * 5.5, 46.0, 90)


# Silkscreen branding (board-only, not in the schematic)
LOGO_AT = (87.0, 56.0)
BRAND_TEXT = [("SURRKLANK", 63.0, 1.3), ("FDD MODULE v0.1", 65.6, 1.0)]


def mm(v):
    return pcbnew.FromMM(v)


def brand(board):
    """Logo footprint and short text on the front silkscreen; replaces old ones."""
    for fp in list(board.GetFootprints()):
        if fp.GetReference() == "LOGO1":
            board.Remove(fp)
    for d in list(board.GetDrawings()):
        if d.GetClass() == "PCB_TEXT" and d.GetText() in {t for t, _, _ in BRAND_TEXT}:
            board.Remove(d)
    logo = load_footprint("surrklank:Surrklank_Logo_8mm")
    logo.SetReference("LOGO1")
    logo.SetPosition(pcbnew.VECTOR2I(mm(OX + LOGO_AT[0]), mm(OY + LOGO_AT[1])))
    board.Add(logo)
    for text, y, size in BRAND_TEXT:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetPosition(pcbnew.VECTOR2I(mm(OX + LOGO_AT[0]), mm(OY + y)))
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(size * 0.15))
        board.Add(t)


def brand_file(board_path, _unused):
    board = pcbnew.LoadBoard(board_path)
    brand(board)
    pcbnew.SaveBoard(board_path, board)


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
        s.SetStart(pcbnew.VECTOR2I(mm(OX + a), mm(OY + b)))
        s.SetEnd(pcbnew.VECTOR2I(mm(OX + c), mm(OY + d)))
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        board.Add(s)


def add_zone(board, net, layer, margin=0.5):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in ((margin, margin), (W - margin, margin), (W - margin, H - margin), (margin, H - margin)):
        outline.Append(mm(OX + x), mm(OY + y))
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    # Solid GND connection: dense connector pins leave no room for thermal spokes.
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
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
        if ref.startswith("H"):
            fp.Reference().SetVisible(False)
        x, y, rot = PLACE[ref]
        fp.SetPosition(pcbnew.VECTOR2I(mm(OX + x), mm(OY + y)))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            info = pad_net.get((ref, pad.GetNumber()))
            if info is not None:
                pad.SetNet(info)
        board.Add(fp)

    add_rect(board, pcbnew.Edge_Cuts, 0, 0, W, H)
    brand(board)
    add_zone(board, nets["GND"], pcbnew.F_Cu)
    add_zone(board, nets["GND"], pcbnew.B_Cu)
    pcbnew.SaveBoard(out, board)


def dsn(board_path, out):
    board = pcbnew.LoadBoard(board_path)
    for z in list(board.Zones()):
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
    subprocess.run([sys.executable, __file__, "finish", board_path, "-"], check=True)


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
    pcbnew.SaveBoard(board_path, board)
    vias = sum(t.GetClass() == "PCB_VIA" for t in board.GetTracks())
    print(f"tracks {len(board.GetTracks()) - vias}, vias {vias}, removed stubs {len(stubs)}, widened {len(narrow)}")


if __name__ == "__main__":
    {"place": place, "dsn": dsn, "import": import_ses, "finish": finish, "brand": brand_file}[sys.argv[1]](sys.argv[2], sys.argv[3])
