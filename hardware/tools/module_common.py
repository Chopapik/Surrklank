"""Blocks shared by the chained module schematics (ribbon, buffer, power).

Nets follow docs/WIRING.md. The FDD generator still contains its own copy of
these blocks so its symbol UUIDs (and PCB links) stay stable; new modules use
this file.
"""

FP_SOIC16 = "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm"
FP_SOIC20W = "Package_SO:SOIC-20W_7.5x12.8mm_P1.27mm"
FP_C = "Capacitor_SMD:C_0805_2012Metric"
FP_C1206 = "Capacitor_SMD:C_1206_3216Metric"
FP_RN = "Resistor_SMD:R_Array_Convex_4x0603"
FP_IDC16 = "Connector_IDC:IDC-Header_2x08_P2.54mm_Vertical"
FP_MOLEX = "surrklank:Molex_8981_1x04_P5.08mm_Vertical"
FP_HOLE = "MountingHole:MountingHole_3.2mm_M3"

QPINS = ["15", "1", "2", "3", "4", "5", "6", "7"]   # 595 QA..QH
D165 = ["11", "12", "13", "14", "3", "4", "5", "6"]  # 165 D0..D7
RIBBON = {1: "DATA", 3: "CLK", 5: "LATCH", 7: "OE", 9: "PL", 11: "CLK165", 13: "Q165", 15: "SPARE"}


def pack(sh, ref, value, x, y, bottom, top=None, rail=None):
    """R_Pack04: bottom pins 1-4 get nets; top pins 8-5 go to a rail or own nets."""
    rn = sh.symbol("Device:R_Pack04", ref, value, x, y, footprint=FP_RN)
    for k in range(4):
        b, t = str(k + 1), str(8 - k)
        if bottom[k] is None:
            sh.no_connect(rn, b)
            if rail is None:
                sh.no_connect(rn, t)
            continue
        sh.connect(rn, b, bottom[k])
        if rail is None:
            sh.connect(rn, t, top[k])
    if rail is not None:
        tops = [rn.pin(str(8 - k))["pos"] for k in range(4)]
        for a, b in zip(tops, tops[1:]):
            sh.wire(a, b)
        sh.connect(rn, "8", rail)
    return rn


def ribbon_and_buffer(sh):
    """J1 IN, J2 OUT, buffer U1, pulls RN1/RN2, series RN3/RN4.

    Exposes buffered nets B_DATA, B_CLK, B_LATCH, B_OE, B_PL, B_CLK165 and
    expects the module to provide SR_LAST (last 595 QH'), Q165_LOCAL (165 QH)
    and to use Q165_NEXT (165 serial input).
    """
    for ref, x, y, side in (("J1", 38.1, 50.8, "IN"), ("J2", 38.1, 101.6, "OUT")):
        j = sh.symbol("Connector_Generic:Conn_02x08_Odd_Even", ref, f"RIBBON_{side}", x, y,
                      footprint=FP_IDC16)
        for p in range(1, 17):
            if p % 2 == 0:
                sh.connect(j, str(p), "GND")
            elif RIBBON[p] == "SPARE":
                sh.connect(j, str(p), "RIB_SPARE")   # unused wire, passes IN -> OUT
            elif RIBBON[p] == "Q165":
                sh.connect(j, str(p), "Q165" if side == "IN" else "Q165_NEXT")
            else:
                sh.connect(j, str(p), f"{side}_{RIBBON[p]}")
    sh.text("Ribbon pin 15 is a spare wire: IN and OUT are joined, nothing else.\n"
            "No power runs on the ribbon.", (25.4, 148.59))

    u1 = sh.symbol("74xx:74AHC244", "U1", "74LVC244A", 111.76, 63.5, footprint=FP_SOIC20W)
    for a, y_, s in (("2", "18", "DATA"), ("4", "16", "CLK"), ("6", "14", "LATCH"), ("8", "12", "OE"),
                     ("17", "3", "PL"), ("15", "5", "CLK165")):
        sh.connect(u1, a, f"IN_{s}")
        sh.connect(u1, y_, f"B_{s}")
    for a, y_ in (("13", "7"), ("11", "9")):
        sh.connect(u1, a, "GND")
        sh.no_connect(u1, y_)
    for pin in ("1", "19", "10"):
        sh.connect(u1, pin, "GND")
    sh.connect(u1, "20", "+3V3")

    pack(sh, "RN1", "10k", 96.52, 116.84, ["IN_DATA", "IN_CLK", "IN_LATCH", "IN_CLK165"], rail="GND")
    pack(sh, "RN2", "10k", 127.0, 116.84, ["IN_OE", "IN_PL", "Q165_NEXT", None], rail="+3V3")
    pack(sh, "RN3", "33", 96.52, 152.4, ["B_CLK", "B_LATCH", "B_OE", "B_PL"],
         top=["OUT_CLK", "OUT_LATCH", "OUT_OE", "OUT_PL"])
    pack(sh, "RN4", "33", 127.0, 152.4, ["B_CLK165", "SR_LAST", "Q165_LOCAL", None],
         top=["OUT_CLK165", "OUT_DATA", "Q165", None])


def register(sh, ref, x, y, ser_in, ser_out, outputs):
    """74HC595 on the buffered bus; outputs: 8 net names (None = unused)."""
    u = sh.symbol("74xx:74HC595", ref, "74HC595", x, y, footprint=FP_SOIC16)
    sh.connect(u, "14", ser_in)
    sh.connect(u, "11", "B_CLK")
    sh.connect(u, "12", "B_LATCH")
    sh.connect(u, "13", "B_OE")
    sh.connect(u, "10", "+3V3")
    sh.connect(u, "16", "+3V3")
    sh.connect(u, "8", "GND")
    sh.connect(u, "9", ser_out)
    for q, n in zip(QPINS, outputs):
        if n is None:
            sh.no_connect(u, q)
        else:
            sh.connect(u, q, n)
    return u


def input_register(sh, ref, x, y, inputs):
    """74HC165; inputs: 8 net names for D0..D7."""
    u = sh.symbol("74xx:74HC165", ref, "74HC165", x, y, footprint=FP_SOIC16)
    for pin, n in zip(D165, inputs):
        sh.connect(u, pin, n)
    sh.connect(u, "10", "Q165_NEXT")
    sh.connect(u, "1", "B_PL")
    sh.connect(u, "2", "B_CLK165")
    sh.connect(u, "15", "GND")
    sh.connect(u, "9", "Q165_LOCAL")
    sh.no_connect(u, "7")
    sh.connect(u, "16", "+3V3")
    sh.connect(u, "8", "GND")
    return u


def molex(sh, ref, x, y):
    j = sh.symbol("Connector_Generic:Conn_01x04", ref, "MOLEX_5V", x, y, footprint=FP_MOLEX)
    sh.no_connect(j, "1")
    sh.connect(j, "2", "GND")
    sh.connect(j, "3", "GND")
    sh.connect(j, "4", "+5V")
    return j


def ldo(sh, x, y):
    """AMS1117-3.3 from +5V with input/output capacitors C6/C7."""
    u6 = sh.symbol("Regulator_Linear:AMS1117-3.3", "U6", "AMS1117-3.3", x, y,
                   footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2")
    sh.connect(u6, "3", "+5V")
    sh.connect(u6, "2", "+3V3")
    sh.connect(u6, "1", "GND")
    for ref, val, cx, net, fp in (("C6", "10u", x - 15.24, "+5V", FP_C), ("C7", "22u", x + 15.24, "+3V3", FP_C1206)):
        c = sh.symbol("Device:C", ref, val, cx, y + 15.24, footprint=fp)
        sh.connect(c, "1", net)
        sh.connect(c, "2", "GND")


def decoupling(sh, count, x0, y):
    for i in range(count):
        c = sh.symbol("Device:C", f"C{i + 1}", "100n", x0 + i * 10.16, y, footprint=FP_C)
        sh.connect(c, "1", "+3V3")
        sh.connect(c, "2", "GND")
    sh.text(f"C1-C{count}: 100 nF next to U1-U{count} supply pins.", (x0 - 2.54, y + 15.24))


FP_LED = "LED_SMD:LED_0603_1608Metric"
FP_R = "Resistor_SMD:R_0603_1608Metric"
FP_TEST = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical"
# Bring-up header J11, pin 6 is GND (end pin, easy for a clip lead)
TEST_PINS = ["+3V3", "B_DATA", "B_CLK", "B_LATCH", "SR_LAST", "GND"]
# (LED, resistor, net lit, label): the serial output of each 595, the 165 return, the rail
DIAG_LEDS = [("D1", "R1", "SR1", "U2 QH'"), ("D2", "R2", "SR2", "U3 QH'"),
             ("D3", "R3", "SR_LAST", "U4 QH'"), ("D4", "R4", "Q165_LOCAL", "U5 QH"),
             ("D5", "R5", "+3V3", "3V3")]


def diagnostics(sh, x, y, last="SR_LAST"):
    """Bring-up aids: one LED per register output plus a 3V3 LED, and header J11.

    Each LED sits on a net that already exists (no new logic): the serial
    output of every 595 (QH'), the 165 return (QH) and the 3.3 V rail. The
    header exposes the buffered bus and the end of the chain for a probe.
    """
    for i, (dref, rref, lit, label) in enumerate(DIAG_LEDS):
        net = last if lit == "SR_LAST" else lit
        yy = y + i * 7.62
        r = sh.symbol("Device:R", rref, "1k", x, yy, angle=90, footprint=FP_R)
        sh.connect(r, "1", net)
        sh.connect(r, "2", f"LED_{dref}")
        d = sh.symbol("Device:LED", dref, "LED", x + 20.32, yy, angle=180, footprint=FP_LED)
        sh.connect(d, "name:A", f"LED_{dref}")
        sh.connect(d, "name:K", "GND")
    j = sh.symbol("Connector_Generic:Conn_01x06", "J11", "TEST", x + 60.96, y + 12.7, footprint=FP_TEST)
    for pin, net in enumerate(TEST_PINS, start=1):
        sh.connect(j, str(pin), last if net == "SR_LAST" else net)
    sh.text("D1-D4 show the level on the serial output of U2, U3, U4 (QH') and the 165 return (QH);\n"
            "D5 shows 3.3 V. Use LEDs with Vf up to about 2.2 V (red, yellow, green).\n"
            "J11: 3V3, buffered DATA, CLK, LATCH, end of chain, GND.", (x - 5.08, y + 41.28))


def mounting_holes(sh, x0, y):
    for i in range(4):
        sh.symbol("Mechanical:MountingHole", f"H{i + 1}", "M3", x0 + i * 10.16, y, footprint=FP_HOLE)
