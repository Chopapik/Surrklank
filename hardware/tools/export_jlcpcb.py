#!/usr/bin/env python3
"""Export JLCPCB fabrication files for the Surrklank boards.

For every board writes to hardware/fabrication/:
  surrklank-<board>.zip                   Gerbers (incl. paste) + PTH/NPTH drill
  bom/surrklank-<board>-bom-smd.csv       SMD parts, JLCPCB BOM format
  bom/surrklank-<board>-cpl.csv           placements, JLCPCB CPL format

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

# LCSC parts, library class checked on jlcpcb.com/partdetail/<number> on
# 2026-11-15. Only Basic parts are listed here: Extended parts add a fee per
# unique part type and are never put into the BOM automatically.
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

# No Basic part found for these (checked 2026-11-15). The BOM leaves the LCSC
# column empty and the export prints a warning: choosing an Extended part
# (a fee per unique type) is the owner's decision. Candidate -> class Extended.
UNRESOLVED = {
    ("74HC165", "SOIC-16"): "C5613 74HC165D,653 (Nexperia)",
    ("74LVC244A", "SOIC-20W"): "C548504 74LVC244AD,118 (Nexperia)",
    ("33", "R_Array"): "C25508 4D03WGJ0330T5E (Uniroyal)",
    ("100k", "R_Array"): "C1996 4D03WGJ0104T5E (Uniroyal)",
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
            UNRESOLVED_USED.add(f"{comment} {name}: Extended only, candidate {candidate}")
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
    parts = 0
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
            writer.writerow([comment, row["Designator"],
                             row["Footprint"].split(":", 1)[-1], number])
    with open(pos_raw, newline="") as src, \
            open(bom_dir / f"surrklank-{board}-cpl.csv", "w",
                 newline="") as dst:
        writer = csv.writer(dst)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        placed = 0
        for row in csv.DictReader(src):
            rotation = (float(row["Rot"]) + rotation_offset(row["Package"])) % 360
            writer.writerow([row["Ref"], f"{float(row['PosX']):.4f}mm",
                             f"{float(row['PosY']):.4f}mm",
                             "Top" if row["Side"] == "top" else "Bottom",
                             f"{rotation:g}"])
            placed += 1
    print(f"{board}: gerbers zipped, {parts} SMD parts in BOM, "
          f"{placed} placements")


def main():
    boards = sys.argv[1:] or BOARDS
    for board in boards:
        if board not in BOARDS:
            sys.exit(f"unknown board {board}; choose from {', '.join(BOARDS)}")
        with tempfile.TemporaryDirectory() as tmp:
            export_board(board, Path(tmp))
    for line in sorted(UNRESOLVED_USED):
        print("no Basic part:", line)


if __name__ == "__main__":
    main()
