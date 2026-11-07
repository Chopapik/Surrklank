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

The sender respects the advertised window, capped at three sectors with
495-byte ATT payloads or one sector with smaller payloads. SimpleBLE 1.2.0
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
Only GPIO19 ATX control and the GPIO13 button are implemented; instrument and
register control are outside the current firmware.

References: [Espressif BLE OTA example](https://github.com/espressif/esp-iot-solution/tree/5fbb2597b88f21ec41e952f81292ccd6ae569761/examples/bluetooth/ble_profiles/ble_ota),
[ESP-IDF OTA](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/system/ota.html).
