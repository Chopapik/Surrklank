#!/usr/bin/env python3
"""Check an exported mainboard netlist against docs/WIRING.md (Mainboard).

Usage: python3 -I check_mainboard.py <netlist.xml>
Rules are written out here independently of the generator.
"""
import sys
import xml.etree.ElementTree as ET

# ESP32 board header (seller pin order; pins 1-19 left, 20-38 right, from the antenna end)
BOARD_PIN = {"GPIO23": "21", "GPIO22": "22", "GPIO34": "5", "GPIO17": "30", "GPIO16": "31",
             "GPIO35": "6", "GPIO18": "28", "GPIO21": "25", "GPIO33": "8", "GPIO32": "7",
             "GPIO19": "27", "GPIO13": "15", "GPIO36": "3", "3V3": "1", "5V": "19",
             "GPIO25": "9", "GPIO26": "10", "GPIO27": "11"}
# WIRING.md GPIO table: GPIO -> (branch connector or None, ribbon pin or role)
SIGNALS = {"GPIO23": ("J2", 1), "GPIO22": ("J2", 5), "GPIO34": ("J2", 13),
           "GPIO17": ("J3", 1), "GPIO16": ("J3", 5), "GPIO35": ("J3", 13)}
SHARED = {"GPIO18": 3, "GPIO21": 7, "GPIO33": 9, "GPIO32": 11}
PULL = {"GPIO21": "ESP_3V3", "GPIO33": "ESP_3V3", "GPIO18": "GND", "GPIO32": "GND",
        "GPIO22": "GND", "GPIO16": "GND", "GPIO23": "GND", "GPIO17": "GND",
        "GPIO34": "GND", "GPIO35": "GND", "GPIO13": "ESP_3V3", "GPIO27": "ESP_3V3"}
errors = []


def main(path):
    root = ET.parse(path).getroot()
    nets, where, func = {}, {}, {}
    for n in root.iter("net"):
        name = n.get("name").lstrip("/")  # local labels are exported as "/NAME"
        nodes = {(x.get("ref"), x.get("pin")) for x in n.iter("node")}
        nets[name] = nodes
        for x in n.iter("node"):
            where[(x.get("ref"), x.get("pin"))] = name
            func[(x.get("ref"), x.get("pin"))] = (x.get("pinfunction") or "").split("_")[0]

    def peers(ref, pin):
        return nets.get(where.get((ref, pin)), set()) - {(ref, pin)}

    def through(rn, pin):
        """Net on the other side of a resistor-array element."""
        return where.get((rn, str(9 - int(pin))))

    def gpio_net(g):
        return where.get(("A1", BOARD_PIN[g]))

    def reaches_via_series(g, conn, rpin):
        for r, q in peers("A1", BOARD_PIN[g]):
            if r.startswith("RN") and through(r, q) == where.get((conn, str(rpin))):
                return True
        return False

    def reaches_via_resistor(g, conn, rpin):
        """Single resistor between the GPIO and the connector pin (Q165 return)."""
        target = where.get((conn, str(rpin)))
        for r, q in peers("A1", BOARD_PIN[g]):
            if r.startswith("R") and not r.startswith("RN") \
                    and where.get((r, "2" if q == "1" else "1")) == target:
                return True
        return False

    for g, (conn, rpin) in SIGNALS.items():
        if rpin == 13:
            if not reaches_via_resistor(g, conn, rpin):
                errors.append(f"{g} must reach {conn}.13 (Q165) through a series resistor")
        elif not reaches_via_series(g, conn, rpin):
            errors.append(f"{g} must reach {conn}.{rpin} through a series resistor")
    for g, rpin in SHARED.items():
        for conn in ("J2", "J3"):
            if not reaches_via_series(g, conn, rpin):
                errors.append(f"{g} must reach {conn}.{rpin} through its own series resistor")
    for g, rail in PULL.items():
        rails = [through(r, q) for r, q in peers("A1", BOARD_PIN[g])
                 if r.startswith("RN") and through(r, q) in ("ESP_3V3", "GND")]
        if rails != [rail]:
            errors.append(f"{g}: expected one pull to {rail}, got {rails}")
    for conn in ("J2", "J3"):
        for p in range(2, 17, 2):
            if where.get((conn, str(p))) != "GND":
                errors.append(f"{conn}.{p} should be GND")
        if peers(conn, "15"):
            errors.append(f"{conn}.15 is a spare wire and must stay unconnected")

    if "+3V3" in nets or any(r.startswith("JP") and r != "JP1" for r, _ in where):
        errors.append("ATX +3V3 and the bench jumpers are removed")
    if gpio_net("3V3") != "ESP_3V3" or gpio_net("3V3") in ("+5V", "ATX_5VSB"):
        errors.append("ESP32 3V3 must stay separate from ATX +5V and +5VSB")
    # +5VSB path: terminal pin 4 -> removable jumper -> ESP32 5V, nothing else
    j1 = {p: where.get(("J1", p)) for p in "1234"}
    if [j1[p] for p in "1234"] != ["GND", "PS_ON#", "ATX_5VSB", "PWR_OK"] or ("J1", "5") in where:
        errors.append(f"J1 order wrong: {j1}")
    # +5VSB may also feed the panel standby LED resistor (checked below)
    on_5vsb = {(r, q) for r, q in nets.get("ATX_5VSB", set()) - {("J1", "3")}
               if r != "Q2" and not (r.startswith("R") and where.get((r, "2" if q == "1" else "1"))
                                     == where.get(("J6", "9")))}
    if len(on_5vsb) != 1 or not next(iter(on_5vsb))[0].startswith("JP"):
        errors.append(f"+5VSB must go only to one removable jumper, got {sorted(on_5vsb)}")
    else:
        jp = next(iter(on_5vsb))[0]
        if "ESP_5V" not in {where.get((jp, q)) for q in ("1", "2")}:
            errors.append("+5VSB jumper must lead to ESP32 5V")
    if gpio_net("5V") != "ESP_5V":
        errors.append("ESP32 5V pin must be on ESP_5V")
    # PWR_OK divider into GPIO36
    rs = [r for r, _ in nets.get("PWR_OK", set()) if r.startswith("R")
          and gpio_net("GPIO36") in {where.get((r, q)) for q in ("1", "2")}]
    if len(rs) != 1:
        errors.append("PWR_OK must reach GPIO36 through a series resistor")
    # ATX switch: GPIO19 -> R -> base, base -> R -> GND, emitter GND, collector PS_ON#
    q = next(r for r, _ in nets["PS_ON#"] if r.startswith("Q"))
    pins = {func[(q, p)]: where[(q, p)] for p in ("1", "2", "3")}
    if pins.get("C") != "PS_ON#" or pins.get("E") != "GND":
        errors.append(f"transistor pins wrong: {pins}")
    base = nets[pins["B"]]
    if not any(r.startswith("R") and gpio_net("GPIO19") in {where.get((r, x)) for x in ("1", "2")}
               for r, _ in base):
        errors.append("GPIO19 must drive the base through a resistor")
    if not any(r.startswith("R") and "GND" in {where.get((r, x)) for x in ("1", "2")} for r, _ in base):
        errors.append("base needs a resistor to GND")
    if {where.get(("J4", "1")), where.get(("J4", "2"))} != {gpio_net("GPIO13"), "GND"}:
        errors.append("button J4 must connect GPIO13 to GND")
    if not any(r.startswith("C") and "GND" in {where.get((r, x)) for x in ("1", "2")}
               for r, _ in peers("A1", BOARD_PIN["GPIO13"])):
        errors.append("button line needs a filter capacitor to GND")

    # Remote panel J6 (2 x 5): 1 ESP_3V3, 2/4/6 GND, 3 SDA, 5 SCL, 7 INT, 8 button,
    # 9 LED from +5VSB, 10 LED from ATX +5V (each through a resistor)
    if where.get(("J6", "1")) != gpio_net("3V3"):
        errors.append("J6.1 must be the ESP32 3V3")
    for p in ("2", "4", "6"):
        if where.get(("J6", p)) != "GND":
            errors.append(f"J6.{p} should be GND")
    for g, p in (("GPIO25", "3"), ("GPIO26", "5"), ("GPIO27", "7"), ("GPIO13", "8")):
        if where.get(("J6", p)) != gpio_net(g):
            errors.append(f"J6.{p} must connect directly to {g}")
    for g in ("GPIO25", "GPIO26"):
        ups = [r for r, q in peers("A1", BOARD_PIN[g]) if r.startswith("R") and not r.startswith("RN")
               and where.get((r, "2" if q == "1" else "1")) == gpio_net("3V3")]
        if len(ups) != 1:
            errors.append(f"{g} (I2C) needs one pull-up to the ESP32 3V3")
    feed = [r for r, q in peers("J6", "9") if r.startswith("R") and not r.startswith("RN")
            and where.get((r, "2" if q == "1" else "1")) == "ATX_5VSB"]
    if len(feed) != 1 or len(peers("J6", "9")) != 1:
        errors.append("J6.9 must be fed only through one resistor from ATX_5VSB")
    # J6.10: one resistor from the emitter of Q2 (collector +5VSB, base from PWR_OK via a resistor)
    feed = [(r, q) for r, q in peers("J6", "10") if r.startswith("R") and not r.startswith("RN")]
    if len(feed) != 1 or len(peers("J6", "10")) != 1:
        errors.append("J6.10 must be fed only through one resistor")
    else:
        r, q = feed[0]
        drv = where.get((r, "2" if q == "1" else "1"))
        q2 = {func[("Q2", p)]: where[("Q2", p)] for p in ("1", "2", "3")}
        if q2.get("E") != drv or q2.get("C") != "ATX_5VSB":
            errors.append(f"Q2 must be an emitter follower on +5VSB feeding J6.10, got {q2}")
        elif not any(r2.startswith("R") and "PWR_OK" in {where.get((r2, x)) for x in ("1", "2")}
                     for r2, _ in nets[q2["B"]]):
            errors.append("Q2 base must be driven from PWR_OK through a resistor")

    if errors:
        print(f"{len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK: netlist matches WIRING.md rules")


if __name__ == "__main__":
    main(sys.argv[1])
