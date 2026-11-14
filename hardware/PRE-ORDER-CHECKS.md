# Pre-order checks (temporary)

**Delete this file once every check below has passed and its consequences are
resolved.** It is a working checklist, not project documentation: results that
change the design belong in `docs/WIRING.md` and `hardware/README.md`, then this
file goes. Record measurements (value, conditions, date) separately from
observations and hypotheses.

Frozen design: commit `6192162` (boards generated, ERC/DRC clean, bring-up LEDs
and header J11 on both modules, nothing built or measured).

## A. Before ordering, no boards needed

| # | Check | How | Look for | Result |
| --- | --- | --- | --- | --- |
| 1 | Dry fit 1:1 | Run `export_dryfit.py` (KiCad's Python), print the A4 sheet at 100 % and check the 10 cm rulers first, then put foam under the paper and push the real parts through it | ESP32 row spacing and antenna overhang; **Molex key side (silk chamfers) and pin order**; IDE header; ATX terminal; JST-XH; OLED; buttons | |

## B. Multimeter on real parts

| # | Check | How | Look for | Result |
| --- | --- | --- | --- | --- |
| 3 | DRV8833 carrier | Apply 5 V to VCC and GND only (no IN, no motor). Measure ULT and EEP to GND with J1 closed and open. Check continuity from the J1 pad to VCC | ULT about 5 V means a pull-up to the carrier supply (about 0.1 mA through 10 kΩ, low risk, record it); about 3.3 V or floating means none | |
| 4 | FDD input terminations | Power one drive from its Molex, data cable disconnected. Measure DC to GND on DS0 (10), DS1 (12), DS2 (14), MOTOR (16), DIR (18), STEP (20), WD (22), WG (24); TRACK0 (26) and WP (28) with the input floating | About 5 V means terminators to +5 V and a risk for the 3.3 V 595/165: add series resistors or level shifting (may change the boards). 0 to 3.3 V or floating is fine | |
| 4b | Hand-wired rig | With all drives connected measure the 3.3 V rail | Must not rise above 3.3 V | |
| 5 | Ribbons | Continuity of all 16 wires and no neighbour shorts on every cable; both sockets on the same face, red wire on pin 1 | Every wire pin n to pin n | |

## C. After the first module is assembled

| # | Check | How | Look for | Result |
| --- | --- | --- | --- | --- |
| 6 | +5 V on the Molex | **Before** fitting DRV8833 modules: real PSU plug into J5, measure pin 4 to GND | Exactly +5 V. 12 V means the header is soldered the wrong way round: unplug at once | |
| 7 | Module 3.3 V | 5 V via Molex only, no ESP | 3.3 V ±0.1 V; AMS1117 not hot | |
| 8 | 3.3 V ripple | Oscilloscope (borrowed), probe with a short ground spring | No oscillation. Datasheet is silent on ceramics: if it misbehaves hand-fit a 22 µF tantalum or polymer (EIA 3216-18) on the C7 pads | |
| 9 | Back-power | ESP on +5VSB, ATX off, module connected by ribbon only (no Molex): measure the module 3.3 V rail | Above about 1.5 V is a problem. Record the value. D5 on the rail starts to glow near 1.8 V (red), so a lit D5 with ATX off means a back-powered rail | |
| 10 | Motor current | Bench supply with current limit or ammeter in the +5V line, one motor at a time | Start and hold current against the DRV8833 limit and one Molex pin | |
| 11 | Long ribbon | Longest planned ribbons, every module connected, motors under load, long run | Wrong or missing steps. Only on errors: oscilloscope on CLK and LATCH at the far end of the longest hop, ringing near 1.65 V. J11 taps add unterminated branches on CLK and LATCH (routed length, measured on the layout: FDD about 42 and 36 mm, LSM/HDD about 15 and 28 mm); look at these first | |

## D. Decisions before ordering

| # | Decision | Notes | Result |
| --- | --- | --- | --- |
| 12 | 74HC595 part | GR part (Chinese datasheet, SOIC-16 body width confirmed 3.9 mm, VIH/VIL given only at 4.5 V) or a branded 74HC595D from a local shop | |
| 13 | Hand soldering SMD | No factory assembly: 0603 resistor arrays and LEDs, SOIC-16/20W and SOT-223 are soldered by hand (fine-tip iron, flux, tweezers); connectors, ESP32 sockets, buttons and DRV8833 modules were hand-soldered anyway. Practise on a spare board if unsure | |
| 14 | Copper weight of the LSM/HDD board | +5V band is 4.7 to 7.9 mm wide (about 10 A at +20 K for 1 oz by an IPC-2221 estimate); the Molex pin and PSU wire limit first | |
| 17 | Bring-up LEDs and J11 | After the first module is built: test firmware shifts a pattern through U2-U4 and the LEDs and J11 pin 5 follow it. Fit the LEDs with the cathode toward GND (flat side or green mark; KiCad pad 1 is the cathode) | |
| 16 | Mounting hole H2 on the mainboard | Sits under the plugged ATX terminal: move it or accept three holes | |
