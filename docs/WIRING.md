# Wiring map

## Two output branches

```text
ESP32 GPIO23 → 595 F1 → 595 F2 → 595 F3 → 595 F4
               FDD1–2  FDD3–4  FDD5–6  FDD7–8

ESP32 GPIO17 → 595 D1 → 595 D2 → 595 H1
               DVD1–2  DVD3–4  HDD1–4

FDD1–8 TRACK0 → one 165 → ESP32 GPIO34
```

F1/D1 are closest to the ESP32. Connect each 595 serial output QH′ (pin 9)
to SER (pin 14) of the next 595 in the same branch.

## ESP32 → registers

| ESP32 GPIO | Connection |
| --- | --- |
| 23 | SER, pin 14 of the first 595 in the FDD branch |
| 17 | SER, pin 14 of the first 595 in the DVD/HDD branch |
| 18 | CLOCK, pin 11 of all 595s in both branches |
| 22 | LATCH, pin 12 of all 595s in the FDD branch |
| 16 | LATCH, pin 12 of all 595s in the DVD/HDD branch |
| 21 | /OE, pin 13 of all 595s in both branches |
| 33 | /PL, pin 1 of the 165 |
| 32 | CLOCK, pin 2 of the 165 |
| 34 | QH, pin 9 of the 165 — data to ESP32 |

## 595 — common pins

| Function | Pin |
| --- | --- |
| QA, QB, QC, QD, QE, QF, QG, QH | 15, 1, 2, 3, 4, 5, 6, 7 |
| SER — serial input | 14 |
| QH′ — serial output to the next 595 | 9 |
| CLOCK / LATCH / /OE | 11 / 12 / 13 |
| /SRCLR | 10 → 3.3 V |
| VCC / GND | 16 → 3.3 V / 8 → GND |

## FDD — addresses and 595 outputs

Address means the device number in the previous protocol, not a bus address.

| Address | Register | STEP → FDD pin 20 | DIR → FDD pin 18 | /SELECT → FDD pin 12 |
| --- | --- | --- | --- | --- |
| FDD 1 | F1 | QE, pin 4 | QF, pin 5 | QG, pin 6 |
| FDD 2 | F1 | QB, pin 1 | QC, pin 2 | QD, pin 3 |
| FDD 3 | F2 | QE, pin 4 | QF, pin 5 | QG, pin 6 |
| FDD 4 | F2 | QB, pin 1 | QC, pin 2 | QD, pin 3 |
| FDD 5 | F3 | QE, pin 4 | QF, pin 5 | QG, pin 6 |
| FDD 6 | F3 | QB, pin 1 | QC, pin 2 | QD, pin 3 |
| FDD 7 | F4 | QE, pin 4 | QF, pin 5 | QG, pin 6 |
| FDD 8 | F4 | QB, pin 1 | QC, pin 2 | QD, pin 3 |

QA and QH of each FDD 595 are unused. /SELECT is active LOW.
Pin 12 is the assumed drive-select input; this depends on the FDD jumper settings.
Odd-numbered pins on the FDD signal connector are GND.

## FDD TRACK0 → 165

Each FDD: pin 26 (/TRACK0) → a separate 165 input, with a 5.1 kΩ pull-up to 3.3 V.

| FDD | 165 input | 165 pin |
| --- | --- | --- |
| 1 | A / D0 | 11 |
| 2 | B / D1 | 12 |
| 3 | C / D2 | 13 |
| 4 | D / D3 | 14 |
| 5 | E / D4 | 3 |
| 6 | F / D5 | 4 |
| 7 | G / D6 | 5 |
| 8 | H / D7 | 6 |

Other 165 pins: VCC16 → 3.3 V, GND8 → GND, CLK INH15 → GND,
SER10 → 3.3 V. Inverted output /QH7 is unused.
With four FDDs, unused inputs D4–D7 are held HIGH.

## DVD/HDD — addresses and 595 outputs

DVD drives use addresses `SLED 1`…`SLED 4`. Each DVD motor uses one DRV8833:
AOUT1/AOUT2 → coil A, BOUT1/BOUT2 → coil B.

| Device / address | Register | AIN1 | AIN2 | BIN1 | BIN2 |
| --- | --- | --- | --- | --- | --- |
| DVD1 / SLED 1 | D1 | QA, pin 15 | QB, pin 1 | QC, pin 2 | QD, pin 3 |
| DVD2 / SLED 2 | D1 | QE, pin 4 | QF, pin 5 | QG, pin 6 | QH, pin 7 |
| DVD3 / SLED 3 | D2 | QA, pin 15 | QB, pin 1 | QC, pin 2 | QD, pin 3 |
| DVD4 / SLED 4 | D2 | QE, pin 4 | QF, pin 5 | QG, pin 6 | QH, pin 7 |

Each HDD VCM coil uses one DRV8833 H-bridge:

| Address | Register | 595 outputs → DRV8833 inputs | Bridge outputs → VCM |
| --- | --- | --- | --- |
| HDD 1 | H1 | QA15 → AIN1, QB1 → AIN2 (DRV7) | AOUT1/AOUT2 |
| HDD 2 | H1 | QC2 → BIN1, QD3 → BIN2 (DRV7) | BOUT1/BOUT2 |
| HDD 3 | H1 | QE4 → AIN1, QF5 → AIN2 (DRV8) | AOUT1/AOUT2 |
| HDD 4 | H1 | QG6 → BIN1, QH7 → BIN2 (DRV8) | BOUT1/BOUT2 |

## DRV8833 — driver connections

Six driver modules are used: DRV1–4 for DVD1–4, DRV7 for HDD1–2 and DRV8
for HDD3–4. These are module labels, not bus addresses. DRV5–6 are not used.
There are no direct motor-control connections from ESP32 GPIOs to these modules;
the 595 outputs drive AIN1/AIN2/BIN1/BIN2 as listed above.

### Power and control

| DRV8833 signal | Connection |
| --- | --- |
| VM (sometimes labelled VIN on a module) | ATX +5 V motor supply |
| GND | Common GND shared with ATX, registers and ESP32 |
| AIN1, AIN2 | Two 595 outputs controlling bridge A |
| BIN1, BIN2 | Two 595 outputs controlling bridge B |
| nSLEEP (sometimes SLP) | HIGH to enable the driver; proposed connection: 10 kΩ pull-up to register logic 3.3 V if the module has no existing enable circuit |
| nFAULT (sometimes FLT) | Leave unconnected; not read by this project |
| AISEN, BISEN | Current-sense connections described below; not digital control inputs |

The bare DRV8833 has no separate 3.3 V logic-supply input. VM supplies the IC;
the 3.3 V signals from the 595s connect to its logic inputs. VINT is an internal
regulator output for its capacitor, not an external power input.

The module model is not identified. Use the signal labels above, not an assumed
header order. IC pin numbers also depend on the package; select the exact part
before assigning a KiCad symbol or footprint. The nSLEEP pull-up is a proposed
addition, not a confirmed connection on the current modules.

### DVD motor wiring

Each DVD motor has two separate coil pairs and uses both bridges of one module:

```text
595 → AIN1/AIN2 → DRV8833 bridge A → AOUT1 ─ coil A ─ AOUT2
595 → BIN1/BIN2 → DRV8833 bridge B → BOUT1 ─ coil B ─ BOUT2
```

DVD1 uses DRV1, DVD2 uses DRV2, DVD3 uses DRV3 and DVD4 uses DRV4.
Neither coil terminal connects to GND or directly to +5 V.

### HDD VCM wiring

| Module | Bridge A: AOUT1/AOUT2 | Bridge B: BOUT1/BOUT2 |
| --- | --- | --- |
| DRV7 | Two terminals of HDD1 VCM coil | Two terminals of HDD2 VCM coil |
| DRV8 | Two terminals of HDD3 VCM coil | Two terminals of HDD4 VCM coil |

Each VCM coil connects between the two outputs of its bridge. Do not join
outputs of different bridges or connect a coil terminal directly to GND/+5 V.

### Current sense and local components

For a bare IC, AISEN connects to GND through the bridge A sense resistor;
BISEN connects to GND through the bridge B sense resistor. The nominal current
trip relationship is `I_trip = 0.2 V / R_sense`. Values depend on the motor and
are not specified here. A direct GND connection disables current regulation;
it is not a current-limiting resistor. Neither sense input should float.

On a ready-made module these connections may already be fitted or tied to GND.
The local VM, VCP and VINT capacitors are listed in the passive-components section.
The exact module schematic is still needed to record its header pins, fitted
sense resistors and existing nSLEEP circuitry.

## Power connections

ESP32, registers, drivers and drives share GND. 595/165 logic uses ATX 3.3 V;
FDD power and DVD/HDD driver VM use 5 V. ESP32 is powered by USB.
Do not connect the positive ATX 3.3 V rail to ESP32 3V3/5V/VIN.

## ATX power switch and button

The previous wiring map uses **GPIO19 for ATX control** and **GPIO13 for the
button**. GPIO18 is the shared 595 clock, not the button input.
The current minimal BLE firmware does not implement either function.

### ESP32 → ATX PS_ON#

Use a separate S8050 NPN transistor:

```text
ESP32 GPIO19 ── 2.2 kΩ ── S8050 base
                              │
                           47–100 kΩ
                              │
Common GND ────────────── S8050 emitter
ATX PS_ON# ────────────── S8050 collector
```

| Connection | Purpose |
| --- | --- |
| GPIO19 → 2.2 kΩ → base | Base drive |
| Base → 47–100 kΩ → emitter/GND | Holds the transistor off while GPIO19 is high impedance |
| Emitter → common GND | Common reference with ATX and ESP32 |
| Collector → ATX PS_ON# | Pulls the active-LOW power-enable signal to GND |

GPIO19 HIGH turns the transistor on and requests ATX ON. GPIO19 LOW turns it
off and releases PS_ON#, requesting ATX OFF. This is a logical command, not a
measurement of the supply rails. PS_ON# is conventionally the green ATX wire;
identify it by connector function. Do not connect PS_ON# directly to an ESP32 GPIO.
Use the actual transistor's base/collector/emitter pinout; S8050 lead order is
not assumed here. No PWR_OK or voltage-measurement input is connected.

### Momentary push button

```text
ESP32 GPIO13 ── normally-open momentary button ── ESP32 GND
```

The intended firmware configures GPIO13 as `INPUT_PULLUP`: released = HIGH,
pressed = LOW. No external pull-up or connection to 3.3 V is needed with that
configuration. Each debounced press toggles the ATX request; releasing the
button does not toggle it. A button held during startup must first be released
before it can request ON. This is a software input, not a physical power isolator.

Additional components: 1 × S8050 NPN, 1 × 2.2 kΩ, 1 × 47–100 kΩ and
1 × normally-open momentary button. These are separate from the resistor counts
for the registers and DRV8833 modules below.

## Resistors and capacitors

The table describes the intended components. The user confirmed 100 nF capacitors
and 5.1 kΩ TRACK0 pull-ups. Other resistors are recommended additions, not a record
of the current assembly. The 10 kΩ value is a project design choice.

### Register supply decoupling

| Component | Full-system quantity | Connection |
| --- | --- | --- |
| 100 nF ceramic capacitor, rated ≥ 6.3 V | 7 for the 595s + 1 for the 165 | VCC pin 16 to GND pin 8 of each IC, with short connections close to the pins |

Each IC has its own capacitor. One shared rail capacitor does not replace these eight.

### TRACK0 and default signal levels

A pull-up connects the signal through a resistor to the register logic 3.3 V rail.
A pull-down connects it through a resistor to GND. These are branches from the
signal, not series resistors between the GPIO and the register.

| Signal | Resistor | Connection | Level without active drive |
| --- | --- | --- | --- |
| TRACK0 FDD1–8 | 5.1 kΩ pull-up per line | 165 inputs A–H → logic 3.3 V | HIGH — TRACK0 inactive |
| /OE, both 595 branches, GPIO21 | One shared 10 kΩ pull-up | Register pin 13 → logic 3.3 V | HIGH — 595 outputs in high impedance |
| 165 /PL, GPIO33 | 10 kΩ pull-up | 165 pin 1 → logic 3.3 V | HIGH — parallel load inactive |
| CLOCK165, GPIO32 | 10 kΩ pull-down | 165 pin 2 → GND | LOW |
| CLOCK595, GPIO18 | One shared 10 kΩ pull-down | Register pin 11 → GND | LOW |
| FDD LATCH, GPIO22 | 10 kΩ pull-down | FDD branch register pin 12 → GND | LOW |
| DVD/HDD LATCH, GPIO16 | 10 kΩ pull-down | DVD/HDD branch register pin 12 → GND | LOW |
| FDD DATA, GPIO23 | 10 kΩ pull-down | First 595 F1 SER pin 14 → GND | LOW |
| DVD/HDD DATA, GPIO17 | 10 kΩ pull-down | First 595 D1 SER pin 14 → GND | LOW |

Total: 8 × 5.1 kΩ and 8 × 10 kΩ. With four FDDs, only four TRACK0 pull-ups
are needed; unused inputs E–H remain connected to 3.3 V.
No additional resistors are specified on QA–QH outputs or QH/QH′ serial outputs.
595 /SRCLR, 165 SER and 165 CLK INH retain the direct connections listed above.

DATA165 at GPIO34 is driven by the 165 QH output. No extra pull-up is required
for normal reads. Defining a level with the cable disconnected is a separate
option, excluded from the resistor count above.

These resistors do not isolate a powered ESP32 from unpowered registers.
Power-domain isolation remains unspecified. High-impedance 595 outputs do not
by themselves define the levels at the connected drive inputs.

### DRV8833 modules

Components already fitted to a module are not counted as extra board components.
For the bare DRV8833 IC, the manufacturer specifies:

| Component | Connection |
| --- | --- |
| At least 10 µF ceramic capacitor, rated for VM | VM → GND, close to each driver |
| 10 nF X7R ceramic capacitor, rated at least 16 V | VCP → VM |
| 2.2 µF ceramic capacitor, rated at least 6.3 V | VINT → GND |

The installed module model and AISEN/BISEN current-sense resistor values have
not been identified. Additional motor-rail bulk capacitance depends on the
module and load. If the proposed nSLEEP pull-ups above are fitted to all six
modules, add 6 × 10 kΩ to the register/TRACK0 resistor count.

Sources: [TI SN74HC595 — decoupling and inputs](https://www.ti.com/lit/ds/symlink/sn74hc595.pdf),
[TI SN74HC165](https://www.ti.com/lit/ds/symlink/sn74hc165.pdf),
[TI DRV8833 — external components](https://www.ti.com/lit/ds/symlink/drv8833.pdf).
