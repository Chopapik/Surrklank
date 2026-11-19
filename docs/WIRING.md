# Wiring map

This branch (`pcb-modules`) describes the **planned PCB wiring**: a mainboard
and chained FDD and actuator modules. Nothing here is built or tested yet.
Firmware on this branch implements this wiring for two FDD modules (FDD1–8) and
keeps the actuator branch cleared; it no longer matches the hand-wired assembly
recorded in `docs/WIRING.md` on `main` (commit `30f4cbc`). See
[FIRMWARE.md](FIRMWARE.md#fdd-laboratory). Board-level design (footprints,
salvaged connectors, manufacturing) is in [hardware/README.md](../hardware/README.md).

Keep the assembly isolated from the ESP32 during firmware maintenance (see
[Maintenance](#maintenance)).

## Instrument names

**LSM (Lead-Screw Motor)** is this project's short label for a miniature
stepper motor with a lead screw, removed from an optical disc drive. It does
not mean a complete DVD drive or every type of stepper motor. FDD refers to
the complete floppy-drive assembly. Each of the four LSM motors has a separate
control channel; a shared resonating enclosure does not make them one channel.

Older `DVD1`–`DVD4` labels correspond to `LSM1`–`LSM4`. Wiring addresses
`SLED 1`–`SLED 4` and internal `dvd_data`/`dvd_latch` names are retained.
The display terminology does not add LSM playback support.

## System overview

```text
mainboard ──16-pin ribbon── FDD module 1 ──ribbon── FDD module 2 ── … FDD module N
          └─16-pin ribbon── actuator module 1 ──ribbon── … actuator module N ── LED board
```

- Two branches leave the mainboard on separate long, flexible ribbons
  (modules can move around a roughly 50 × 50 cm area).
- Every module has identical IN and OUT connectors; modules of one branch are
  daisy-chained. Module 1 is closest to the mainboard.
- An FDD module serves four drives; two FDD modules serve the current eight.
- An actuator module carries up to four DRV8833 driver modules.
- A proposed perfboard LED board ends the actuator branch (see
  [Running-LED board](#running-led-board-proposed)).
- ESP32, modules, drivers and drives share GND.

## Mainboard

### ESP32 GPIO

| GPIO | Function | Status |
| --- | --- | --- |
| 23 | FDD branch DATA | as today |
| 22 | FDD branch LATCH | as today |
| 34 | FDD branch Q165 (input only) | as today |
| 17 | actuator branch DATA | as today |
| 16 | actuator branch LATCH | as today |
| 35 | actuator branch Q165 (input only) | new, proposed |
| 18 | CLK, both branches | as today |
| 21 | /OE, both branches | as today |
| 33 | /PL, both branches | as today (FDD only) |
| 32 | CLK165, both branches | as today (FDD only) |
| 19 | ATX PS_ON# transistor | as today |
| 13 | ATX button | as today |
| 36 | PWR_OK via divider (input only; GPIO39 is the alternative) | new, proposed |
| 25 | Remote panel I2C SDA | new, proposed |
| 26 | Remote panel I2C SCL | new, proposed |
| 27 | Remote panel expander INT (input, 10 kΩ pull-up) | new, proposed |

A GPIO shared by both branches drives each ribbon through its own series
resistor. GPIO34–39 have no internal pull resistors.

### Default levels on the mainboard

Pull resistors on the mainboard keep register control lines inactive while the
ESP32 boots or a GPIO is high impedance. They use the ESP32 board's own 3.3 V
(`ESP_3V3`), which is powered whenever the ESP32 runs, not ATX +3.3 V:

| Signal | Resistor | Level without active drive |
| --- | --- | --- |
| /OE | 10 kΩ pull-up to ESP_3V3 | HIGH: 595 outputs high impedance |
| /PL | 10 kΩ pull-up | HIGH: parallel load inactive |
| CLK, CLK165 | 10 kΩ pull-down | LOW |
| LATCH (each branch) | 10 kΩ pull-down | LOW |
| DATA (each branch) | 10 kΩ pull-down | LOW |
| Q165 (each branch) | 10 kΩ pull-down | LOW with no module connected |
| Button (GPIO13) | 10 kΩ pull-up to ESP_3V3, 100 nF to GND | HIGH: released |

Q165 returns from each ribbon through a 1 kΩ series resistor, which limits
current if a powered module drives an unpowered ESP32 (bench jumper, JP1
removed). With the pull-down on the GPIO side a module HIGH reads about 3.0 V.

### Power input

A KF301 screw terminal (4 poles, 5.08 mm, J1) brings GND, PS_ON#, +5VSB and
PWR_OK from the user's ATX distribution. ATX +5 V and +3.3 V do not reach the
mainboard: the modules take +5 V from their own terminals and make their own 3.3 V.

- **+5VSB → ESP32.** The ATX standby rail powers the ESP32 board through a
  removable jumper (JP1) into the board's 5 V pin, so the ESP32 runs while ATX
  main rails are off. There is no diode: it would only block one direction
  and its 0.3–0.45 V drop would leave the ESP32 board's 3.3 V regulator
  (likely AMS1117, about 1.1 V dropout) near its limit. **Remove JP1 before
  plugging in USB**, also with ATX unplugged from the mains: it is the only
  isolation between USB 5 V and the ATX standby rail. The ESP32 board is
  assumed to have no USB VBUS diode (seller warning); this is not verified.
- Never connect any supply to the ESP32 board's 3V3 pin; the board's 5 V pin
  takes +5VSB through JP1 only.
- **PWR_OK** (grey ATX wire, nominally 5 V logic) reaches GPIO36 through a
  10 kΩ / 20 kΩ divider (about 3.3 V from 5 V). It reports main rails up,
  unlike the GPIO19 request. Firmware enables the module bus only while it is
  HIGH, because module logic runs from the main rails: earlier writes would
  reach unpowered modules, and their 595s power up in an undefined state. It
  reports the level as `pwr_ok`. It reads actuator Q165 (GPIO35) for DRV8833
  ULT faults; see [FIRMWARE.md](FIRMWARE.md#fdd-laboratory).

### ATX power switch and button

ATX starts OFF in firmware, and a maintenance lock forces OFF and rejects ON
until the next ESP32 restart.

Schematic: `hardware/mainboard/surrklank-mainboard.kicad_sch` (generated, v0.1).
The PCB uses an MMBT3904 (SOT-23) in place of the hand-wired S8050.

```text
ESP32 GPIO19 ── 2.2 kΩ ── S8050 base
                              │
                           47–100 kΩ
                              │
Common GND ────────────── S8050 emitter
ATX PS_ON# ────────────── S8050 collector
```

GPIO19 HIGH turns the transistor on and requests ATX ON; LOW releases PS_ON#,
requesting OFF. This is a command, not a rail measurement. PS_ON# is
conventionally the green ATX wire; identify it by connector function and never
connect it directly to a GPIO. Use the actual transistor's pinout.

```text
ESP32 GPIO13 ── normally-open momentary button ── ESP32 GND
```

GPIO13 has a 10 kΩ external pull-up and 100 nF to GND on the mainboard (the
internal pull-up alone is weak for a cable near the motors): released HIGH,
pressed LOW. Each debounced
press toggles the ATX request. A button held during startup must be released
before it can request ON. It is a software input, not a power isolator. The
button connects to the mainboard through a two-pin connector.

### Standby power and module back-powering

With the ESP32 on standby power, module logic is unpowered while ATX is off.
Ribbon signals must not back-power modules through register inputs. Planned
measures: a module input buffer with power-off protection (a 74LVC244A-class
part with Ioff) and 33 Ω series resistors on the mainboard outputs are in the
design. Open: the mainboard pull-ups on /OE and /PL reach the module's own
10 kΩ pull-ups (module RN2) through the 33 Ω resistors and can lift the
unpowered module's 3.3 V rail; the level reached is not measured. Firmware must
drive DATA, CLK, LATCH and CLK165 LOW while ATX is off, and must keep /OE and
/PL HIGH: /OE LOW would enable the 595 outputs of a module that is powering up.

### Remote panel

An optional panel on a cable of about 1–2 m brings the ATX button, status
LEDs and later an I2C display and buttons closer to the user. Instruments stay
on the 595/165 chains: I2C is too slow for STEP timing (100 µs motion tick,
two frames per STEP) and is used only for this slow user interface. Panel
schematic: `hardware/panel/surrklank-panel.kicad_sch` (generated, v0.1); the
mainboard connector is J6 (2 × 5 IDC, straight-through ribbon to panel J1):

| Pin | Signal | Pin | Signal |
| --- | --- | --- | --- |
| 1 | ESP_3V3 (panel logic) | 2 | GND |
| 3 | SDA (GPIO25) | 4 | GND |
| 5 | SCL (GPIO26) | 6 | GND |
| 7 | INT (GPIO27) | 8 | ATX button (GPIO13, parallel to J4) |
| 9 | LED anode, 1 kΩ from +5VSB | 10 | LED anode, 470 Ω from Q2 emitter |

- I2C runs at 100 kHz with 2.2 kΩ pull-ups to ESP_3V3 on the mainboard, which
  keeps rise time within the standard-mode limit for about 2 m of ribbon; a
  bus buffer is not planned. Planned panel parts: 0.96" SSD1306 OLED (I2C,
  usually address 0x3C) and an MCP23017/PCF8574 expander for buttons and LEDs.
- Pin 9 lights while +5VSB is present and pin 10 while ATX main rails are up
  (measured rail, not the GPIO19 request); both work without firmware. Pin 10
  is driven by Q2 (MMBT3904 emitter follower, collector +5VSB, base from PWR_OK
  through 1 kΩ), so the weak PWR_OK output carries only the base current
  (about 50 µA). It draws about 5 mA at Vf 2 V and follows PWR_OK, not +5 V. Panel
  LEDs connect to GND and should have Vf about 2 V (red, green or yellow).
- Panel expander U1 (MCP23017, address 0x20, INTA on the INT line with
  IOCON.MIRROR, internal pull-ups for buttons): GPA0 PREV, GPA1 PLAY, GPA2 STOP,
  GPA3 NEXT (buttons to GND, active LOW), GPA4–GPA7 spare on J2 (GPA7 is
  output only on the MCP23017, so only GPA4–GPA6 can be buttons), GPB0 ATX ON
  request LED, GPB1 ESP32 activity LED (through 330 Ω), GPB2–GPB7 unused.
- The POWER button on the panel is wired straight to GPIO13, parallel to J4,
  so it works without I2C.
- OLED socket J4 and I2C extension J3: GND, VCC, SCL, SDA. Some SSD1306
  modules swap GND and VCC; check the module before plugging it in.
- Firmware supports the buttons and the ATX ON and ESP LEDs, not the OLED yet;
  the panel is required at ESP32 start (see
  [FIRMWARE.md](FIRMWARE.md#remote-panel)).

## Module ribbon (16-pin)

Both branches use the same 2 × 8 IDC ribbon. Every signal runs next to a ground
wire. Use shrouded (keyed) box headers only: unkeyed pin strips allow a plug
turned 180° or crimped on the wrong face, which puts GPIO outputs on GND (and,
on the panel cable, the ESP32 3.3 V rail on GND). Pin assignment:

| Pin | Signal | Pin | Signal |
| --- | --- | --- | --- |
| 1 | DATA | 2 | GND |
| 3 | CLK | 4 | GND |
| 5 | LATCH | 6 | GND |
| 7 | /OE | 8 | GND |
| 9 | /PL | 10 | GND |
| 11 | CLK165 | 12 | GND |
| 13 | Q165 | 14 | GND |
| 15 | Reserved (spare wire, passes IN to OUT) | 16 | GND |

On each module:

- DATA, CLK, LATCH, /OE, /PL and CLK165 from IN pass through the input buffer
  to the module's registers and to OUT.
- The last 595's QH′ drives DATA on OUT.
- The 165's QH drives Q165 on IN; its serial input (SER, pin 10) takes Q165
  from OUT, with a pull resistor so an open OUT reads a defined level.
- Modules are powered locally from their own KF301 screw terminal; no power runs on the
  ribbon. Pin 15 is a spare wire that passes straight through each module and
  is unconnected on the mainboard.

Mainboard outputs and module OUT outputs have 33 Ω series resistors (mainboard
RN4–RN7, module RN3/RN4); the module input buffer is a 74LVC244A (U1). The
buffer re-drives every signal, so each ribbon hop is an independent
point-to-point link and lengths do not add up. Whether its inputs have
hysteresis depends on the maker: the fitted Nexperia part (LCSC C548504) states
Schmitt-trigger action without giving a hysteresis value, and the TI part has
standard CMOS inputs. Treat it as a repeater, not a filter, for ringing that
crosses its input threshold.

### Crimping the ribbon

The ribbon is straight-through: wire *w*, counted from the red wire, lands on
pin *w* at both ends. The red wire is pin 1 (DATA), wire 2 is GND and wire 16
is GND.

- Put both IDC sockets on the **same face** of the ribbon, each with its pin-1
  triangle at the red wire.
- A socket on the opposite face swaps odd and even pins within each pair (1↔2,
  3↔4, …), putting every signal on a ground pin and every ground on a signal
  pin. This is standard IDC behaviour, not tested on this hardware.
- A socket turned 180° in the plane maps wire *w* to pin 17 − *w*.
- Check all 16 wires for continuity and neighbour shorts before first use.

### Signal integrity

Expected lengths: about 50 cm from the mainboard to module 1 and up to about
100 cm between modules; the panel cable is longer (up to about 2 m) but carries
only slow I2C. No measurement exists, so the following is a plan, not a result.

1. Acceptance is functional: the longest planned ribbons, every module
   connected, motors under load and long runs of motion, counting wrong or
   missing steps and unexpected outputs.
2. Changes that need no new boards, in this order: keep ribbons away from motor
   supply wires and cross them at right angles; use a thick, short power GND
   wire so the ribbon GND wires carry almost no motor return current; replace
   the 33 Ω series arrays with 47–68 Ω to slow the edges; add ferrite clamps;
   slow CLK in firmware if the frame budget allows (not checked).
3. Diagnosis needs an oscilloscope of at least 100 MHz with a short probe
   ground spring: look for ringing on CLK and LATCH at the far end of the
   longest hop crossing about 1.65 V. A logic analyser samples too slowly for
   this.
4. Board changes (a Schmitt-trigger buffer or optional RC filters on CLK,
   LATCH, CLK165 and /PL) are not planned.

## FDD module

Each module serves four drives with 3 × 74HC595 (24 outputs, six per drive) and
1 × 74HC165 (8 inputs, two per drive). Schematic:
`hardware/fdd-module/surrklank-fdd-module.kicad_sch` (generated, v0.1).

### Register bit order

U2 is first in the chain (its SER takes buffered DATA); U2 QH′ → U3 SER →
U4 SER, and U4 QH′ drives OUT DATA.

| Register | QA | QB | QC | QD | QE | QF | QG | QH |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| U2 | D1 DS0 | D1 DS1 | D1 DS2 | D1 MOTOR | D1 DIR | D1 STEP | D2 DS0 | D2 DS1 |
| U3 | D2 DS2 | D2 MOTOR | D2 DIR | D2 STEP | D3 DS0 | D3 DS1 | D3 DS2 | D3 MOTOR |
| U4 | D3 DIR | D3 STEP | D4 DS0 | D4 DS1 | D4 DS2 | D4 MOTOR | D4 DIR | D4 STEP |

| 165 input | D0 | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| U5 | D1 TRACK0 | D1 WP | D2 TRACK0 | D2 WP | D3 TRACK0 | D3 WP | D4 TRACK0 | D4 WP |

D1–D4 are the module's drive positions: J3 serves D1–D2, J4 serves D3–D4.
U5 serial input (DS) takes Q165 from the OUT connector; U5 QH drives Q165 on IN
through a 33 Ω resistor.

### Module circuit

- Input buffer U1 (74LVC244A, SOIC-20W, 74AHC244 symbol with the same pinout)
  re-drives DATA, CLK, LATCH, /OE, /PL and CLK165; its enables are tied LOW.
- Ribbon inputs have pull resistors (10 kΩ) on the module: DATA, CLK, LATCH and
  CLK165 to GND; /OE, /PL and the chained Q165 to 3.3 V.
- Buffered CLK, LATCH, /OE, /PL, CLK165 and U4 QH′ reach OUT through 33 Ω.
- Power: KF301 J5 (2 poles, +5 V and GND) → AMS1117-3.3 (10 µF in, 22 µF out); 100 nF per IC.
- Parts are SMD (SOIC, 0805, 4 × 0603 resistor arrays) except connectors.
- Bring-up aids: five 0603 LEDs with 1 kΩ resistors show the level on the
  serial output of each 595 (D1 U2, D2 U3, D3 U4), the 165 return (D4) and the
  3.3 V rail (D5). They read existing nets and add no logic; use LEDs with Vf up
  to about 2.2 V (red, yellow, green). Header J11 (1 × 6) taps 3V3, buffered
  DATA, CLK, LATCH, the end of the chain and GND for a probe or clip lead. A
  test firmware that shifts a known pattern through the chain therefore shows
  where it stops, before any drive or motor is connected. The LEDs show data
  levels, not activity: all registers share CLK and LATCH. `BUS TEST ON` is
  that test (see [FIRMWARE.md](FIRMWARE.md#bring-up-chain-test)).

### Outputs and inputs per drive

All drive signals are active LOW. Select-line names differ between sources;
this project uses FDD pin numbers.

| Signal | FDD pin | Direction | Note |
| --- | --- | --- | --- |
| DS0 | 10 | 595 → drive | Shugart DS0; Amiga internal drives select here |
| DS1 | 12 | 595 → drive | Typical PC drives select here |
| DS2 | 14 | 595 → drive | Spare select for unusual jumper settings |
| MOTOR | 16 | 595 → drive | Many 3.5" drives may not spin without a disk (unverified) |
| DIR | 18 | 595 → drive | Head direction |
| STEP | 20 | 595 → drive | Head step |
| WRITE DATA | 22 | pull-up only | Never driven |
| WRITE GATE | 24 | pull-up only | Never driven |
| TRACK0 | 26 | drive → 165 | Open collector from the drive |
| WRITE PROTECT | 28 | drive → 165 | Open collector from the drive |

Odd FDD pins are GND. Firmware chooses the select line per drive
(set per drive in the UI and stored on the ESP32; DS1 by default), so PC and
Amiga drives share the same cable without rewiring or rebuilding firmware. Firmware keeps MOTOR
and the other select lines HIGH and reads WRITE PROTECT without using it.

WRITE DATA and WRITE GATE are not connected to registers: a software-shifted
595 chain cannot produce floppy write timing, and a controllable WRITE GATE
could erase a disk.

### Default levels

- Every line toward a drive (DS0–DS2, MOTOR, DIR, STEP, WRITE DATA, WRITE GATE)
  has a pull-up to 3.3 V, so drives stay deselected and still while 595 outputs
  are high impedance during startup. The hand-wired assembly runs without
  pull-ups on the 595 outputs; the PCB keeps them as a cheap precaution.
- TRACK0 and WRITE PROTECT have pull-ups to 3.3 V; the drive only pulls them LOW.
  The hand-wired assembly uses 5.1 kΩ for TRACK0.
- Pull-ups are 4 × 0603 resistor arrays: 10 kΩ on drive inputs, 4.7 kΩ on
  TRACK0 and WRITE PROTECT. The drives' own input terminations are not verified.

### Drive cable

Each module has two 40-pin IDE headers; each serves two drives.

- Use a **40-wire** IDE ribbon; 80-wire Ultra ATA ribbons cannot be split this way.
- Split the ribbon lengthwise into two 20-wire halves. Crimp each half into a
  34-pin IDC socket with its first wire on **FDD pin 10**, so it covers FDD pins
  10–29. Socket positions 1–9 and 30–34 stay empty.
- Socket contact = wire of the half + 9: wires 1–20 land on contacts 10–29, and
  the first wire sits 9 × 1.27 mm = 11.43 mm from the pin-1 end of the socket.
- Only the first half has the red wire. Mark wire 21, the first wire of the
  second half, before splitting the ribbon: it also goes on contact 10.
- Ribbon wire *n* lands on IDE header pin *n*.

| IDE header pins | Drive | FDD pin |
| --- | --- | --- |
| 1–20 | first drive of the pair | IDE pin + 9 |
| 21–40 | second drive of the pair | IDE pin − 11 |

IDE pin 20 is often blocked as a polarity key; it maps to FDD pin 29 (GND) of
the first drive, so only one ground wire is lost. Mark the wire-1 position on
each IDC socket, because wire 1 on FDD pin 1 shifts every signal.

Drives keep their own power connectors from the ATX supply.

## actuator module

Each module carries up to four DRV8833 driver modules soldered on header pins,
3 × 74HC595 (20 of 24 outputs used) and 1 × 74HC165 (4 of 8 inputs used).

| Per DRV8833 | Count | Connection |
| --- | --- | --- |
| IN1–IN4 | 4 | 595 outputs |
| EEP (nSLEEP) | 1 | 595 output |
| ULT (nFAULT) | 1 | 165 input with pull-up to 3.3 V |

All registers are always fitted; a module may carry only two or three drivers.
Unused outputs drive nothing and empty FAULT inputs read HIGH (no fault), so the
chain length stays constant without jumpers. Firmware configuration says which
slots are used. Schematic: `hardware/actuator-module/surrklank-actuator-module.kicad_sch`
(generated, v0.1).

### Register bit order

U2 is first in the chain; U2 QH′ → U3 SER → U4 SER, and U4 QH′ drives OUT DATA.
M1–M4 are the module's DRV8833 slots.

| Register | QA | QB | QC | QD | QE | QF | QG | QH |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| U2 | M1 IN1 | M1 IN2 | M1 IN3 | M1 IN4 | M1 EEP | M2 IN1 | M2 IN2 | M2 IN3 |
| U3 | M2 IN4 | M2 EEP | M3 IN1 | M3 IN2 | M3 IN3 | M3 IN4 | M3 EEP | M4 IN1 |
| U4 | M4 IN2 | M4 IN3 | M4 IN4 | M4 EEP | — | — | — | — |

| 165 input | D0 | D1 | D2 | D3 | D4–D7 |
| --- | --- | --- | --- | --- | --- |
| U5 | M1 ULT | M2 ULT | M3 ULT | M4 ULT | tied to GND |

### Module circuit

- Ribbon interface, input buffer, pull resistors and series resistors are the
  same as on the FDD module.
- EEP lines have 100 kΩ pull-downs (asleep at power-up when J1 on the DRV8833
  module is open; with J1 closed the module's own pull-up wins). IN1–IN4 rely
  on the DRV8833 internal pull-downs. ULT lines have 10 kΩ pull-ups to 3.3 V.
- Each slot has a 4-pin JST-XH connector (2.5 mm): pins 1–4 = OUT1–OUT4.
- Power: KF301 J5 (4 poles: +5 V, +5 V, GND, GND; two wires per rail share the
  motor current), 470 µF bulk capacitor on +5 V, AMS1117-3.3 for logic.
- Bring-up LEDs D1–D5 and header J11 are the same as on the FDD module.

### Motor connections

An LSM motor uses both bridges of one DRV8833; an HDD voice-coil (VCM) coil uses
one bridge, so one DRV8833 serves two HDDs.

```text
595 → IN1/IN2 → bridge A → OUT1 ─ coil ─ OUT2
595 → IN3/IN4 → bridge B → OUT3 ─ coil ─ OUT4
```

Each coil connects between the two outputs of its bridge. Never join outputs of
different bridges or connect a coil terminal to GND or +5 V. The assignment of
LSM1–4 and HDD1–4 to modules and slots is configuration, not fixed wiring.

### Installed DRV8833 module and header pinout

The installed modules are the common 12-pin "DRV8833 2 Channel DC Motor Driver
Module" boards. Identification is from the vendor document (Rajguru Electronics)
and the user's check of the module underside (`EEP`, `ULT`, jumper J1); no
module schematic is available. Header geometry was measured by the user:
2 × 6 pins, 2.54 mm pitch, rows 15.24 mm apart (centre to centre).

Pins in top view (component side), numbered like a DIP package:

| Pin | Label | Signal | Pin | Label | Signal |
| --- | --- | --- | --- | --- | --- |
| 1 | EEP | nSLEEP | 12 | IN4 | BIN2 |
| 2 | OUT1 | AOUT1 | 11 | IN3 | BIN1 |
| 3 | OUT2 | AOUT2 | 10 | GND | GND |
| 4 | OUT3 | BOUT1 | 9 | VCC | VM, +5 V motor supply |
| 5 | OUT4 | BOUT2 | 8 | IN2 | AIN2 |
| 6 | ULT | nFAULT | 7 | IN1 | AIN1 |

Pins 1–6 run down the left row and 7–12 up the right row; the underside view is
mirrored. The bare DRV8833 has no separate logic supply; 3.3 V inputs are
compatible.

- **EEP and J1.** With J1 closed (factory default) an on-board pull-up keeps the
  driver awake. With J1 open the chip's internal pull-down keeps it asleep until
  the 595 drives EEP HIGH, the safest power-up state. The supply of the J1
  pull-up is not documented; check it before driving EEP from 3.3 V against it.
- **ULT** is open-drain and needs the carrier board's pull-up to read correctly.
- **Current sense.** According to the vendor document, no sense resistors are
  fitted, so current regulation is inactive; only the IC's over-current,
  over-temperature and under-voltage protection applies. Not electrically
  verified. Vendor ratings are 1.2 A continuous and 2 A peak per bridge; LSM and
  VCM coil currents are not measured.
- **Capacitors.** Vendor photos show the VM, VCP and VINT capacitors on the module
  (marked 10 µF tantalum, 0.01 µF and 2.2 µF), so they are not repeated on the
  carrier board.

### Running-LED board (proposed)

Actuator module v0.1 has no indicator per motor. A hand-built perfboard at the
**end of the actuator branch** shows which bridges are driving. Not built yet.

```text
mainboard ── actuator module 1 ── … ── actuator module N ──ribbon── LED board
                                       OUT (J2)                     IN
```

- One or two 74HC595 (DIP-16): 8 or 16 LEDs, one LED per bridge. A second 595
  takes its SER from the first one's QH′; CLK, LATCH and /OE are shared.
- Ribbon IN only: pin 1 DATA → SER (pin 14), pin 3 CLK → SRCLK (pin 11),
  pin 5 LATCH → RCLK (pin 12), pin 7 /OE → /OE (pin 13), even pins GND.
  Pins 9, 11, 13 and 15 are not connected; the last QH′ is not connected.
  /MR (pin 10) to 3.3 V.
- Power: +5 V and GND wires like every module, a THT LDO to 3.3 V
  (MCP1700-3302E/TO, 1 µF in and out; not a 78L33, whose dropout is too high),
  100 nF at each 595. Each LED through 330 Ω from a 595 output to GND
  (red, yellow or green; about 4 mA).
- The board has no input buffer, so it must stay last in the branch: a
  mid-chain position would pass CLK, LATCH and /OE unbuffered to the next
  module, and a 74HC595 without Ioff would be back-powered while unpowered.
  It is powered together with the modules. /OE (pull-up on the mainboard)
  keeps the LEDs off while the ESP32 boots.

Bit assignment with two modules and two 595s (A = OUT1/OUT2, B = OUT3/OUT4):

| LED 595 | QA | QB | QC | QD | QE | QF | QG | QH |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1st (SER from module N) | 1 M1A | 1 M1B | 1 M2A | 1 M2B | 1 M3A | 1 M3B | 1 M4A | 1 M4B |
| 2nd | 2 M1A | 2 M1B | 2 M2A | 2 M2B | 2 M3A | 2 M3B | 2 M4A | 2 M4B |

The prefix is the actuator module number. With one 595, map the eight LEDs to
the bridges in use.

Firmware rules:

- The actuator branch frame is `N × 24 + 8 × LED registers` bits. The LED
  registers are the last stages in the chain, so their bits are shifted
  first in each frame.
- A bridge drives its coil only at IN1/IN2 (or IN3/IN4) = 10 or 01; 00 is coast
  and 11 is brake. The LED of a bridge is `IN1 XOR IN2` (bridge A) or
  `IN3 XOR IN4` (bridge B) of the same frame, so the rule needs no LSM, HDD or
  electromagnet configuration. An LSM lights both LEDs of its slot.
- Hold an LED for about 50 ms after the last driving frame so short pulses
  stay visible.
- Describe the chain as an ordered list of stages (for example
  `[actuator, actuator, led8, led8]`), not as a module count.
- The LEDs show the commanded state, not measured coil current; a broken coil
  or cable still lights its LED. ULT (nFAULT) reports driver faults.

A later actuator module revision is planned with a fourth 595 (U7) after U4
(U4 QH′ → U7 SER → OUT DATA) carrying eight on-board bridge LEDs; the U2–U4 bit
order above stays unchanged.

## Power

The ATX supply is used only through its 24-pin connector; the user distributes
GND (black), +5VSB (purple), PS_ON# (green) and PWR_OK (grey) to the mainboard and
+5 V (red) and GND to each module with their own wires and Wago-style splice
nodes. +3.3 V (orange) is not used.

| Board | Supply |
| --- | --- |
| Mainboard | KF301 screw terminal, 4 poles (see [Power input](#power-input)) |
| FDD module | One KF301, 2 poles (+5 V, GND); an on-board 3.3 V LDO makes the logic supply |
| actuator module | One KF301, 4 poles (2 × +5 V, 2 × GND) for motor +5 V; the same LDO makes the logic supply |
| LED board (proposed, perfboard) | +5 V and GND wires; THT MCP1700-3302E/TO makes 3.3 V |

- Each module takes power from exactly one local source. Logic current is
  estimated at about 10 mA per module, mainly pull-ups. The LDO is an
  AMS1117-3.3 (SOT-223, 10 µF in, 22 µF out). The AMS datasheet recommends
  22 µF solid tantalum on the output and says nothing about ceramics, so the
  1206 ceramic (C7) is untested. If the 3.3 V rail misbehaves on the first
  board, hand-fit a 22 µF tantalum or polymer capacitor (EIA 3216-18) on the
  same pads and drop C7 from the JLCPCB BOM.
- One standard for every Surrklank power input: KF301 screw terminal, 5.08 mm
  pitch, through-hole, wire entry from the board edge. Fixed pole order
  (module J5 and mainboard J1), each pole labelled on the silkscreen with its
  function (+5V, GND, ...) next to the terminal, outside the body so it stays
  readable after soldering:

  | Board, part | Poles | Order (pin 1 first) |
  | --- | --- | --- |
  | Mainboard J1 | 4 | GND black, PS_ON# green, +5VSB purple, PWR_OK grey |
  | FDD module J5 | 2 | +5V red, GND black |
  | actuator module J5 | 4 | +5V red, +5V red, GND black, GND black |

  There is no +12 V position on any of them and no plug to confuse with a PSU
  Molex; a yellow +12 V wire is never connected. Use 18 AWG wire from the PSU;
  on the actuator module one wire per pole, two per rail. Measure +5 V at the
  terminal poles before fitting the DRV8833 modules. +3.3 V is never carried.
  Pole and body dimensions in the footprints are generic KF301 values: check
  the bought part against the 1:1 print.
- Actuator module worst case by DRV8833 rating is 4 × 2 × 1.2 A ≈ 9.6 A per module,
  shared by two +5 V and two GND poles and the same +5 V band. The ATX +5 V
  rail, the terminal rating and the wire gauge limit the current as well. Wide
  copper and a 470 µF bulk capacitor at the input are fitted.

## Passive components

| Component | Where |
| --- | --- |
| 100 nF ceramic, ≥ 6.3 V | One per register and buffer IC, close to its supply pins |
| LDO input/output capacitors | Each module: 10 µF in, 22 µF out (ESR to check, see Power) |
| Bulk capacitor | Power input of each actuator module: 470 µF 16 V |
| 10 kΩ pull resistors | Mainboard control lines (table above) |
| Pull-up resistor arrays | FDD lines and inputs, DRV8833 FAULT inputs |
| Series resistors | 33 Ω on mainboard ribbon outputs and module OUT |
| LED resistors | 1 kΩ 0603, one per module bring-up LED (five per module) |
| PWR_OK divider | Mainboard: 10 kΩ / 20 kΩ |
| MMBT3904, 2.2 kΩ, 100 kΩ | Mainboard ATX switch (S8050 in the hand-wired assembly) |

## Maintenance

Before USB flashing or OTA, ATX stays OFF. For USB flashing also remove the
+5VSB jumper and disconnect both ribbons, so the ESP32 runs from USB only.
Never power instruments during an upload.

Sources: [TI SN74HC595](https://www.ti.com/lit/ds/symlink/sn74hc595.pdf),
[TI SN74HC165](https://www.ti.com/lit/ds/symlink/sn74hc165.pdf),
[TI DRV8833](https://www.ti.com/lit/ds/symlink/drv8833.pdf),
[Floppy disk drive interface](https://en.wikipedia.org/wiki/Floppy_disk_drive_interface),
[PC floppy drive in Amiga](https://www.retrosix.wiki/pc-floppy-drive-in-amiga).
