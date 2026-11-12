# Wiring map

This branch (`pcb-modules`) describes the **planned PCB wiring**: a mainboard
and chained FDD and LSM/HDD modules. Nothing here is built or tested yet.
Firmware on this branch still implements the hand-wired mapping recorded in
`docs/WIRING.md` on `main` (commit `eef29dd`): four 595s for FDD1–8 with three
outputs per drive, one 165 for TRACK0 and no LSM/HDD playback. Firmware moves
to this wiring after the modules are assembled. Board-level design (footprints,
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
          └─16-pin ribbon── LSM/HDD module 1 ──ribbon── … LSM/HDD module N
```

- Two branches leave the mainboard on separate long, flexible ribbons
  (modules can move around a roughly 50 × 50 cm area).
- Every module has identical IN and OUT connectors; modules of one branch are
  daisy-chained. Module 1 is closest to the mainboard.
- An FDD module serves four drives; two FDD modules serve the current eight.
- An LSM/HDD module carries up to four DRV8833 driver modules.
- ESP32, modules, drivers and drives share GND.

## Mainboard

### ESP32 GPIO

| GPIO | Function | Status |
| --- | --- | --- |
| 23 | FDD branch DATA | as today |
| 22 | FDD branch LATCH | as today |
| 34 | FDD branch Q165 (input only) | as today |
| 17 | LSM/HDD branch DATA | as today |
| 16 | LSM/HDD branch LATCH | as today |
| 35 | LSM/HDD branch Q165 (input only) | new, proposed |
| 18 | CLK, both branches | as today |
| 21 | /OE, both branches | as today |
| 33 | /PL, both branches | as today (FDD only) |
| 32 | CLK165, both branches | as today (FDD only) |
| 19 | ATX PS_ON# transistor | as today |
| 13 | ATX button | as today |
| 36 | PWR_OK via divider (input only; GPIO39 is the alternative) | new, proposed |

A GPIO shared by both branches drives each ribbon through its own series
resistor. GPIO34–39 have no internal pull resistors.

### Default levels on the mainboard

Pull resistors on the mainboard keep register control lines inactive while the
ESP32 boots or a GPIO is high impedance:

| Signal | Resistor | Level without active drive |
| --- | --- | --- |
| /OE | 10 kΩ pull-up to 3.3 V | HIGH: 595 outputs high impedance |
| /PL | 10 kΩ pull-up | HIGH: parallel load inactive |
| CLK, CLK165 | 10 kΩ pull-down | LOW |
| LATCH (each branch) | 10 kΩ pull-down | LOW |
| DATA (each branch) | 10 kΩ pull-down | LOW |
| Q165 (each branch) | pull resistor, value not chosen | defined with no module connected |

### Power input

A pluggable (two-part) screw terminal brings +3V3, GND, PS_ON#, +5VSB and
PWR_OK from the user's ATX distribution. +5 V on this terminal is not decided.

- **+5VSB → ESP32.** The ATX standby rail powers the ESP32 board through a
  Schottky diode and a removable jumper into the board's 5 V pin, so the ESP32
  runs while ATX main rails are off. The diode stops USB 5 V from feeding the
  standby rail; removing the jumper isolates the ESP32 from ATX for USB
  flashing. The ESP32 board is assumed to have no USB VBUS diode (seller
  warning); this is not verified.
- **+3V3** from ATX feeds only mainboard pull resistors and, through a normally
  open solder jumper, the ribbons for bench use. Never connect ATX +3.3 V to
  the ESP32 board's 3V3 or 5 V pin.
- **PWR_OK** (grey ATX wire, nominally 5 V logic) reaches GPIO36 through a
  resistor divider to 3.3 V levels. It reports main rails up, unlike the GPIO19
  request. Divider values are not chosen; firmware does not read it yet.

### ATX power switch and button

ATX starts OFF in firmware, and a maintenance lock forces OFF and rejects ON
until the next ESP32 restart.

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

GPIO13 uses the internal pull-up: released HIGH, pressed LOW. Each debounced
press toggles the ATX request. A button held during startup must be released
before it can request ON. It is a software input, not a power isolator. The
button connects to the mainboard through a two-pin connector.

### Standby power and module back-powering

With the ESP32 on standby power, module logic is unpowered while ATX is off.
Ribbon signals must not back-power modules through register inputs. Planned
measures: a module input buffer with power-off protection (a 74LVC244A-class
part with Ioff), series resistors on the mainboard, and firmware that drives
branch lines LOW while ATX is off. Not designed or verified yet.

## Module ribbon (16-pin)

Both branches use the same proposed 2 × 8 IDC ribbon. Every signal runs next to
a ground wire. Pin assignment is a proposal for the schematic:

| Pin | Signal | Pin | Signal |
| --- | --- | --- | --- |
| 1 | DATA | 2 | GND |
| 3 | CLK | 4 | GND |
| 5 | LATCH | 6 | GND |
| 7 | /OE | 8 | GND |
| 9 | /PL | 10 | GND |
| 11 | CLK165 | 12 | GND |
| 13 | Q165 | 14 | GND |
| 15 | +3V3 (bench only, solder jumper) | 16 | GND |

On each module:

- DATA, CLK, LATCH, /OE, /PL and CLK165 from IN pass through the input buffer
  to the module's registers and to OUT.
- The last 595's QH′ drives DATA on OUT.
- The 165's QH drives Q165 on IN; its serial input (SER, pin 10) takes Q165
  from OUT, with a pull resistor so an open OUT reads a defined level.
- Modules are powered locally; the ribbon +3V3 wire connects only when the
  bench solder jumper is closed.

Series resistors on mainboard outputs and the buffer part are not chosen.

## FDD module

Each module serves four drives with 3 × 74HC595 (24 outputs, six per drive) and
1 × 74HC165 (8 inputs, two per drive). The exact register bit order is fixed
during schematic design and recorded here then.

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

Odd FDD pins are GND. Firmware will choose the select line per drive, so PC and
Amiga drives share the same cable without rewiring.

WRITE DATA and WRITE GATE are not connected to registers: a software-shifted
595 chain cannot produce floppy write timing, and a controllable WRITE GATE
could erase a disk.

### Default levels

- Every line toward a drive (DS0–DS2, MOTOR, DIR, STEP, WRITE DATA, WRITE GATE)
  has a pull-up to 3.3 V, so drives stay deselected and still while 595 outputs
  are high impedance during startup.
- TRACK0 and WRITE PROTECT have pull-ups to 3.3 V; the drive only pulls them LOW.
  The hand-wired assembly uses 5.1 kΩ for TRACK0.
- Pull-ups are resistor arrays. Values and the drives' own input terminations
  are not verified.

### Drive cable

Each module has two 40-pin IDE headers; each serves two drives.

- Use a **40-wire** IDE ribbon; 80-wire Ultra ATA ribbons cannot be split this way.
- Split the ribbon lengthwise into two 20-wire halves. Crimp each half into a
  34-pin IDC socket with its first wire on **FDD pin 10**, so it covers FDD pins
  10–29. Socket positions 1–9 and 30–34 stay empty.
- Ribbon wire *n* lands on IDE header pin *n*.

| IDE header pins | Drive | FDD pin |
| --- | --- | --- |
| 1–20 | first drive of the pair | IDE pin + 9 |
| 21–40 | second drive of the pair | IDE pin − 11 |

IDE pin 20 is often blocked as a polarity key; it maps to FDD pin 29 (GND) of
the first drive, so only one ground wire is lost. Mark the wire-1 position on
each IDC socket, because wire 1 on FDD pin 1 shifts every signal.

Drives keep their own power connectors from the ATX supply.

## LSM/HDD module

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
slots are used. The exact register bit order is fixed during schematic design.

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

## Power

The ATX supply is used only through its 24-pin connector; the user distributes
+3.3 V (orange), +5 V (red), GND (black), +5VSB (purple), PS_ON# (green) and
PWR_OK (grey) with their own wires and Wago-style splice nodes.

| Board | Supply |
| --- | --- |
| Mainboard | Screw terminal (see [Power input](#power-input)) |
| FDD module | One male 4-pin Molex (+5 V, GND); an on-board 3.3 V LDO makes the logic supply |
| LSM/HDD module | One or two male 4-pin Molex connectors for motor +5 V; the same LDO makes the logic supply |

- Each module takes power from exactly one local source. Logic current is
  estimated at about 10 mA per module, mainly pull-ups; the LDO part is not chosen.
- The Molex keeps the standard peripheral pinout: +5 V at the red position,
  both middle pins GND, the +12 V (yellow) position unconnected and marked on
  the silkscreen. A standard PSU Molex plugged in by mistake stays harmless;
  +3.3 V is never carried on a Molex.
- LSM/HDD worst case by DRV8833 rating is 4 × 2 × 1.2 A ≈ 9.6 A per module; the
  second Molex is fitted only if measured current requires it. Wide copper and a
  bulk capacitor at the input are planned.

## Passive components

| Component | Where |
| --- | --- |
| 100 nF ceramic, ≥ 6.3 V | One per register and buffer IC, close to its supply pins |
| LDO input/output capacitors | Each module, per the chosen LDO datasheet |
| Bulk capacitor | Molex input of each LSM/HDD module; value not chosen |
| 10 kΩ pull resistors | Mainboard control lines (table above) |
| Pull-up resistor arrays | FDD lines and inputs, DRV8833 FAULT inputs |
| Series resistors | Mainboard ribbon outputs; value not chosen |
| PWR_OK divider | Mainboard; values not chosen |
| Schottky diode | Mainboard +5VSB path |
| S8050, 2.2 kΩ, 47–100 kΩ | Mainboard ATX switch |

## Maintenance

Before USB flashing or OTA, ATX stays OFF. For USB flashing also remove the
+5VSB jumper and disconnect both ribbons, so the ESP32 runs from USB only.
Never power instruments during an upload.

Sources: [TI SN74HC595](https://www.ti.com/lit/ds/symlink/sn74hc595.pdf),
[TI SN74HC165](https://www.ti.com/lit/ds/symlink/sn74hc165.pdf),
[TI DRV8833](https://www.ti.com/lit/ds/symlink/drv8833.pdf),
[Floppy disk drive interface](https://en.wikipedia.org/wiki/Floppy_disk_drive_interface),
[PC floppy drive in Amiga](https://www.retrosix.wiki/pc-floppy-drive-in-amiga).
