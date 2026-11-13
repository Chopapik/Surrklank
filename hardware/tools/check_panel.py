#!/usr/bin/env python3
"""Check an exported remote panel netlist against docs/WIRING.md (Remote panel).

Usage: python3 -I check_panel.py <netlist.xml>
Rules are written out here independently of the generator.
"""
import sys
import xml.etree.ElementTree as ET

# Mainboard J6 pinout; the ribbon is straight-through
CABLE = {"1": "3V3", "2": "GND", "3": "SDA", "4": "GND", "5": "SCL", "6": "GND",
         "7": "INT", "8": "BUTTON", "9": "LED_SB", "10": "LED_ON"}
# MCP23017 SOIC-28 pins
MCP = {"VDD": "9", "VSS": "10", "SCK": "12", "SDA": "13", "A0": "15", "A1": "16", "A2": "17",
       "RESET": "18", "INTA": "20"}
errors = []


def main(path):
    root = ET.parse(path).getroot()
    nets, where = {}, {}
    for n in root.iter("net"):
        name = n.get("name").lstrip("/")
        nets[name] = {(x.get("ref"), x.get("pin")) for x in n.iter("node")}
        for x in n.iter("node"):
            where[(x.get("ref"), x.get("pin"))] = name
    values = {c.get("ref"): c.findtext("value") for c in root.iter("comp")}

    def peers(ref, pin):
        return nets.get(where.get((ref, pin)), set()) - {(ref, pin)}

    def other(ref, pin):
        return where.get((ref, "2" if pin == "1" else "1"))

    j1 = {p: where.get(("J1", p)) for p in CABLE}
    vcc, gnd = j1["1"], "GND"
    for p in ("2", "4", "6"):
        if j1[p] != gnd:
            errors.append(f"J1.{p} should be GND")
    if vcc in (None, gnd):
        errors.append("J1.1 must be the panel supply")

    # Expander on the bus, address 0x20, reset pulled up, decoupled
    u = {k: where.get(("U1", p)) for k, p in MCP.items()}
    if u["VDD"] != vcc or u["VSS"] != gnd:
        errors.append(f"U1 supply wrong: {u['VDD']}/{u['VSS']}")
    for k, p in (("SDA", "3"), ("SCK", "5"), ("INTA", "7")):
        if u[k] != j1[p]:
            errors.append(f"U1 {k} must connect to J1.{p}")
    if any(u[a] != gnd for a in ("A0", "A1", "A2")):
        errors.append("U1 A0-A2 must be GND (address 0x20)")
    if not any(r.startswith("R") and other(r, q) == vcc for r, q in peers("U1", MCP["RESET"])):
        errors.append("U1 RESET needs a pull-up to the supply")
    if not any(r.startswith("C") and other(r, q) == gnd for r, q in nets.get(vcc, set())):
        errors.append("panel supply needs a decoupling capacitor")

    # Hardware LEDs: anode on J1.9 / J1.10, cathode GND, nothing else on the line
    for p in ("9", "10"):
        line = peers("J1", p)
        if len(line) != 1 or not next(iter(line))[0].startswith("D"):
            errors.append(f"J1.{p} must drive exactly one LED")
        else:
            d = next(iter(line))[0]
            if where.get((d, "1")) != gnd:
                errors.append(f"{d} cathode must be GND")
    # Power button straight on the cable line to GND
    if not any(r.startswith("SW") and other(r, q) == gnd for r, q in peers("J1", "8")):
        errors.append("J1.8 needs a push button to GND")

    # Expander buttons on GPA0-GPA3 to GND; LEDs on GPB0/GPB1 via resistor
    for p in ("21", "22", "23", "24"):
        if not any(r.startswith("SW") and other(r, q) == gnd for r, q in peers("U1", p)):
            errors.append(f"U1 pin {p} (GPA) needs a button to GND")
    for p in ("1", "2"):
        ok = False
        for r, q in peers("U1", p):
            if r.startswith("R"):
                led = [d for d, k in nets.get(other(r, q), set()) if d.startswith("D") and k == "2"]
                ok = bool(led) and where.get((led[0], "1")) == gnd
        if not ok:
            errors.append(f"U1 pin {p} (GPB) must drive an LED through a resistor")

    # OLED socket and I2C extension: GND VCC SCL SDA
    for ref in ("J4", "J3"):
        got = [where.get((ref, p)) for p in "1234"]
        if got != [gnd, vcc, j1["5"], j1["3"]]:
            errors.append(f"{ref} must be GND, VCC, SCL, SDA, got {got}")
    if "SSD1306" not in (values.get("J4") or ""):
        errors.append("J4 should be the SSD1306 OLED socket")

    if errors:
        print(f"{len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK: netlist matches WIRING.md rules")


if __name__ == "__main__":
    main(sys.argv[1])
