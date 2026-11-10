# Surrklank firmware and maintenance

## Build and dependencies

Firmware uses PlatformIO `espressif32@6.12.0` with ESP-IDF 5.5. It does not use
Arduino. Espressif's `ble_conn_mgr`, `ble_services` and `ble_ota_raw` components
are pinned to commit `5fbb2597b88f21ec41e952f81292ccd6ae569761` in
`firmware/src/idf_component.yml`. Component-manager downloads are generated
dependencies, not application source.

```sh
pio run -d firmware -e esp32
python3 firmware/tests/test_atx_power.py
python3 firmware/tests/test_fdd.py
python3 firmware/tests/test_fdd_control.py
```

These commands build/check locally and do not connect to a physical ESP32.
Physical USB or BLE OTA upload is a separate, explicitly authorized action.

`main.cpp` initializes ATX output before NVS, BLE and OTA. `atx_power.cpp`
initializes GPIO19 LOW, samples/debounces the GPIO13 button and owns the
maintenance lock. `ble_connection.cpp` advertises `EM-MIDI-IDF` through the
official connection manager and implements FFF1 commands and FFF2 state
notifications. See [BLE application protocol](BLE-PROTOCOL.md). The application
requests 251-byte BLE Data Length Extension and a 15 ms connection interval;
actual link parameters are observed, not assumed.

`ota_update.cpp` connects the official OTA profile to ESP-IDF flash and boot
APIs. Completed sectors enter a bounded FreeRTOS queue; flash writes happen
outside the BLE callback. A static 64 KiB buffer batches sequential writes at
erase-block boundaries. Session epochs discard queued data from an aborted
transfer. Queue/window sizes bound memory use. An incomplete transfer is
aborted on disconnect or timeout without selecting it for boot.

## Official BLE OTA transport

Service `0x8018` uses receive-firmware characteristic `0x8020` and command
characteristic `0x8022`. The backend subscribes to both notification streams
before START. The 20-byte command includes a little-endian opcode (START `1`,
STOP `2`), firmware size for START and CRC16-XMODEM at bytes 18–19. The command
ACK reports acceptance and the receiver's sector window. Firmware packets carry
sector index, packet sequence and data; the final packet of a sector contains
its CRC16-XMODEM. Sectors contain at most 4096 firmware bytes, with official
sector receipts. The sender introduces no separate data or credit protocol.

The sender uses one sector in flight, awaiting its receipt before sending the
next. This bounds receiver queue pressure during flash erase/write stalls.
After each full 64 KiB group it waits one second before the next group.
This pacing is not an acknowledgment of committed flash; final ready/identity
verification remains mandatory. SimpleBLE 1.2.0
reports the write-without-response payload length on macOS. Other platforms
use a 20-byte payload until their native behavior is verified; their OTA
throughput is unknown. An ACK means a sector was accepted into the application
queue, not written to flash. FFF2 and FFF1 INFO report committed flash bytes
and the same `idle`/`writing`/`ready`/`failed` stage mapping.

## Maintenance and verification

Before either upload, the client must confirm physical isolation: USB power
only, with ATX and register/instrument wiring disconnected. The backend
reserves the BLE device for the entire job, including work after HTTP 202.
On a connected ATX-capable image it sends `ATX PREPARE`, reads INFO and requires
OFF. The firmware also forces OFF at OTA START; ON commands and button presses
remain blocked until ESP32 restart, including after a failed transfer. An
unreachable device or older image cannot be switched off over BLE; physical
isolation is essential. See [wiring](WIRING.md) and [ownership](ARCHITECTURE.md).

USB provisioning selects a CP2102 port, releases the BLE connection and runs
PlatformIO's upload target, writing bootloader, partition table and application.
BLE OTA builds the current application and transfers it to the inactive slot.
The sender waits for ESP32 flash `ready` (15 s deadline on subscribed FFF2),
then reads one FFF1 INFO snapshot to verify `ready` and zero error. If the event
is missing but the link remains usable, it attempts one INFO reconciliation
with a fresh 10 s cancellation budget. A known flash error fails the job; an
unresolved result is `uncertain` and the image is never resent automatically.
If a sector-receipt timeout occurs after the device has finished flashing,
one INFO reconciliation checks `ready`, zero error and the complete image byte
count before proceeding to reboot. A missing receipt alone does not prove that
flash failed; incomplete or unconfirmed results do not trigger image replay.
An older image without FFF2 notifications uses bounded legacy ready reads for
its first update.

After BLE flash validation, the backend requests REBOOT. Both upload modes
reconnect and compare the running image identity with the built image, verify
a PING/PONG exchange, and confirm any trial image before reporting
`complete`. Progress reaching 100% alone is not success. The ESP-IDF partition
table has `ota_0`, `ota_1` and `otadata` with rollback enabled; an unconfirmed
trial rolls back after 60 seconds. If both application slots are unusable,
physical USB recovery is required. The accepted BLE transfer target is at most
60 seconds, not a guarantee on every host or radio link.

The browser has no manual upload-cancel action. Closing it does not cancel the
server job. Shutdown cancels owned work; a cancelled or failed operation must
be inspected before retry because boot selection may already be committed.
Native SimpleBLE calls may not stop immediately when a cancellation token
expires. The reservation stays owned until an in-flight call returns; it is
never released by a wrapper timeout while native work continues.

Maintenance events and PlatformIO output are written outside Git under the
system temporary directory's `surrklank-idf/`. Firmware does not enable Secure
Boot, flash encryption, signed-image authorization or anti-replay protection,
and does not change eFuses. Private legacy signing keys remain outside Git.
Maintenance is rejected while Laboratory owns instruments; OTA START also
checks this firmware lock. Stop and finish parking before maintenance.

## FDD Laboratory

`fdd_engine.cpp` owns platform-independent drive state and pulse scheduling;
`fdd_control.cpp` owns the ESP-IDF task, GPIO and 595/165 transfer. One scheduler
maintains a full 32-bit FDD output image, preserving the other drives when one
changes. The mapping is defined in [WIRING.md](WIRING.md). DIR HIGH means toward
TRACK0 in this software profile; /SELECT LOW selects the drive. SELECT is
asserted before preparation, kept through playing/manual parking and released at a
terminal state. Each DIR change precedes the next STEP by at least 5 ms.

Preparation homes at 100 steps/s until TRACK0 is active, steps outward until
TRACK0 releases (at most four pulses), then returns until TRACK0 activates.
Both transitions are required; a stuck LOW input is not accepted as a working
sensor. Every member must pass before COMMIT starts a batch. Preparation can
move a head even if another member eventually fails. An absent HIGH input
cannot distinguish an unplugged sensor from a missing drive, power or wiring
fault; the error says TRACK0 was not confirmed.

During playing, a drive receives 70 outward STEP commands and then returns
until TRACK0 is active. The return is not forced to 70 commands. Head position
is only estimated from issued pulses; reaching a pulse limit never counts as
successful parking. Per-drive duration starts at COMMIT and is timed on ESP32;
preparation is additional time. Duration expiry finishes the current STEP pulse
and enters `stopped`, releasing SELECT without returning the head to TRACK0.
Position and issued counts remain unchanged until the next start, which homes
and checks the drive again. Manual STOP still completes the current pulse and
parks at 100 steps/s.

The implementation profile permits 1–300 STEP pulses/s for 1–60000 ms.
For requests of 200 steps/s or higher, playing uses a high-rate startup profile:
it starts at 100 steps/s and ramps linearly in frequency over the first eight
issued playing steps of the whole tone. The ramp does not restart after a
reversal. Later traverses retain the requested cadence. High-rate playing uses
a 15 ms direction guard; lower-rate playing and preparation retain 5 ms.
The outward limit remains 70 commands and TRACK0 alone confirms a return,
with the unchanged 120-pulse limit. Startup and direction pauses lower the
whole-tone mean, so these recordings are not constant-rate trials for their
entire duration. Record firmware identity when comparing measurements.
Software timing diagnostics and successful completion do not establish the
absence of audible grain or faithful mechanical following of every command.
Each STEP is completed in the motion task: latch LOW, wait 30 microseconds,
then shift and latch HIGH.
The LOW interval includes that wait plus the HIGH-frame transfer and may be
extended by preemption; 30 microseconds is not a measured physical pulse width.
Homing/parking uses a 120-pulse or
two-second limit per seek phase. Playing returns also have a 120-pulse limit.
Late playing work beyond two current-profile periods faults rather than emitting
catch-up pulses. These values are software bounds, not measured accuracy or
a verified operating range for a particular FDD. Requested STEP frequency
does not guarantee an exact acoustic pitch; direction guards add pauses.

The 595 serializer uses one-microsecond DATA setup and CLOCK HIGH delays.
The 165 reader uses one-microsecond load/settle and clock half-period delays,
sampling QH before the first rising edge. These are configured delays;
they are software delays, not an electrical signal-integrity qualification.

A GPTimer alarm wakes the motion task every 100 microseconds through an ISR
notification. The motion task is pinned to CPU1 and creates/enables the timer
on that core; Bluetooth remains on CPU0 in this configuration. The callback
itself does not shift registers, acquire the engine mutex or send BLE data. STEP deadlines follow
an absolute per-drive cadence, so small dispatch and register-transfer delays do
not accumulate into a lower average rate. If dispatch is more than half a period
late, a fresh full period is scheduled to avoid a catch-up burst; playing delays
over two periods still fault. The LOW hold is referenced to the post-latch
timestamp and pulses are completed in the same motion iteration.
Task scheduling and BLE load can still delay edges; electrical accuracy is not
established by this scheduling rule.
The diagnostic build also records software latch intervals on the constant-rate
middle sections and STEP LOW durations. After a drive becomes stopped/error,
the lower-priority report task prints one `FDD_CADENCE` summary to UART. These
are internal timestamp observations, not independently measured pin edges;
printing occurs after the reported drive is terminal, outside the engine mutex. Opening the USB
serial port can reset this board, so bench capture opens it with ATX OFF before
connecting BLE and starting a trial.

The motion task completes all pending LOW pulses before releasing its mutex.
It hands snapshots to a fixed per-drive mailbox. A separate lower-priority task
copies and clears the mailbox under the mutex, then sends notifications outside
it. Slow BLE delivery can coalesce intermediate telemetry snapshots but cannot
block the motion task in a notification call. Phase/direction events remain in
the separate bounded event history. Task scheduling can still delay motion;
offline tests do not establish acoustic improvement or timing under radio load.
FFF2 telemetry and one-shot commands are
described in [BLE-PROTOCOL.md](BLE-PROTOCOL.md).

The adapter initializes register outputs only while ATX output is requested
ON. It shifts an inactive FDD image and zeroes the LSM/HDD branch before
enabling the shared /OE. LSM/HDD playback is not implemented. On ATX OFF it
disables /OE, releases driven bus pins and invalidates positions. While a
drive is active, firmware rejects ATX OFF/maintenance and ignores the GPIO13
button. ATX output is not a supply measurement; external power loss cannot
be detected directly by this design.

The host tests exercise the real scheduling engine with simulated sensors,
missed head movement, unequal return counts, parallel batches and stop/fault
paths. They do not verify electrical levels, SELECT jumper configuration,
actual motor movement, STEP/DIR timing under BLE load or playback pitch.
Physical checks on FDD 1 and 2 confirm sensor transitions, concurrent playing,
independent STOP, STOP ALL and final TRACK0 parking at the tested frequencies
(100, 110, 220 and 300 Hz). This is ESP32 telemetry evidence, not an external
position, frequency or voltage measurement. Other drives and disconnected-sensor
faults have not been exercised physically. Keep ATX OFF during uploads.

References: [Espressif BLE OTA example](https://github.com/espressif/esp-iot-solution/tree/5fbb2597b88f21ec41e952f81292ccd6ae569761/examples/bluetooth/ble_profiles/ble_ota),
[ESP-IDF OTA](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/system/ota.html).

## Timestamped FDD history

`laboratory_timing.h` owns a fixed 128-event ring, accessed through the engine
mutex in `fdd_control.cpp`. It records changes of phase, direction and batch
with boot-relative microsecond timestamps. FFF1 provides clock queries and
cursor-based replay; the motion worker performs no replay I/O. These timestamps
are software observations, not independently measured physical transitions.
See [timing v1](BLE-PROTOCOL.md#laboratory-timing-v1) for time boundaries and limits.
