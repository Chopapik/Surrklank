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
| 1 | Dry fit 1:1 | Run `export_dryfit.py` (KiCad's Python), print the A4 sheet at 100 % and check the 10 cm rulers first, then put foam under the paper and push the real parts through it | ESP32 row spacing and antenna overhang; **KF301 terminals (pole pitch, body size, wire entry side)**; IDE header; JST-XH; OLED; buttons | 2026-11-14, user report: everything fits on the 1:1 print after the ESP32 row spacing was set to 24.85 mm (caliper measurement 24.8 to 24.9 mm). Observation only: the Molex key side was not reported separately | |

## B. Multimeter on real parts

| # | Check | How | Look for | Result |
| --- | --- | --- | --- | --- |
| 3 | DRV8833 carrier | Apply 5 V to VCC and GND only (no IN, no motor). Measure ULT and EEP to GND with J1 closed and open. Check continuity from the J1 pad to VCC | ULT about 5 V means a pull-up to the carrier supply (about 0.1 mA through 10 kΩ, low risk, record it); about 3.3 V or floating means none | 2026-11-15, user measurement with J1 closed (factory state, J1 cannot be opened): ULT 1.5 V, EEP 4.64 V, supply voltage not recorded. Observation: ULT is a floating open-drain input read by the meter (no pull-up to the carrier supply), so the 165 inputs are not exposed to 5 V; EEP is pulled up by the module. Open-J1 measurement skipped. Closed: no board change | 
| 4 | FDD input terminations | Power one drive from its Molex, data cable disconnected. Measure DC to GND on DS0 (10), DS1 (12), DS2 (14), MOTOR (16), DIR (18), STEP (20), WD (22), WG (24); TRACK0 (26) and WP (28) with the input floating | About 5 V means terminators to +5 V and a risk for the 3.3 V 595/165: add series resistors or level shifting (may change the boards). 0 to 3.3 V or floating is fine | 2026-11-15, user measurement on one spare drive (model not recorded, not necessarily the drives to be used), data cable disconnected: TRACK0 (pin 26) 3.44 V, repeated reading 3.4 V; no other pin measured. Observation: not 5 V, so no pull-up to +5 V on TRACK0 for this drive, but 0.1 V above the 3.3 V rail, which suggests a drive-side divider or diode: harmless for the 165 (rating VCC + 0.5 V). Input pins 10 to 24 (DS, MOTOR, DIR, STEP, WD, WG) and WP not measured: their terminations remain unverified | 
| 4b | Hand-wired rig | With all drives connected measure the 3.3 V rail | Must not rise above 3.3 V | |
| 5 | Ribbons | Continuity of all 16 wires and no neighbour shorts on every cable; both sockets on the same face, red wire on pin 1 | Every wire pin n to pin n | |

## C. After the first module is assembled

| # | Check | How | Look for | Result |
| --- | --- | --- | --- | --- |
| 6 | +5 V on the J5 poles | **Before** fitting DRV8833 modules: with the PSU wires screwed in (red to the +5V poles, black to GND), measure each +5V pole to GND | Exactly +5 V on every +5V pole. 12 V means a yellow wire is connected: unplug at once | |
| 7 | Module 3.3 V | 5 V via the J5 terminal only, no ESP | 3.3 V ±0.1 V; AMS1117 not hot | |
| 8 | 3.3 V ripple | Oscilloscope (borrowed), probe with a short ground spring | No oscillation. Datasheet is silent on ceramics: if it misbehaves hand-fit a 22 µF tantalum or polymer (EIA 3216-18) on the C7 pads | |
| 9 | Back-power | ESP on +5VSB, ATX off, module connected by ribbon only (no J5 supply): measure the module 3.3 V rail | Above about 1.5 V is a problem. Record the value. D5 on the rail starts to glow near 1.8 V (red), so a lit D5 with ATX off means a back-powered rail | |
| 10 | Motor current | Bench supply with current limit or ammeter in the +5V line, one motor at a time | Start and hold current against the DRV8833 limit and one KF301 pole (rating of the bought part) | |
| 11 | Long ribbon | Longest planned ribbons, every module connected, motors under load, long run | Wrong or missing steps. Only on errors: oscilloscope on CLK and LATCH at the far end of the longest hop, ringing near 1.65 V. J11 taps add unterminated branches on CLK and LATCH (routed length, measured on the layout: FDD about 42 and 36 mm, actuator module about 15 and 28 mm); look at these first | |

## D. Decisions before ordering

| # | Decision | Notes | Result |
| --- | --- | --- | --- |
| 12 | 74HC595 part | GR part (Chinese datasheet, SOIC-16 body width confirmed 3.9 mm, VIH/VIL given only at 4.5 V) or a branded 74HC595D from a local shop | |
| 13 | Hand soldering SMD | No factory assembly: 0603 resistor arrays and LEDs, SOIC-16/20W and SOT-223 are soldered by hand (fine-tip iron, flux, tweezers); connectors, ESP32 sockets, buttons and DRV8833 modules were hand-soldered anyway. Practise on a spare board if unsure | |
| 14 | Copper weight of the actuator module board | +5V band is 4.7 to 7.9 mm wide (about 10 A at +20 K for 1 oz by an IPC-2221 estimate); the KF301 pole and PSU wire limit first | |
| 17 | Bring-up LEDs and J11 | After the first module is built: test firmware shifts a pattern through U2-U4 and the LEDs and J11 pin 5 follow it. Fit the LEDs with the cathode toward GND (flat side or green mark; KiCad pad 1 is the cathode) | |
| 16 | Mounting hole H2 on the mainboard | Moved to x 70 mm so it clears the KF301 ATX terminal J1 (x 37-58 mm, y 66-74 mm): confirm that three or four holes fit the enclosure plan | |
