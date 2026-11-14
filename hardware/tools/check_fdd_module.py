#!/usr/bin/env python3
"""Check an exported FDD-module netlist against the rules in docs/WIRING.md.

Usage: python3 -I check_fdd_module.py <netlist.xml>
Export with: kicad-cli sch export netlist --format kicadxml -o <netlist.xml> <schematic>
Rules are written out here independently of the generator.
"""
import sys
import xml.etree.ElementTree as ET

FDD_SIGNALS = {10: "DS0", 12: "DS1", 14: "DS2", 16: "MOTOR", 18: "DIR", 20: "STEP",
               22: "WD", 24: "WG", 26: "TRK0", 28: "WP"}
OUTPUTS = {"DS0", "DS1", "DS2", "MOTOR", "DIR", "STEP"}
INPUTS = {"TRK0", "WP"}
RIBBON = {1: "DATA", 3: "CLK", 5: "LATCH", 7: "OE", 9: "PL", 11: "CLK165", 13: "Q165", 15: "spare"}

errors = []


def fail(msg):
    errors.append(msg)


def main(path):
    root = ET.parse(path).getroot()
    nets, where = {}, {}
    for n in root.iter("net"):
        nodes = {(x.get("ref"), x.get("pin")) for x in n.iter("node")}
        nets[n.get("name")] = nodes
        for node in nodes:
            where[node] = n.get("name")

    def peers(ref, pin):
        return nets.get(where.get((ref, pin)), set()) - {(ref, pin)}

    def refs(nodes, prefix):
        return {r for r, _ in nodes if r.startswith(prefix)}

    # Drive headers: J3 drives 1-2, J4 drives 3-4; wire n on IDE pin n.
    bits = []
    for header, drives in (("J3", (1, 2)), ("J4", (3, 4))):
        for slot, drive in enumerate(drives):
            for fdd in range(10, 30):
                ide = fdd - 9 if slot == 0 else fdd + 11
                net = where.get((header, str(ide)))
                if fdd % 2:
                    if net != "GND":
                        fail(f"{header}.{ide} (drive {drive} FDD pin {fdd}) should be GND, is {net}")
                    continue
                sig = FDD_SIGNALS[fdd]
                p = peers(header, str(ide))
                pull = [r for r, _ in p if r.startswith("RN")]
                if len(pull) != 1:
                    fail(f"drive {drive} {sig}: expected one pull-up, found {pull}")
                else:
                    rail_side = nets[where[(pull[0], str(9 - int([q for r, q in p if r == pull[0]][0])))]]
                    if where[next(iter(rail_side))] != "+3V3":
                        fail(f"drive {drive} {sig}: pull-up not to +3V3")
                ics = sorted((r, q) for r, q in p if r.startswith("U"))
                if sig in OUTPUTS:
                    if len(ics) != 1 or ics[0][0] not in ("U2", "U3", "U4"):
                        fail(f"drive {drive} {sig}: expected one 595 output, found {ics}")
                    else:
                        bits.append((ics[0][0], ics[0][1], f"drive {drive} {sig} (FDD {fdd})"))
                elif sig in INPUTS:
                    if len(ics) != 1 or ics[0][0] != "U5":
                        fail(f"drive {drive} {sig}: expected one 165 input, found {ics}")
                    else:
                        bits.append((ics[0][0], ics[0][1], f"drive {drive} {sig} (FDD {fdd})"))
                elif ics:
                    fail(f"drive {drive} {sig}: must not reach a register, found {ics}")

    # Ribbon IN/OUT: even pins GND, signal names per WIRING.md.
    for j in ("J1", "J2"):
        for pin in range(1, 17):
            net = where.get((j, str(pin)))
            if pin % 2 == 0 and net != "GND":
                fail(f"{j}.{pin} should be GND, is {net}")
    if "U1" not in refs(peers("J1", "1"), "U") or "U1" not in refs(peers("J1", "3"), "U"):
        fail("IN DATA/CLK must reach the buffer U1")
    if nets.get(where.get(("J1", "15"))) != {("J1", "15"), ("J2", "15")}:
        fail("ribbon pin 15 must only pass IN->OUT")
    if any(r.startswith("JP") for r, _ in where):
        fail("bench jumpers are removed; no JP parts expected")
    if ("U5", "9") not in {n for r, q in peers("J1", "13") for n in nets[where[(r, str(9 - int(q)))]]}:
        fail("IN Q165 must come from U5 QH through a series resistor")
    if ("U5", "10") not in peers("J2", "13"):
        fail("OUT Q165 must feed U5 serial input")

    # Chain: U2 QH' -> U3 SER -> U4 SER -> OUT DATA (via series resistor)
    if ("U3", "14") not in peers("U2", "9") or ("U4", "14") not in peers("U3", "9"):
        fail("595 chain U2->U3->U4 broken")
    out_data = {n for r, q in peers("U4", "9") if r.startswith("RN") for n in nets[where[(r, str(9 - int(q)))]]}
    if ("J2", "1") not in out_data:
        fail("U4 QH' must reach OUT DATA through a series resistor")

    # Supplies
    for ref, pin in (("U1", "20"), ("U2", "16"), ("U3", "16"), ("U4", "16"), ("U5", "16")):
        if where.get((ref, pin)) != "+3V3":
            fail(f"{ref}.{pin} not on +3V3")
    if where.get(("J5", "1")) != "+5V" or where.get(("J5", "2")) != "GND" or ("J5", "3") in where:
        fail("J5 (KF301, 2 poles) must be pin 1 +5V and pin 2 GND")

    # Bring-up aids: LEDs read existing nets through 1k, header J11 is a plain tap
    lit = {"D1": ("U2", "9"), "D2": ("U3", "9"), "D3": ("U4", "9"), "D4": ("U5", "9")}
    for d, (ic, pin) in lit.items():
        if where.get((d, "1")) != "GND":
            fail(f"{d} cathode must be on GND")
        rr = "R" + d[1:]
        src = where.get((ic, pin))
        if where.get((rr, "1")) != src or where.get((rr, "2")) != where.get((d, "2")):
            fail(f"{d}: expected {ic} pin {pin} -> {rr} -> LED anode")
    if where.get(("R5", "1")) != "+3V3" or where.get(("D5", "1")) != "GND" or where.get(("R5", "2")) != where.get(("D5", "2")):
        fail("D5/R5 must light from +3V3")
    if nets.get(where.get(("J11", "1"))) is None or where.get(("J11", "1")) != "+3V3" or where.get(("J11", "6")) != "GND":
        fail("J11 pin 1 must be +3V3 and pin 6 GND")
    for pin, what in (("2", ("U2", "14")), ("3", ("U2", "11")), ("4", ("U2", "12")), ("5", ("U4", "9"))):
        if where.get(("J11", pin)) != where.get(what):
            fail(f"J11 pin {pin} must share the net of {what[0]} pin {what[1]}")

    order = {"15": "QA", "1": "QB", "2": "QC", "3": "QD", "4": "QE", "5": "QF", "6": "QG", "7": "QH"}
    d165 = {"11": "D0", "12": "D1", "13": "D2", "14": "D3", "3": "D4", "4": "D5", "5": "D6", "6": "D7"}
    print("Register bits:")
    for ref, pin, what in sorted(bits, key=lambda b: (b[0], list(order).index(b[1]) if b[0] != "U5" else list(d165).index(b[1]))):
        print(f"  {ref} {(d165 if ref == 'U5' else order)[pin]} (pin {pin}): {what}")
    if errors:
        print(f"{len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK: netlist matches WIRING.md rules")


if __name__ == "__main__":
    main(sys.argv[1])
