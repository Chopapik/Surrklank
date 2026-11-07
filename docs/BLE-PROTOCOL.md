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
| `ATX ON`, `ATX OFF` | Explicit output request; matching reply or `ERR MAINTENANCE` |
| `ATX PREPARE` | Force OFF and reject ON until restart; reply `ATX OFF` |
| `INFO` | JSON snapshot with image identity, OTA state, ATX state and sequences |
| `PING <digits>` | Matching `PONG <digits>`; initiated manually |
| `CONFIRM` | Confirm a trial image; `VALID` on success |
| `REBOOT` | Restart after validated flash; `REBOOTING` on success |

FFF1 is a request/reply command channel. BLE connection, disconnection and
discovery are link operations, not FFF1 commands. The OTA image is transferred
through Espressif's separate service; see [firmware operation](FIRMWARE.md).

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
| 1 | 1 | Type: `1` ATX, `2` firmware |
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

## Compatibility and browser boundary

An older image without `events_version` remains readable and can receive one
OTA upgrade. It cannot publish FFF2 events, so its flash-ready check uses
bounded reads. Images advertising event version 1 require a successful FFF2
subscription. The backend translates device state into JSON snapshots on the
browser's existing `/ws`; its socket remains open while the ESP32 reboots.
