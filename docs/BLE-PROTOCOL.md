# Surrklank BLE application protocol

The ESP32 is the GATT server and ASP.NET is the GATT client. Discovery and link
management happen outside these characteristics. The compatibility discovery
name is `EM-MIDI-IDF`; existing UUIDs and Espressif's OTA profile remain stable.

## FFF1: commands and replies

Service `0xFFF0`, characteristic `0xFFF1` (Write / Read). A client writes one
ASCII command shorter than 64 bytes and reads the last reply (up to 512 bytes).
The backend serializes native exchanges through a device reservation; see
[application architecture](ARCHITECTURE.md).

| Command | Reply / purpose |
| --- | --- |
| `ATX ON`, `ATX OFF` | Explicit output request; refused during conflicting ownership |
| `ATX PREPARE` | Force OFF and reject ON until restart; refused while Laboratory is active |
| `INFO` | JSON snapshot with image identity, OTA state, ATX state and sequences |
| `PING <digits>` | Matching `PONG <digits>`; initiated manually |
| `CONFIRM` | Confirm a trial image; `VALID` on success |
| `REBOOT` | Restart after validated flash; `REBOOTING` on success |
| `LAB BEGIN <batch> <mask>` | Reserve one pending batch; bit 0 selects FDD 1, bit 7 FDD 8 |
| `LAB SET <batch> <device> <mHz> <ms>` | Stage frequency and duration for one member |
| `LAB PREPARE <batch>` | Home/check every staged member; no musical start |
| `LAB COMMIT <batch>` | Start all members only if every member is ready |
| `LAB ABORT <batch>` | Cancel this pending batch and park its active members |
| `LAB STOP <device>`, `LAB STOPALL` | Stop and park one/all drives; also cancel affected preparation |
| `LAB INFO <device>` | JSON telemetry for one FDD, numbered 1–8 |

FFF1 is a request/reply command channel. BLE connection, disconnection and
discovery are link operations, not FFF1 commands. The OTA image is transferred
through Espressif's separate service; see [firmware operation](FIRMWARE.md).

`INFO` advertises `laboratory_version: 1` when Laboratory is supported. LAB
commands reply `LAB OK` or `ERR LAB BUSY OR INVALID`; `LAB INFO` returns JSON.
Batch IDs are nonzero 32-bit integers. A pending batch has a 30-second lease;
expiry faults its members without starting them. BEGIN rejects overlap with
active devices or another pending batch. ABORT only affects the matching
pending batch, never an older committed batch. See [motion semantics](FIRMWARE.md#fdd-laboratory).

## FFF2: readable snapshot and notifications

Service `0xFFF0`, characteristic `0xFFF2` (Read / Notify). A read returns a JSON
snapshot. Compatible images advertise `events_version: 1`, `atx_sequence` and
`firmware_sequence`. The backend reads FFF2 before subscribing to detect this
capability, subscribes, then requests a fresh `INFO` through FFF1. It never
reads FFF2 after subscription. On macOS, SimpleBLE's [read implementation](https://github.com/simpleble/simpleble/blob/main/simpleble/src/backends/macos/PeripheralBaseMacOS.mm)
waits for another notification when reading a notifying characteristic; an
idle stream may therefore leave that read pending.

FFF2 notifications carry typed binary state events. All frames fit in the
minimum 20-byte ATT value payload; multi-byte values are little-endian.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 1 | Protocol version `1` |
| 1 | 1 | Type: `1` ATX, `2` firmware, `3` Laboratory state, `4` Laboratory parameters |
| 2 | 4 | Unsigned sequence, per stream and boot |
| 6 | 1 | ATX: `0` OFF / `1` ON; total frame length 7 |
| 6 | 1 | Firmware: `0` idle / `1` writing / `2` ready / `3` failed |
| 7 | 4 | Firmware bytes committed to flash |
| 11 | 4 | Signed ESP-IDF error; firmware frame length 15 |

ATX events follow GPIO19 output changes from FFF1 commands or the GPIO13
button. The button is sampled and debounced locally every 10 ms. Firmware
events follow flash state and committed-byte changes; accepted transfer bytes
are a separate count. Firmware INFO and FFF2 use the same stage mapping.

`DeviceState` merges INFO snapshots and notifications under the BLE session
lock. It rejects malformed, unknown-version, duplicate and older frames, and
ignores callbacks from an old session. Unsigned 32-bit sequences are compared
with wrap-around and reset on a new BLE session/boot. A delayed snapshot cannot
replace a newer accepted event.

Notifications have no application acknowledgment, so intermediate events are
not guaranteed to arrive. On link loss, ATX and device flash state become
unknown; reconnect resubscribes and synchronizes them. Explicit ATX commands
are followed by one INFO snapshot. A detected sequence gap queues one INFO
refresh after any ongoing maintenance, outside the notification callback. If
refresh fails, the backend disconnects and marks state unknown. A final lost
physical-button event followed by silence cannot be detected by this scheme;
there is no strict freshness bound until reconnect. There is no periodic ATX
read.

## Laboratory FFF2 events

Both Laboratory frames are 20 bytes. They share a per-device sequence and
are merged independently by type, so parameters cannot overwrite newer state.

| Offset | Type 3: state | Type 4: parameters |
| --- | --- | --- |
| 0–1 | Version `1`, type `3` | Version `1`, type `4` |
| 2–5 | Device sequence, uint32 | Same sequence, uint32 |
| 6 | Device 1–8 | Device 1–8 |
| 7 | Phase, uint8 | Frequency in millihertz, uint32 (7–10) |
| 8–11 | Batch ID, uint32 | Duration in ms, uint32 (11–14) |
| 12 | Error, uint8 | Return STEP count, uint16 (15–16) |
| 13 | Flags, uint8 | Estimated position, int16 (17–18); negative means unknown |
| 14–15 | Issued STEP count, uint16 | Reserved byte 19, zero |
| 16–19 | Elapsed playing time in ms, uint32 | — |

Phase codes: 0 unknown, 1 staged, 2 homing, 3 checking_out, 4 checking_return,
5 ready, 6 playing, 7 parking, 8 parked, 9 error, 10 stopped (duration elapsed;
head remains in place until the next preparation).
Flags: bit 0 TRACK0 valid, bit 1 TRACK0 active, bit 2 left TRACK0 during the
outward leg, bit 3 direction toward zero. Error codes: 0 none, 1 TRACK0 not
confirmed, 2 TRACK0 did not release, 3 return limit, 4 scheduling deadline,
5 batch aborted, 6 power request lost, 7 preparation lease expired.

`LAB INFO n` carries the same fields as named JSON: `device`, `sequence`,
`batch`, `state`, `frequency_hz`, `duration_ms`, `elapsed_ms`, `track0`,
`left_track0`, `toward_zero`, `steps_issued`, `return_steps`, `position_estimate`
and `error_code`. The backend adds `device_type: "fdd"` and a human-readable
`message` in the browser envelope. TRACK0 is the last sampled input; position
and STEP counts are estimates/issued commands, not measured head displacement.

Firmware pushes changed state plus a refresh every 250 ms while any drive is
active and every second when idle. A later push repairs a lost final
Laboratory event. These are device-originated snapshots, not backend polling.
Detected sequence gaps, an explicit command or an uncertain outcome can cause
one FFF1 reconciliation. Reconnect reads all eight `LAB INFO` snapshots after
subscription. No Laboratory code reads subscribed FFF2.

## Compatibility and browser boundary

An older image without `events_version` remains readable and can receive one
OTA upgrade. It cannot publish FFF2 events, so its flash-ready check uses
bounded reads. Images advertising event version 1 require a successful FFF2
subscription. The backend translates device state into JSON snapshots on the
browser's existing `/ws`; its socket remains open while the ESP32 reboots.

## Laboratory timing v1

Timing is an additive FFF1 extension; existing FFF2 frames and UUIDs are unchanged.
`LAB CLOCK` returns `timing_version: 1`, a boot-scoped random uint32
`esp_boot_id`, `event_cursor`, `esp_receive_time_us`, and `esp_send_time_us`.
The receive stamp is taken on entry to the Laboratory command handler; the send
stamp is taken before reply formatting, not on-air transmission. Both use
`esp_timer_get_time()`. The exchange includes native transport and reply work.
The boot identifier distinguishes restarts probabilistically; it is not a persistent identity.

`LAB EVENT <cursor>` returns the oldest retained event newer than the cursor,
plus `esp_boot_id` and `latest`. `event` is null when none remains. Events contain
`event_sequence`, `device`, `batch`, `state`, `toward_zero`, `esp_event_time_us`.
The fixed ring retains 128 phase/direction/batch changes across all eight FDDs.
A first returned sequence greater than cursor+1 means records were overwritten.
No per-STEP events are emitted. Sequence wrap is outside timing v1's supported
capture lifetime; restart or a cursor ahead of latest requires a new capture.

Events are captured under the engine lock: command-side transitions after command
execution; worker transitions after output update (or pin release). These are
software observation times, not exact latch-edge, sensor-motion or audio times.
Only bounded memory operations occur in the motion path; replay is request-driven.
Older firmware rejects the extension without changing motion commands.

`POST /api/laboratory/clock` performs one reserved clock exchange.
`POST /api/laboratory/events?after=N` drains up to 128 retained events under one
native reservation and returns `type: laboratory_timing`, `clock`, `after`, `next`,
`gap`, and `events`. Local Origin is required, as for play/stop. Busy is 409;
unsupported timing, malformed replies, disconnection or reboot during replay is 503.
The envelope is also published on `/ws` after replay and on subsequent snapshots.
It is retained history, not a continuously pushed live event stream: consumers
must refresh through the endpoint, deduplicate by boot/sequence, and never treat
socket arrival as event time. Clock stamps are ESP boot-relative microseconds;
backend-created notifications do not acquire fabricated ESP timestamps.
