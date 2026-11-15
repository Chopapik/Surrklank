# Surrklank PCB design

Status: **proposed design, not built or tested.** Signals, pins, pull
resistors and power wiring of the planned boards are defined in
[WIRING.md](../docs/WIRING.md); this file covers board-level design only.
Firmware does not support the module layout yet.

KiCad 10 projects:

| Folder | Content |
| --- | --- |
| `fdd-module/` | FDD module v0.1: generated schematic and autorouted 100 × 80 mm 2-layer PCB |
| `actuator-module/` | actuator module v0.1: generated schematic and autorouted 120 × 80 mm 2-layer PCB |
| `mainboard/` | Mainboard v0.1: generated schematic and autorouted 100 × 80 mm 2-layer PCB (within the 100 × 100 mm low-cost fab class) |
| `panel/` | Remote panel v0.1: generated schematic and autorouted 100 × 59 mm 2-layer PCB |
| `surrklank-controller/` | Empty first KiCad project, superseded by `mainboard/` |
| `lib/` | Custom symbols (DRV8833 module, ESP32 38-pin board) and footprints (KF301 screw terminals, ESP32 board, DRV8833 module, Surrklank logo) |
| `tools/` | Generators, netlist check and build script |

Boards are generated, not edited by hand. One command rebuilds a board
(schematic, ERC, netlist check, placement, autorouting, zone fill, DRC with
schematic parity and all severities):

```sh
hardware/tools/build_fdd_module.sh [work_dir]
hardware/tools/build_actuator_module.sh [work_dir]
hardware/tools/build_mainboard.sh [work_dir]
hardware/tools/build_panel.sh [work_dir]
```

All wrap `build_module.sh fdd|actuator|mainboard|panel`, which stops at the first
failing step. Placement, zones and branding of all boards live in
`gen_module_pcb.py`.

Requirements: KiCad 10 (its bundled Python runs `gen_module_pcb.py`), Freerouting
2.5.0 jar in `~/.local/share/freerouting/bin/` (official GitHub release,
SHA-256 `f6f51bb0…5de3c7`) and Java 25 (`brew install openjdk@25`). The script
runs Freerouting headless with analytics and telemetry disabled. The native
Freerouting 2.5.0 CLI build fails on board serialization and is not used.

- `check_fdd_module.py`, `check_actuator_module.py`, `check_mainboard.py` and
  `check_panel.py` verify the netlist against WIRING.md rules written
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
- Actuator module load supply: a +5V band on B_Cu (7.9 mm at its widest, 4.7 mm at the
  four GND notches, about 10 A at +20 K for 1 oz copper by an IPC-2221 estimate;
  the terminal and the PSU wire limit first, so consider 2 oz copper) runs from the two +5V
  poles of KF301 J5 past C8 (+) and the VCC pins of all four DRV8833 slots. Below it
  B_Cu is a solid GND plane reaching each slot's GND pin through a notch in the
  band, plus the two GND poles of J5 and C8 (−). Both zones are passed to Freerouting
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
| FDD module | 3 × 74HC595, 1 × 74HC165, input buffer, LDO, two 40-pin IDE headers, IN/OUT ribbon connectors, one 2-pole KF301 |
| actuator module | Four DRV8833 module positions, 3 × 74HC595, 1 × 74HC165, input buffer, LDO, IN/OUT ribbon connectors, one 4-pole KF301 |

At least two module designs are needed. Whether the mainboard is a third design
or is merged into one of them is not decided.

## Mainboard

ESP32 board as purchased: "ESP32-WROOM-32 38-pin, micro-USB, CP2102"
(seller code ARD-ESP32-38P), about 55.3 × 28 mm, 2 × 19 pins on 2.54 mm pitch,
pin order listed by the seller and matching the silkscreen photo.

- Row spacing is **24.85 mm** centre to centre (many official DevKitC boards
  and 38-pin clones differ: 25.4 and 22.86 mm also occur). Measured by the user
  with a caliper: 25.5 mm across the rows on pin outer edges (minus the 0.64 mm
  pin width) and 24.8 to 24.9 mm directly centre to centre; along a row 46.0 mm
  across 18 pitches (45.72 mm nominal). An earlier footprint used 25.4 mm and
  did not fit a paper dry fit.
- The board plugs into two 1 × 19 female headers on the left of the PCB. Its
  antenna end is flush with the top edge and the top 3.6 mm under it carries
  no copper on either layer (Surrklank uses BLE). It does not overhang: the
  body outline in the footprint is approximate, so the antenna position on
  the real board is not checked.
- Below the USB end the PCB is left free (only the silkscreen note
  "REMOVE JP1 BEFORE USB") so the micro-USB plug clears the ATX terminal (KF301 J1, x 37-58 mm, y 66-74 mm).
- PCB v0.1 layout: register control resistor arrays in the middle, ribbon
  J2 (FDD) and J3 (actuator module) on the right edge, ATX terminal J1 (KF301, 4 poles) at the bottom
  edge with the wire entry outward and labelled poles above it, button J4 bottom right, remote panel
  connector J6 (2 × 5 IDC, see WIRING.md) at the top edge. Autorouted, not
  hand-optimised.
- Power input: KF301 screw terminal on every board that takes power (mainboard 4 poles,
  FDD module 2, actuator module 4); ATX button on a two-pin connector.

## Remote panel

Front panel on a cable to mainboard J6 (pinout in WIRING.md). PCB v0.1,
everything on the front side:

- J1 cable header top left; socket J4 for a 0.96" SSD1306 OLED module (the
  module's 27 × 27 mm body covers the area below the socket, which carries
  only tracks); four 3 mm LEDs top right: STBY and RAILS (hardware), ATX ON
  and ESP (firmware via the expander).
- MCP23017 expander (address 0x20) with 330 Ω LED resistors; 6 mm tactile
  buttons POWER (straight to GPIO13), PREV, PLAY, STOP, NEXT (expander GPA0–3).
- J2 (JST-XH 6-pin): +3V3, GND and GPA4–GPA7 (GPA7 is output only, so three
  more buttons); J3
  (JST-XH 4-pin): I2C extension (GND, VCC, SCL, SDA) for another expander or
  sensor. Keyed JST-XH as on the actuator module outputs, at the bottom edge. GPB2–GPB7 are unused: routing
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
| Power input | Custom `TerminalBlock_KF301_1xNN_P5.08mm_Horizontal` (2 and 4 poles, from `gen_terminal_footprints.py`): 5.08 mm pitch, 3.0 mm pads, 1.4 mm holes, generic body about 8 mm deep with the wires entering from the +y side; check against the bought part |
| DRV8833 module | Custom `DRV8833_Module_2x6_W15.24mm`: 2 × 6, 2.54 mm pitch, rows 15.24 mm apart, 1.0 mm holes, DIP-style numbering |
| Motor outputs | JST-XH 4-pin vertical (B4B-XH-A, 2.5 mm) per DRV8833 slot; crimped plugs |
| Actuator module bulk capacitor | 470 µF 16 V radial THT, 10 mm diameter, 5 mm pitch |
| ESP32 board | Two 1 × 19 female headers, 2.54 mm pitch, rows 24.85 mm apart |

Salvaged male Molex headers turned out to be SMD, so every power input is a
KF301 screw terminal (see WIRING.md, Power). A cut-off IDE part can still serve
as an FDD module header.

## Layout notes

- Silkscreen branding, white, board-only footprints (not in the schematic):
  the Surrklank mark (10 mm frame with the beamed-notes glyph, 55 % of the frame
  height, footprint `Surrklank_Mark_10mm` from `gen_logo_footprints.py`) with the
  wordmark "Surrklank" and the board name and revision below it, and the author
  mark (8 mm square ring, `Surrklank_Logo_8mm`) with a small italic "by" in its
  upper-left corner. The author mark is on the back of every board, the front
  carries only the Surrklank mark.
  `gen_module_pcb.py <board> brand` re-applies them without rerouting. Wordmark
  and "by" are TrueType text (Arial bold, Georgia bold italic) outlined in the
  Gerbers; a different font on another machine changes their shape.
- actuator module: ribbon IN/OUT on the left and right edges, registers in a
  row above four DRV8833 slots (rotated so OUT1–OUT4 face the bottom edge),
  JST-XH motor connectors at the bottom edge, 4-pole KF301 J5 at the left edge
  with C8 beside it. Every pole is labelled with its function (+5V or GND) to
  the right of the terminal body. The board is 120 mm wide: C8 and four 18.6 mm
  slots do not fit in 100 mm.
- Ribbon signals keep the signal/ground order of the 16-pin assignment.
- Both modules carry bring-up aids: LEDs D1-D5 (register serial outputs, 165
  return, 3.3 V) at the registers and header J11 (3V3, DATA, CLK, LATCH, end of
  chain, GND). The FDD module stays 100 x 80 mm, within the 100 x 100 mm limit.

## Manufacturing

There is no factory assembly: bare boards are ordered and every part is bought
separately and soldered by hand (SOIC, 0603 and SOT-223 included). The BOM
written by `export_jlcpcb.py` doubles as a shopping list.

`hardware/tools/export_review.py [board ...]` writes review tables to
`hardware/fabrication/review/` (git-ignored): a pin-by-pin table per board from
the netlist (connectors, modules, switches, LEDs: pin name, net, what else is
on it). The tables are generated from the schematic, so they are the thing to
compare with the real parts and breadboard wiring; `check_*.py` only compares
the schematic with WIRING.md.

`hardware/tools/export_dryfit.py` (run with KiCad's Python, which provides
`pcbnew`) writes `surrklank-dryfit-a4-1to1.pdf` to the same folder: one A4
landscape sheet with all four boards at true size for a paper dry fit. Black
lines are the board edge, footprint outlines and mounting holes; red circles
are through-hole pads with their drills; tracks and SMD parts are left out to
save ink. A 10 cm ruler along both axes shows whether the printer rescaled the
page: print at 100 % / actual size, never fit to page.

`hardware/tools/export_jlcpcb.py [board ...]` writes upload files to
`hardware/fabrication/` (git-ignored): one Gerber and drill zip per board
(separate PTH and NPTH files, paste layers included), plus an SMD BOM and CPL
that are only needed if factory assembly is used. The BOM carries only
LCSC numbers whose JLCPCB class was read as Basic or Promotional (Preferred)
Extended on 2026-11-15 (class and stock change, recheck before ordering);
the only Promotional part is the 74HC165 (C5613), which is free of the
loading fee in Economic assembly only. Four part types have no Basic or
Promotional option and stay without a number, listed in `UNRESOLVED` in the
script with their Extended candidates (extra fee per unique part type):
74LVC244A (SOIC-20W) on both modules, the 33 Ω 0603 × 4 array (mainboard and
both modules), the 100 k 0603 × 4 array (actuator module) and the panel's
MCP23017-E/SO. These parts are left out of the assembly BOM and CPL and listed
in `bom/surrklank-<board>-hand-solder.csv`: the factory places only Basic and
Promotional parts and these are soldered by hand. CPL rotation offsets are verified only for
SOIC-16/20 and SOT-223; SOT-23, resistor arrays and SOIC-28W must be checked
in the JLCPCB placement preview.

## Open items

- Before ordering: dry-fit the 1:1 sheet (`export_dryfit.py`) with the real ESP32
  board, salvaged IDE header, KF301 terminals, buttons and OLED; measure the
  DRV8833 module J1 and EEP pull-up supply with a multimeter.
- Parts: AMS1117 with the 22 µF 1206 ceramic is untested (datasheet silent on
  ceramics; scope the 3.3 V rail of the first module).
- Power input: KF301 pole and body size against the bought terminals (generic values in the footprints).
- MOTOR behaviour on the installed drives (the hand-wired assembly works with
  TRACK0 pulled up and no 595 output pull-ups).
- Motor supply current per actuator module and wire gauge.
- Firmware migration after assembly: six outputs per drive and a longer FDD
  chain (48 output bits for two modules), 165 chains with WRITE PROTECT and
  FAULT bits, configurable select line, EEP control, PWR_OK input on GPIO36,
  actuator Q165 on GPIO35, DATA, CLK, LATCH and CLK165 held LOW (and /OE and
  /PL HIGH) while ATX is off.
