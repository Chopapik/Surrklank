# Surrklank PCB design

Status: **proposed design, not built or tested.** Signals, pins, pull
resistors and power wiring of the planned boards are defined in
[WIRING.md](../docs/WIRING.md); this file covers board-level design only.
Firmware does not support the module layout yet.

The KiCad project in `surrklank-controller/` is an empty placeholder (KiCad 10.0).

## Board family

| Board | Contents |
| --- | --- |
| Mainboard | ESP32 board, ATX switch and button, PWR_OK input, 5VSB supply, one ribbon connector per branch |
| FDD module | 3 × 74HC595, 1 × 74HC165, input buffer, LDO, two 40-pin IDE headers, IN/OUT ribbon connectors, one Molex |
| LSM/HDD module | Four DRV8833 module positions, 3 × 74HC595, 1 × 74HC165, input buffer, LDO, IN/OUT ribbon connectors, one or two Molex |

At least two module designs are needed. Whether the mainboard is a third design
or is merged into one of them is not decided.

## Mainboard

ESP32 board as purchased: "ESP32-WROOM-32 38-pin, micro-USB, CP2102"
(seller code ARD-ESP32-38P), about 55.3 × 28 mm, 2 × 19 pins on 2.54 mm pitch,
pin order listed by the seller and matching the silkscreen photo.

- Row spacing is **not confirmed**: official DevKitC boards use 25.4 mm, many
  38-pin clones 22.86 mm. The 28 mm board width suggests 25.4 mm; measure before
  drawing the footprint.
- The board plugs into two 1 × 19 female headers; the USB end faces a board edge
  with clearance.
- The WROOM antenna (end opposite USB) gets no copper underneath and should
  overhang the mainboard edge, because Surrklank uses BLE.
- Power input: pluggable (two-part) screw terminal; ATX button on a two-pin connector.

## Connectors and footprints

| Part | Footprint |
| --- | --- |
| Ribbon IN/OUT | 2 × 8 IDC box header, 2.54 mm |
| FDD drive cable | Salvaged 40-pin IDE header; standard DIN 41651 2 × 20 footprint (2.54 mm pitch, 1.0 mm holes, body about 58.5 × 8.9 mm in KiCad) with extra clearance for a cut-down housing |
| Molex power | Custom: Molex 8981 family, 5.08 mm pitch, slightly enlarged holes and a few millimetres of clearance for different salvaged housings; pin tail diameter (optional measurement) can refine holes |
| DRV8833 module | Custom 2 × 6, 2.54 mm pitch, rows 15.24 mm apart, holes for 0.64 mm square header pins |
| ESP32 board | Two 1 × 19 female headers, row spacing to be measured |

Male Molex connectors may be salvaged from HDD controller boards, where they
often share one housing with the IDE header and jumpers. Desolder the whole part
first, then cut the plastic housing; the cut-off IDE part can serve as an FDD
module header.

## Layout notes

- LSM/HDD modules: wide copper from the Molex to the DRV8833 positions and a
  bulk capacitor at the input; mark the unconnected +12 V Molex position.
- Ribbon signals keep the signal/ground order of the 16-pin assignment.
- Optional test points on DATA, CLK, LATCH, /OE, +3V3 and GND are proposed for
  debugging; not decided.

## Manufacturing

SMD (factory assembly) or THT (hand soldering) is not decided. With factory
assembly, parts would be chosen from the JLCPCB/LCSC stock to limit assembly
fees; costs are not estimated yet.

## Open items

- ESP32 row spacing (25.4 or 22.86 mm); +5 V on the mainboard terminal.
- Values: pull resistors, series resistors, PWR_OK divider, bulk capacitors.
- Parts: input buffer, LDO, Schottky diode; exact register bit order.
- Drive input terminations and MOTOR behaviour on the installed drives.
- Motor supply current per LSM/HDD module and wire gauge.
- Firmware migration after assembly: six outputs per drive and a longer FDD
  chain (48 output bits for two modules), 165 chains with WRITE PROTECT and
  FAULT bits, configurable select line, EEP control, PWR_OK input on GPIO36,
  LSM/HDD Q165 on GPIO35, branch lines held LOW while ATX is off.
