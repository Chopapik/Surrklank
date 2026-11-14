#!/usr/bin/env python3
"""Check an exported LSM/HDD-module netlist against the rules in docs/WIRING.md.

Usage: python3 -I check_lsm_hdd_module.py <netlist.xml>
Rules are written out here independently of the generator.
"""
import sys
import xml.etree.ElementTree as ET

# Installed DRV8833 module header (top view, DIP numbering), from WIRING.md
DRV = {"1": "EEP", "2": "OUT1", "3": "OUT2", "4": "OUT3", "5": "OUT4", "6": "ULT",
       "7": "IN1", "8": "IN2", "9": "VCC", "10": "GND", "11": "IN3", "12": "IN4"}
QNAME = {"15": "QA", "1": "QB", "2": "QC", "3": "QD", "4": "QE", "5": "QF", "6": "QG", "7": "QH"}
DNAME = {"11": "D0", "12": "D1", "13": "D2", "14": "D3", "3": "D4", "4": "D5", "5": "D6", "6": "D7"}
errors = []


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

    def far_end(rn, pin):
        """Net on the other side of resistor-array element."""
        return where.get((rn, str(9 - int(pin))))

    bits = []
    for m in range(1, 5):
        drv = f"M{m}"
        term = f"J{5 + m}"
        for pin, sig in DRV.items():
            net = where.get((drv, pin))
            p = peers(drv, pin)
            if sig == "VCC":
                if net != "+5V":
                    errors.append(f"{drv} VCC on {net}, expected +5V")
            elif sig == "GND":
                if net != "GND":
                    errors.append(f"{drv} GND on {net}")
            elif sig.startswith("OUT"):
                k = sig[-1]
                if p != {(term, k)}:
                    errors.append(f"{drv} {sig} must reach only {term}.{k}, got {sorted(p)}")
            elif sig in ("IN1", "IN2", "IN3", "IN4", "EEP"):
                regs = [(r, q) for r, q in p if r in ("U2", "U3", "U4")]
                others = [(r, q) for r, q in p if not r.startswith(("U2", "U3", "U4", "RN"))]
                if len(regs) != 1 or others:
                    errors.append(f"{drv} {sig}: expected one 595 output only, got {sorted(p)}")
                else:
                    bits.append((regs[0][0], QNAME[regs[0][1]], f"M{m} {sig}"))
                pulls = [(r, q) for r, q in p if r.startswith("RN")]
                if sig == "EEP" and (len(pulls) != 1 or far_end(*pulls[0]) != "GND"):
                    errors.append(f"{drv} EEP needs one pull-down to GND, got {pulls}")
                if sig != "EEP" and pulls:
                    errors.append(f"{drv} {sig} should rely on the DRV8833 internal pull-down")
            elif sig == "ULT":
                ins = [(r, q) for r, q in p if r == "U5"]
                pulls = [(r, q) for r, q in p if r.startswith("RN")]
                if len(ins) != 1:
                    errors.append(f"{drv} ULT must reach one 165 input, got {sorted(p)}")
                else:
                    bits.append(("U5", DNAME[ins[0][1]], f"M{m} ULT (nFAULT)"))
                if len(pulls) != 1 or far_end(*pulls[0]) != "+3V3":
                    errors.append(f"{drv} ULT needs one pull-up to +3V3, got {pulls}")

    for j in ("J1", "J2"):
        for pin in range(2, 17, 2):
            if where.get((j, str(pin))) != "GND":
                errors.append(f"{j}.{pin} should be GND")
    if nets.get(where.get(("J1", "15"))) != {("J1", "15"), ("J2", "15")}:
        errors.append("ribbon pin 15 must only pass IN->OUT")
    if any(r.startswith("JP") for r, _ in where):
        errors.append("bench jumpers are removed; no JP parts expected")
    if ("U3", "14") not in peers("U2", "9") or ("U4", "14") not in peers("U3", "9"):
        errors.append("595 chain U2->U3->U4 broken")
    if ("U5", "10") not in peers("J2", "13"):
        errors.append("OUT Q165 must feed U5 serial input")
    for ref, pin in (("U1", "20"), ("U2", "16"), ("U3", "16"), ("U4", "16"), ("U5", "16")):
        if where.get((ref, pin)) != "+3V3":
            errors.append(f"{ref}.{pin} not on +3V3")
    for j in ("J5", "J10"):
        if where.get((j, "4")) != "+5V" or not (where.get((j, "1")) or "unconnected").startswith("unconnected"):
            errors.append(f"{j}: pin 4 must be +5V and pin 1 (+12V) unconnected")
    if ("U6", "3") not in nets["+5V"] or ("U6", "2") not in nets["+3V3"]:
        errors.append("LDO must take +5V and supply +3V3")

    print("Register bits:")
    for ref, q, what in sorted(bits, key=lambda b: (b[0], b[1])):
        print(f"  {ref} {q}: {what}")
    if errors:
        print(f"{len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK: netlist matches WIRING.md rules")


if __name__ == "__main__":
    main(sys.argv[1])
