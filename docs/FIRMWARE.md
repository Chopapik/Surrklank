# Surrklank ESP-IDF firmware: BLE and OTA

## Dependencies and ownership

PlatformIO `espressif32@6.12.0`, ESP-IDF package `3.50500.0` (IDF 5.5).
Arduino and NimBLE-Arduino are not dependencies.
Espressif `ble_conn_mgr`, `ble_services` and `ble_ota_raw` are Git dependencies
pinned to `5fbb2597b88f21ec41e952f81292ccd6ae569761`; see `src/idf_component.yml`.
The component manager downloads them as generated dependencies, not application code.

`atx_power.cpp` initializes GPIO19 LOW, debounces GPIO13 and owns the ATX maintenance lock.
`main.cpp` initializes ATX before NVS, the event loop, connection and OTA modules.
`ble_connection.cpp` uses the official connection manager and advertises the
legacy identifier `EM-MIDI-IDF` so existing Surrklank clients can discover it. It
registers the small command/info service and observes native connection events.
It requests standard 251-byte Data Length Extension and a 15 ms interval; actual
MTU and connection interval are observed, not assumed.
`ota_update.cpp` connects the official OTA profile to the SDK flash/boot APIs.
It copies completed sectors to a bounded FreeRTOS queue and writes outside the
BLE callback. A static 64 KiB buffer batches `esp_ota_write()` calls at hardware
erase-block boundaries; this trades 64 KiB of RAM for fewer erase operations. Session epochs discard queued data from an aborted transfer.
The ESP-IDF project name is `surrklank`; it appears in the firmware image's
application metadata. The BLE name, UUIDs, existing commands and OTA wire protocol are
unchanged. FFF2 gains the Notify property and its CCCD. ATX commands extend the existing command characteristic. The queue/window sizes bound memory use. `OTA_WITH_SEQUENTIAL_WRITES` keeps
bulk erase out of the NimBLE START callback; erasure happens in the flash task. Disconnect/timeout aborts an incomplete
flash session without selecting it for boot. The official STOP command resets
the profile after disconnect. A completed boot selection is retained.

## Connection service

Vendor service `0xFFF0`: command characteristic `0xFFF1` (Write / Read) and
information/event characteristic `0xFFF2` (Read / Notify). Write `PING <digits>` and read the
matching `PONG <digits>`. The backend never schedules heartbeat pings.
Information is JSON with the application ELF SHA-256 identity, version, slot,
trial state, flash progress, reset reason and last SDK error. Native NimBLE
connection interval and latency are also reported. `CONFIRM` accepts a trial image
and `REBOOT` is allowed only after a completed OTA image has been validated.
`ATX ON` and `ATX OFF` set an explicit output state. `ATX PREPARE` forces OFF
and locks out ON until restart. The information JSON adds `atx_on`; it describes
GPIO19 output state, not measured power. `INFO` returns the same JSON through
FFF1. FFF2 publishes typed, sequenced ATX and flash-state notifications; ATX is
not polled. The backend uses FFF1 INFO after subscribing to avoid SimpleBLE's
macOS read-on-notifying behavior. See [BLE protocol](BLE-PROTOCOL.md).
These application commands do not replace the official OTA transfer protocol.

## Official OTA protocol

Service `0x8018`, receive firmware `0x8020`, command `0x8022`.
Subscribe to receive/command notifications before START. Commands are 20 bytes:
uint16 LE opcode (START=1, STOP=2), firmware size uint32 LE for START, reserved
bytes, CRC16-XMODEM at bytes 18..19. Command ACK is opcode 3, echoed command and
status 0 on acceptance. Byte 6 advertises the sector send window.
Firmware packets contain uint16 LE sector index, uint8 packet sequence and data.
Final sequence 0xFF includes CRC16-XMODEM of that sector. Sectors contain at most
4096 firmware bytes. ACKs include sector index, status and packet CRC16.
The ASP.NET sender follows this published framing; it does not create another
DATA/BLOCK/CREDIT protocol. The sender respects the receiver-advertised window, limited to three sectors at
495-byte ATT payloads, or one sector for smaller payloads. SimpleBLE 1.2.0 reports
the write-without-response payload length on macOS. Until other platforms are verified,
the sender uses the minimum 20-byte payload there; their OTA performance is unknown. It drains official
sector receipts after each window; no extra credit protocol is introduced.

Sector ACK means accepted into the application queue, not committed flash.
The backend waits for the flash state `ready`, then requests restart, reconnects,
compares the running ELF identity with the built image, verifies ping and confirms
a pending trial. Progress reaching 100% alone is not reported as success.
No lost command or uncertain transfer is replayed automatically.

## Boot and update limits

Partition table has `ota_0`, `ota_1` and `otadata`; rollback is enabled in the
compiled bootloader. An unconfirmed trial requests rollback after 60 seconds.
Ordinary BLE OTA writes only the inactive application; first USB provisioning
also writes the ESP-IDF bootloader and partition table. ATX control is limited to GPIO19 and the GPIO13 button; there is no instrument
or playback control. Maintenance is only for the isolated board. ATX is forced
OFF before OTA flash writes and remains locked OFF until restart, even after a
cancelled/failed transfer. See [ATX validation](ATX-VALIDATION.md).

The official CRC and ESP image checks detect damaged transfers. This revision
does not claim signed image authorization, encrypted OTA or anti-replay protection.
The old private signing key remains outside the repository and is not overwritten.
The firmware does not enable Secure Boot, flash encryption or write any eFuse.
Physical recovery still requires USB if both application slots are unusable.

## Validation in this repository

On 2026-11-06, the former Python application was installed and built independently in
`electromechanical-midi-core`, using a new venv and generated build directories.
The isolated ESP32-D0WD-V3 / CP2102 remained USB-only, with no ATX or actuator power.

| Check | Observed result |
| --- | --- |
| Offline tests | 19 passed; fake BLE only |
| ESP-IDF build | Passed from the new directory; pinned IDF 5.5.0, rollback enabled |
| USB upload | 36.294 s upload command; reconnect, identity and ping verified |
| Manual BLE ping | 116.1 ms; disconnect/reconnect also verified |
| Official BLE OTA, 550160 bytes | 22.631 s transfer/flash validation |
| Complete OTA operation | 2.560 s build + 25.092 s subsequent operation = 27.652 s |
| Final boot | Version 0.1.7, slot 0x1f0000, trial false, matching ELF identity |
| Final ping | 72.7 ms after OTA |
| HTTP / WebSocket | Page and API respond; firmware progress and connection transitions received over /ws |

Image SHA-256: `3854a82c49b1688f8227883c6d04e448408ad00861d3c1477c2d69137621bc8f`.
ELF identity: `1df5d5e45169284e40b37f9edfb8077243ba3ca7f37e86e4a0b007d306d25b41`.
Link during OTA: MTU 498, 495-byte packets, window 3, interval 15 ms.
Current ASP.NET maintenance logs are stored outside Git in the system temp
directory's `surrklank-idf/`. For the historical Python run, detailed jobs were
stored outside Git under the system temp directory's
`electromechanical-midi-idf/validation.jsonl` and job-specific build/upload logs.

These measurements predate the ASP.NET migration and do not verify the C# sender.

Cancelled-transfer recovery and physical trial rollback were tested in the
source project before extraction. They were not repeated during this migration.
Physical Windows support, abrupt power-cut detection latency and long-duration
endurance remain untested. The accepted transfer target is <=60 s; these observed
measurements are not a guarantee for every host/radio environment.

## Connection loss reporting

The application observes native disconnect callbacks and, every 100 ms, the BLE library's
cached connection state as a fallback. The observer performs no BLE reads,
writes or pings. State changes from native callbacks are synchronized before publishing WebSocket snapshots. A disconnect during
initial device-info reading cannot restore a stale connected state. If WebSocket
itself closes, the page shows BLE state as unknown and disables device actions.

The historical Python offline suite covered native callbacks, cached-state loss without a callback,
cross-thread publication and disconnect during setup. It does not validate the ASP.NET migration.
No physical power-cut test was performed. The OS/controller must detect abrupt link loss before it can be
reported; this still depends on the BLE supervision timeout.

References: [official example](https://github.com/espressif/esp-iot-solution/tree/5fbb2597b88f21ec41e952f81292ccd6ae569761/examples/bluetooth/ble_profiles/ble_ota),
[ESP-IDF OTA](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/system/ota.html).
