# Surrklank PCB design

Status: **proposed design, not built or tested.** Signals, pins, pull
resistors and power wiring of the planned boards are defined in
[WIRING.md](../docs/WIRING.md); this file covers board-level design only.
Firmware does not support the module layout yet.

KiCad 10 projects:

| Folder | Content |
| --- | --- |
| `fdd-module/` | FDD module v0.1: generated schematic and autorouted 100 × 80 mm 2-layer PCB |
| `lsm-hdd-module/` | LSM/HDD module v0.1: generated schematic; PCB not started |
| `surrklank-controller/` | Empty placeholder for the mainboard |
| `lib/` | Custom symbol (DRV8833 module) and footprints (Molex 8981, DRV8833 module, Surrklank logo) |
| `tools/` | Generators, netlist check and build script |

Boards are generated, not edited by hand. One command rebuilds the FDD module
(schematic, ERC, netlist check, placement, autorouting, zone fill, DRC):

```sh
hardware/tools/build_fdd_module.sh [work_dir]
```

The LSM/HDD schematic is generated and checked the same way:

```sh
python3 -I hardware/tools/gen_lsm_hdd_module.py hardware/lsm-hdd-module/surrklank-lsm-hdd-module.kicad_sch
kicad-cli sch export netlist --format kicadxml -o /tmp/lsm.xml hardware/lsm-hdd-module/surrklank-lsm-hdd-module.kicad_sch
python3 -I hardware/tools/check_lsm_hdd_module.py /tmp/lsm.xml
```

Requirements: KiCad 10 (its bundled Python runs `gen_fdd_pcb.py`), Freerouting
2.5.0 jar in `~/.local/share/freerouting/bin/` (official GitHub release,
SHA-256 `f6f51bb0…5de3c7`) and Java 25 (`brew install openjdk@25`). The script
runs Freerouting headless with analytics and telemetry disabled. The native
Freerouting 2.5.0 CLI build fails on board serialization and is not used.

- `check_fdd_module.py` verifies the netlist against WIRING.md rules written
  independently of the generator (drive header pins, pull-ups, register chain,
  ribbon, supplies).
- Routing is not deterministic: each run gives different tracks. The build
  passes only with zero DRC violations and zero unconnected pads.
- Design rules: Default class 0.25 mm tracks / 0.2 mm clearance, Power class
  (+5V, +3V3, GND) 0.6 mm / 0.25 mm, vias 0.6/0.3 mm, minimum track 0.15 mm
  (above the 0.127 mm limit of low-cost fabs). Freerouting neck-down is disabled;
  any remaining track under 0.15 mm is widened and re-checked by DRC.
- GND is poured on both layers with solid pad connections; dense IDE header
  pins left no room for thermal spokes.
- The autorouted layout is electrically complete but not hand-optimised
  (long detours, signals near edges). It has not been reviewed for signal
  integrity or checked with a 1:1 paper print.

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

- Row spacing is **25.4 mm** (as on official DevKitC boards; many 38-pin clones
  use 22.86 mm). Measured by the user with a caliper on pin outer edges: 46.0 mm
  across 18 pitches along a row (45.72 mm nominal) and 25.5 mm across the rows,
  giving about 25.2 mm centre to centre; the nearest standard spacing is 25.4 mm.
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
| DRV8833 module | Custom `DRV8833_Module_2x6_W15.24mm`: 2 × 6, 2.54 mm pitch, rows 15.24 mm apart, 1.0 mm holes, DIP-style numbering |
| Motor outputs | 4-way 3.5 mm screw terminal per DRV8833 slot (proposal) |
| ESP32 board | Two 1 × 19 female headers, 2.54 mm pitch, rows 25.4 mm apart |

Male Molex connectors may be salvaged from HDD controller boards, where they
often share one housing with the IDE header and jumpers. Desolder the whole part
first, then cut the plastic housing; the cut-off IDE part can serve as an FDD
module header.

## Layout notes

- Front silkscreen branding: the Surrklank logo (square ring, 8 mm, drawn
  geometrically in the proportions of the user's image) with "SURRKLANK" and
  the board name and revision, in white. It is a board-only footprint, not in
  the schematic; `gen_fdd_pcb.py brand` re-applies it without rerouting.

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

- +5 V on the mainboard terminal.
- Values: mainboard series resistors, PWR_OK divider, LSM/HDD bulk capacitor.
- Parts: Schottky diode; LCSC part numbers; LDO output capacitor type.
- Drive input terminations and MOTOR behaviour on the installed drives.
- Motor supply current per LSM/HDD module and wire gauge.
- Firmware migration after assembly: six outputs per drive and a longer FDD
  chain (48 output bits for two modules), 165 chains with WRITE PROTECT and
  FAULT bits, configurable select line, EEP control, PWR_OK input on GPIO36,
  LSM/HDD Q165 on GPIO35, branch lines held LOW while ATX is off.
