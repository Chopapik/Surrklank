#!/usr/bin/env python3
"""Export JLCPCB fabrication files for the Surrklank boards.

For every board writes to hardware/fabrication/:
  surrklank-<board>.zip                   Gerbers (incl. paste) + PTH/NPTH drill
  bom/surrklank-<board>-bom-smd.csv       SMD parts, JLCPCB BOM format
  cpl/surrklank-<board>-cpl.csv           placements, JLCPCB CPL format
  bom/surrklank-<board>-hand-solder.csv   SMD parts left out of the BOM and CPL
                                          (no Basic/Promotional LCSC part): the
                                          owner solders these by hand

Usage: export_jlcpcb.py [board ...]     (default: all boards)

Requires kicad-cli (KiCad 10). Nothing is uploaded or ordered.
"""
import csv
import io
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HARDWARE = Path(__file__).resolve().parent.parent
OUT = HARDWARE / "fabrication"
BOARDS = ["mainboard", "fdd-module", "actuator-module", "panel"]

# F.Paste/B.Paste are the solder paste layers JLCPCB uses to make a stencil.
GERBER_LAYERS = ("F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,"
                 "F.Paste,B.Paste,Edge.Cuts")

# KiCad and JLCPCB use different zero angles for some packages. Offsets are
# added to the KiCad rotation and were read off the JLCPCB placement preview
# (pin-1 marker against the board silkscreen) on the FDD module. SOIC-28W,
# SOT-23 and other packages are not verified: check each one in the preview.
ROTATION_OFFSETS = [
    ("SOIC-", 270),
    ("SOT-223", 180),
]

# LCSC parts, library class checked on the JLCPCB parts library on
# 2026-11-15. Only Basic and Promotional (Preferred) Extended parts are listed
# here: plain Extended parts add a feeder loading fee per unique part type and
# are never put into the BOM automatically. Promotional Extended parts carry
# no loading fee in Economic assembly only; their part page still says
# "Extended", the category page and the library search show the promotion.
# (BOM comment, footprint-name prefix) -> (LCSC number, manufacturer part).
# JLCPCB warns when the BOM comment differs from the part's own name, so the
# manufacturer part replaces the comment when it is known.
LCSC = {
    ("100n", "C_0805"): ("C49678", "CC0805KRX7R9BB104"),
    ("10u", "C_0805"): ("C15850", "CL21A106KAYNNNE"),
    ("22u", "C_1206"): ("C12891", "CL31A226KAHNNNE"),
    ("10k", "R_Array"): ("C29718", "4D03WGJ0103T5E"),
    ("4.7k", "R_Array"): ("C1980", "4D03WGJ0472T5E"),
    ("74HC595", "SOIC-16"): ("C5947", "74HC595D,118"),
    # Promotional Extended (Shift Registers category page, 2026-11-15).
    ("74HC165", "SOIC-16"): ("C5613", "74HC165D,653"),
    ("AMS1117-3.3", "SOT-223"): ("C6186", "AMS1117-3.3"),
    ("MMBT3904", "SOT-23"): ("C20526", "MMBT3904(RANGE:100-300)"),
    ("1k", "R_0603"): ("C21190", "0603WAF1001T5E"),
    ("LED", "LED_0603"): ("C2286", "KT-0603R"),
    ("10k", "R_0805"): ("C17414", "0805W8F1002T5E"),
    ("20k", "R_0805"): ("C4328", "0805W8F2002T5E"),
    ("2.2k", "R_0805"): ("C17520", "0805W8F2201T5E"),
    ("100k", "R_0805"): ("C149504", "0805W8F1003T5E"),
    ("1k", "R_0805"): ("C17513", "0805W8F1001T5E"),
    ("470", "R_0805"): ("C17710", "0805W8F4700T5E"),
    ("330", "R_0805"): ("C17630", "0805W8F3300T5E"),
}

# No Basic or Promotional Extended part found for these (checked 2026-11-15).
# They are left out of the assembly BOM and CPL and listed in the board's
# hand-solder file: the owner solders them by hand (the alternative, a plain
# Extended part, costs a fee per unique type). Candidates are Extended.
UNRESOLVED = {
    ("74LVC244A", "SOIC-20W"): "C548504 74LVC244AD,118 (Nexperia)",
    ("33", "R_Array"): "C25508 4D03WGJ0330T5E (Uniroyal), C165956 YC164-JR-0733RL (Yageo)",
    ("100k", "R_Array"): "C1996 4D03WGJ0104T5E (Uniroyal), C192933 YC164-JR-07100KL (Yageo)",
    ("MCP23017-E/SO", "SOIC-28W"): "C47023 MCP23017-E/SO (Microchip)",
}

UNRESOLVED_USED = set()
SMD_MARKERS = ("_SMD", "Package_SO:")


def kicad_cli():
    found = shutil.which("kicad-cli")
    if found:
        return found
    app = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if app.exists():
        return str(app)
    sys.exit("kicad-cli not found")


def run(*args):
    subprocess.run([kicad_cli(), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def rotation_offset(package):
    for prefix, offset in ROTATION_OFFSETS:
        if package.startswith(prefix):
            return offset
    return 0


def lcsc_for(comment, footprint):
    """Return (comment for the BOM, LCSC number)."""
    name = footprint.split(":", 1)[-1]
    for (value, prefix), (number, mpn) in LCSC.items():
        if comment == value and name.startswith(prefix):
            return mpn or comment, number
    for (value, prefix), candidate in UNRESOLVED.items():
        if comment == value and name.startswith(prefix):
            UNRESOLVED_USED.add(f"{comment} {name}: Extended only, candidates {candidate}")
    return comment, ""


def export_board(board, work):
    pcb = HARDWARE / board / f"surrklank-{board}.kicad_pcb"
    sch = HARDWARE / board / f"surrklank-{board}.kicad_sch"
    gerbers = work / "gerbers"
    gerbers.mkdir()
    run("pcb", "export", "gerbers", "--output", f"{gerbers}/",
        "--layers", GERBER_LAYERS, str(pcb))
    run("pcb", "export", "drill", "--output", f"{gerbers}/",
        "--format", "excellon", "--drill-origin", "absolute",
        "--excellon-units", "mm", "--excellon-separate-th", str(pcb))
    OUT.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT / f"surrklank-{board}.zip", "w",
                         zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gerbers.iterdir()):
            z.write(f, f.name)

    bom_raw = work / "bom.csv"
    run("sch", "export", "bom", "--output", str(bom_raw),
        "--fields", "Reference,Value,Footprint,${QUANTITY},${DNP}",
        "--labels", "Designator,Comment,Footprint,Qty,DNP",
        "--group-by", "Value,Footprint", "--ref-range-delimiter", "",
        str(sch))
    pos_raw = work / "pos.csv"
    run("pcb", "export", "pos", "--output", str(pos_raw), "--format", "csv",
        "--units", "mm", "--side", "both", "--smd-only", "--exclude-dnp",
        str(pcb))

    bom_dir = OUT / "bom"
    bom_dir.mkdir(exist_ok=True)
    cpl_dir = OUT / "cpl"
    cpl_dir.mkdir(exist_ok=True)
    parts = 0
    hand = []
    with open(bom_raw, newline="") as src, \
            open(bom_dir / f"surrklank-{board}-bom-smd.csv", "w",
                 newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for row in csv.DictReader(src):
            if row["DNP"] or not any(m in row["Footprint"] for m in SMD_MARKERS):
                continue
            parts += int(row["Qty"])
            comment, number = lcsc_for(row["Comment"], row["Footprint"])
            if not number:
                hand.append((comment, row["Designator"],
                             row["Footprint"].split(":", 1)[-1]))
                parts -= int(row["Qty"])
                continue
            writer.writerow([comment, row["Designator"],
                             row["Footprint"].split(":", 1)[-1], number])
    hand_refs = {r.strip() for _, refs, _ in hand for r in refs.split(",")}
    with open(bom_dir / f"surrklank-{board}-hand-solder.csv", "w",
              newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow(["Comment", "Designator", "Footprint"])
        writer.writerows(hand)
    with open(pos_raw, newline="") as src, \
            open(cpl_dir / f"surrklank-{board}-cpl.csv", "w",
                 newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        placed = 0
        for row in csv.DictReader(src):
            if row["Ref"] in hand_refs:
                continue
            rotation = (float(row["Rot"]) + rotation_offset(row["Package"])) % 360
            writer.writerow([row["Ref"], f"{float(row['PosX']):.4f}mm",
                             f"{float(row['PosY']):.4f}mm",
                             "Top" if row["Side"] == "top" else "Bottom",
                             f"{rotation:g}"])
            placed += 1
    print(f"{board}: gerbers zipped, {parts} SMD parts in the assembly BOM, "
          f"{placed} placements (hand-solder parts left out)")
    # The assembly BOM only holds Basic or Promotional Extended parts. CPL
    # rotations for SOT-23 and resistor arrays are unverified either way.
    print(f"{board}: assembly BOM has Basic/Promotional parts only")
    if hand:
        print(f"{board}: solder by hand: "
              f"{', '.join(f'{c} ({r})' for c, r, _ in hand)}")


def main():
    boards = sys.argv[1:] or BOARDS
    for board in boards:
        if board not in BOARDS:
            sys.exit(f"unknown board {board}; choose from {', '.join(BOARDS)}")
        with tempfile.TemporaryDirectory() as tmp:
            export_board(board, Path(tmp))
    for line in sorted(UNRESOLVED_USED):
        print("no Basic/Promotional part:", line)


if __name__ == "__main__":
    main()
