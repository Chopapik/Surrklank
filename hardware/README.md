# Surrklank PCB design

Status: **proposed design, not built or tested.** Signals, pins, pull
resistors and power wiring of the planned boards are defined in
[WIRING.md](../docs/WIRING.md); this file covers board-level design only.
Firmware does not support the module layout yet.

KiCad 10 projects:

| Folder | Content |
| --- | --- |
| `fdd-module/` | FDD module v0.1: generated schematic and autorouted 100 × 80 mm 2-layer PCB |
| `lsm-hdd-module/` | LSM/HDD module v0.1: generated schematic and autorouted 120 × 80 mm 2-layer PCB |
| `mainboard/` | Mainboard v0.1: generated schematic and autorouted 100 × 80 mm 2-layer PCB (within the 100 × 100 mm low-cost fab class) |
| `panel/` | Remote panel v0.1: generated schematic and autorouted 100 × 59 mm 2-layer PCB |
| `surrklank-controller/` | Empty first KiCad project, superseded by `mainboard/` |
| `lib/` | Custom symbols (DRV8833 module, ESP32 38-pin board) and footprints (Molex 8981, DRV8833 module, Surrklank logo) |
| `tools/` | Generators, netlist check and build script |

Boards are generated, not edited by hand. One command rebuilds a board
(schematic, ERC, netlist check, placement, autorouting, zone fill, DRC with
schematic parity and all severities):

```sh
hardware/tools/build_fdd_module.sh [work_dir]
hardware/tools/build_lsm_hdd_module.sh [work_dir]
hardware/tools/build_mainboard.sh [work_dir]
hardware/tools/build_panel.sh [work_dir]
```

All wrap `build_module.sh fdd|lsm-hdd|mainboard|panel`, which stops at the first
failing step. Placement, zones and branding of all boards live in
`gen_module_pcb.py`.

Requirements: KiCad 10 (its bundled Python runs `gen_module_pcb.py`), Freerouting
2.5.0 jar in `~/.local/share/freerouting/bin/` (official GitHub release,
SHA-256 `f6f51bb0…5de3c7`) and Java 25 (`brew install openjdk@25`). The script
runs Freerouting headless with analytics and telemetry disabled. The native
Freerouting 2.5.0 CLI build fails on board serialization and is not used.

- `check_fdd_module.py` and `check_lsm_hdd_module.py` verify the netlist against WIRING.md rules written
  independently of the generator (drive header pins, pull-ups, register chain,
  ribbon, supplies).
- Routing is not deterministic: each run gives different tracks, and a run
  occasionally leaves a connection unrouted; rerun the build then. The build
  passes only with zero DRC violations and zero unconnected pads.
- Design rules: Default class 0.25 mm tracks / 0.2 mm clearance, Power class
  (+5V, +3V3, GND) 0.6 mm / 0.25 mm, vias 0.6/0.3 mm, minimum track 0.15 mm
  (above the 0.127 mm limit of low-cost fabs). Freerouting neck-down is disabled;
  any remaining track under 0.15 mm is widened and re-checked by DRC.
- GND is poured on both layers with solid pad connections; dense IDE header
  pins left no room for thermal spokes.
- LSM/HDD motor supply: an 8 mm wide +5V band on B_Cu runs from Molex J5 pin 4
  past C8 (+) and the VCC pins of all four DRV8833 slots to J10 pin 4. Below it
  B_Cu is a solid GND plane reaching each slot's GND pin through a notch in the
  band, plus the Molex GND pins and C8 (−). Both zones are passed to Freerouting
  as planes, and a rule area forbids B_Cu tracks and vias there, so signals
  cross on F_Cu only. The band's current capacity for the theoretical 9.6 A is
  estimated, not calculated or measured; the LDO is fed by a 0.6 mm track.
- The autorouted layout is electrically complete but not hand-optimised
  (long detours, signals near edges). It has not been reviewed for signal
  integrity or checked with a 1:1 paper print.

## Board family

| Board | Contents |
| --- | --- |
| Mainboard | ESP32 board, ATX switch and button, PWR_OK input, 5VSB supply, one ribbon connector per branch, remote panel connector |
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
- The board plugs into two 1 × 19 female headers on the left of the PCB. Its
  antenna end is flush with the top edge and the top 3.6 mm under it carries
  no copper on either layer (Surrklank uses BLE). It does not overhang: the
  body outline in the footprint is approximate, so the antenna position on
  the real board is not checked.
- Below the USB end the PCB is left free (only the silkscreen note
  "REMOVE JP1 BEFORE USB") so the micro-USB plug clears the ATX terminal.
- PCB v0.1 layout: register control resistor arrays in the middle, ribbon
  J2 (FDD) and J3 (LSM/HDD) on the right edge, ATX terminal J1 at the bottom
  edge with the plug side outward, button J4 bottom right, remote panel
  connector J6 (2 × 5 IDC, see WIRING.md) at the top edge. Autorouted, not
  hand-optimised.
- Power input: pluggable (two-part) screw terminal; ATX button on a two-pin connector.

## Remote panel

Front panel on a cable to mainboard J6 (pinout in WIRING.md). PCB v0.1,
everything on the front side:

- J1 cable header top left; socket J4 for a 0.96" SSD1306 OLED module (the
  module's 27 × 27 mm body covers the area below the socket, which carries
  only tracks); four 3 mm LEDs top right: STBY and RAILS (hardware), ATX ON
  and ESP (firmware via the expander).
- MCP23017 expander (address 0x20) with 330 Ω LED resistors; 6 mm tactile
  buttons POWER (straight to GPIO13), PREV, PLAY, STOP, NEXT (expander GPA0–3).
- J2 (JST-XH 6-pin): +3V3, GND and GPA4–GPA7 for four more buttons; J3
  (JST-XH 4-pin): I2C extension (GND, VCC, SCL, SDA) for another expander or
  sensor. Keyed JST-XH as on the LSM/HDD motor outputs, at the bottom edge. GPB2–GPB7 are unused: routing
  them to a header blocked the autorouter.
- All panel nets use the Default 0.25 mm class; the panel draws tens of mA
  and GND is poured on both layers. With 0.6 mm Power tracks Freerouting
  could not route GND between the expander and header pins and left +3V3
  unrouted as well.
- Not decided: mounting in an enclosure, front-panel cutouts, LED colours
  (Vf about 2 V needed for the hardware LEDs).

## Connectors and footprints

| Part | Footprint |
| --- | --- |
| Ribbon IN/OUT | 2 × 8 IDC box header, 2.54 mm |
| FDD drive cable | Salvaged 40-pin IDE header; standard DIN 41651 2 × 20 footprint (2.54 mm pitch, 1.0 mm holes, body about 58.5 × 8.9 mm in KiCad) with extra clearance for a cut-down housing |
| Molex power | Custom: Molex 8981 family, 5.08 mm pitch, slightly enlarged holes and a few millimetres of clearance for different salvaged housings; pin tail diameter (optional measurement) can refine holes |
| DRV8833 module | Custom `DRV8833_Module_2x6_W15.24mm`: 2 × 6, 2.54 mm pitch, rows 15.24 mm apart, 1.0 mm holes, DIP-style numbering |
| Motor outputs | JST-XH 4-pin vertical (B4B-XH-A, 2.5 mm) per DRV8833 slot; crimped plugs |
| LSM/HDD bulk capacitor | 470 µF 16 V radial THT, 10 mm diameter, 5 mm pitch |
| ESP32 board | Two 1 × 19 female headers, 2.54 mm pitch, rows 25.4 mm apart |

Male Molex connectors may be salvaged from HDD controller boards, where they
often share one housing with the IDE header and jumpers. Desolder the whole part
first, then cut the plastic housing; the cut-off IDE part can serve as an FDD
module header.

## Layout notes

- Front silkscreen branding: the Surrklank logo (square ring, 8 mm, drawn
  geometrically in the proportions of the user's image) with "SURRKLANK" and
  the board name and revision, in white. It is a board-only footprint, not in
  the schematic; `gen_module_pcb.py <board> brand` re-applies it without rerouting.
- LSM/HDD module: ribbon IN/OUT on the left and right edges, registers in a
  row above four DRV8833 slots (rotated so OUT1–OUT4 face the bottom edge),
  JST-XH motor connectors at the bottom edge, J5 bottom left with C8 beside it,
  optional J10 bottom right. The Molex footprint marks the +12 V position NC.
  The board is 120 mm wide: the Molex clearance, C8 and four 18.6 mm slots do
  not fit in 100 mm.
- Ribbon signals keep the signal/ground order of the 16-pin assignment.
- Optional test points on DATA, CLK, LATCH, /OE, +3V3 and GND are proposed for
  debugging; not decided.

## Manufacturing

SMD (factory assembly) or THT (hand soldering) is not decided. With factory
assembly, parts would be chosen from the JLCPCB/LCSC stock to limit assembly
fees; costs are not estimated yet.

`hardware/tools/export_review.py [board ...]` writes review material to
`hardware/fabrication/review/` (git-ignored): a pin-by-pin table per board from
the netlist (connectors, modules, switches, LEDs: pin name, net, what else is
on it) and an A4 PDF of copper and silkscreen at 1:1 for a paper dry fit. The
tables are generated from the schematic, so they are the thing to compare with
the real parts and breadboard wiring; `check_*.py` only compares the schematic
with WIRING.md.

`hardware/tools/export_jlcpcb.py [board ...]` writes JLCPCB upload files to
`hardware/fabrication/` (git-ignored): one Gerber and drill zip per board
(separate PTH and NPTH files), an SMD-only BOM and a CPL. Factory assembly
covers SMD only; connectors, the ESP32 board, buttons, LEDs and the DRV8833
modules stay hand-soldered.

- LCSC numbers are filled in for the FDD and LSM/HDD parts picked in the
  JLCPCB BOM editor (resistor arrays 4D03WGJ…, 74HC595/165, 74LVC244A,
  AMS1117, capacitors); the mainboard and panel parts are left for the editor
  to match.
- CPL rotations are KiCad's plus 270° for SOIC and 180° for SOT-223, read off
  the JLCPCB placement preview of the FDD module (pin-1 marker against the
  board silkscreen); not tested on a built board. SOIC-28W (panel), SOT-23
  (mainboard) and other packages are not verified: compare each pin-1 marker
  in the preview. The BOM comment is the manufacturer part number where it is
  known, because JLCPCB warns when the comment differs from the part's name.

## Open items

- Pending rebuild, decided: remove ATX +3.3 V. Mainboard J1 pin 1 becomes
  +5 V, R10 (panel LED) feeds from it, JP2/JP3 on the mainboard and JP1 on both
  modules go away, ribbon pin 15 becomes a pass-through, and `check_*.py` follow.
  The v0.1 PCB files still contain +3V3 on these parts.
- Before ordering: dry-fit the 1:1 print (`export_review.py`) with the real ESP32
  board, salvaged IDE header and Molex, terminal, buttons and OLED; measure the
  DRV8833 module J1 and EEP pull-up supply with a multimeter; compare every
  pin-1 marker in the JLCPCB placement preview.
- Parts: LCSC numbers for mainboard and panel; AMS1117 output-capacitor ESR
  requirement against the fitted 22 µF 1206 ceramic; SMD or THT assembly.
- MOTOR behaviour on the installed drives (the hand-wired assembly works with
  TRACK0 pulled up and no 595 output pull-ups).
- Motor supply current per LSM/HDD module and wire gauge.
- Firmware migration after assembly: six outputs per drive and a longer FDD
  chain (48 output bits for two modules), 165 chains with WRITE PROTECT and
  FAULT bits, configurable select line, EEP control, PWR_OK input on GPIO36,
  LSM/HDD Q165 on GPIO35, branch lines held LOW while ATX is off.
