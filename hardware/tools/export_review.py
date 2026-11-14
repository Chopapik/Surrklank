#!/usr/bin/env python3
"""Export human review material for the Surrklank boards.

For every board writes to hardware/fabrication/review/:
  surrklank-<board>-pins.md           pin-by-pin table of every connector,
                                      module and switch: pin number, pin name,
                                      net and what else is on that net

The tables come from the schematic netlist, not from WIRING.md, so they can be
compared against the real breadboard wiring and the physical parts. The paper
dry-fit sheet is made by export_dryfit.py.

Usage: export_review.py [board ...]     (default: all boards)
Requires kicad-cli (KiCad 10).
"""
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HARDWARE = Path(__file__).resolve().parent.parent
OUT = HARDWARE / "fabrication" / "review"
BOARDS = ["mainboard", "fdd-module", "actuator-module", "panel"]
# Reference prefixes that face the outside world (connectors, modules, controls).
EXTERNAL = ("J", "A", "M", "SW", "D", "JP")
MAX_PEERS = 6


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


def ref_key(ref):
    prefix = ref.rstrip("0123456789")
    digits = ref[len(prefix):]
    return prefix, int(digits) if digits else 0


def pin_key(pin):
    return (0, int(pin)) if pin.isdigit() else (1, pin)


def export_board(board, work):
    sch = HARDWARE / board / f"surrklank-{board}.kicad_sch"
    pcb = HARDWARE / board / f"surrklank-{board}.kicad_pcb"
    xml_path = work / "netlist.xml"
    run("sch", "export", "netlist", "--format", "kicadxml",
        "--output", str(xml_path), str(sch))
    root = ET.parse(xml_path).getroot()

    values = {c.get("ref"): c.findtext("value", "") for c in root.iter("comp")}
    where = {}
    nets = {}
    for net in root.iter("net"):
        name = net.get("name")
        nodes = [(n.get("ref"), n.get("pin"), n.get("pinfunction", ""))
                 for n in net.iter("node")]
        nets[name] = nodes
        for ref, pin, _ in nodes:
            where[(ref, pin)] = name

    lines = [f"# {board}: pin review", "",
             "Generated from the schematic netlist. Compare each row with the",
             "real part (pin names against its silkscreen) and with the",
             "breadboard wiring. 'Also on net' lists up to "
             f"{MAX_PEERS} other pins; GND and wide nets are summarised.", ""]
    pins = {}
    for net, nodes in nets.items():
        for ref, pin, func in nodes:
            pins.setdefault(ref, {})[pin] = (func, net)
    for ref in sorted(pins, key=ref_key):
        if not ref.startswith(EXTERNAL) or ref.startswith(("DRV",)):
            continue
        lines += [f"## {ref} ({values.get(ref, '')})", "",
                  "| Pin | Pin name | Net | Also on net |", "| --- | --- | --- | --- |"]
        for pin in sorted(pins[ref], key=pin_key):
            func, net = pins[ref][pin]
            peers = [f"{r}.{p}" + (f" ({f})" if f else "")
                     for r, p, f in nets[net] if (r, p) != (ref, pin)]
            if len(peers) > MAX_PEERS:
                peers = [f"{len(peers)} pins"]
            lines.append(f"| {pin} | {func} | {net} | {', '.join(peers)} |")
        lines.append("")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"surrklank-{board}-pins.md").write_text("\n".join(lines))
    print(f"{board}: {len([r for r in pins if r.startswith(EXTERNAL)])} "
          "parts in the pin table written")


def main():
    boards = sys.argv[1:] or BOARDS
    for board in boards:
        if board not in BOARDS:
            sys.exit(f"unknown board {board}; choose from {', '.join(BOARDS)}")
        with tempfile.TemporaryDirectory() as tmp:
            export_board(board, Path(tmp))


if __name__ == "__main__":
    main()
