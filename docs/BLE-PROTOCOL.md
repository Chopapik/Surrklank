# Surrklank BLE application protocol

The ESP32 is the GATT server; ASP.NET is the GATT client. Connection/discovery
use the BLE library independently of the characteristic commands below.
The discovery name remains `EM-MIDI-IDF`. UUIDs remain unchanged.

## FFF1: commands and replies

Service FFF0, characteristic FFF1 (Write / Read). The backend serializes each
write/read exchange with the shared device gate. Commands are ASCII, shorter
than 64 bytes. Read returns the last reply, up to 512 bytes.

| Command | Reply / purpose |
| --- | --- |
| `ATX ON`, `ATX OFF` | Explicit output request; matching reply, or `ERR MAINTENANCE` |
| `ATX PREPARE` | Lock the output OFF until restart; reply `ATX OFF` |
| `INFO` | JSON snapshot, including image identity, OTA state, ATX and sequences |
| `PING <digits>` | `PONG <digits>`; manual only |
| `CONFIRM` | Confirm the current trial image; reply `VALID` on success |
| `REBOOT` | Restart after verified flash; reply `REBOOTING` on success |

## FFF2: initial information and subscribed state

FFF2 remains readable for existing clients and initial capability detection.
It adds the Notify property/CCCD. New snapshots advertise `events_version: 1`,
`atx_sequence` and `firmware_sequence` along with the existing fields.

After connecting, the backend reads FFF2 before subscribing, subscribes to its
notifications, then requests INFO through FFF1. Reads after subscription also
use FFF1 INFO. Each stream's snapshot/notification sequence is merged under the
BLE owner's state lock, so a delayed read cannot overwrite a newer event.
Sequence numbers are unsigned 32-bit, compared with wrap-around and reset for
each new BLE session/boot. Duplicate, older, malformed and unknown-version
frames are ignored. Callbacks from a disposed/previous session are ignored.

All notification frames fit within the minimum 20-byte ATT value payload.
Multi-byte integers are little-endian. The backend translates binary events
into JSON snapshots for browsers.

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 1 | Protocol version = 1 |
| 1 | 1 | Type: 1 ATX, 2 firmware |
| 2 | 4 | Sequence, scoped to this stream and boot |
| 6 | 1 | ATX: 0 OFF / 1 ON; total frame length 7 |
| 6 | 1 | Firmware: 0 idle / 1 writing / 2 ready / 3 failed |
| 7 | 4 | Firmware: bytes committed to flash |
| 11 | 4 | Firmware: signed SDK error; total frame length 15 |

ATX events follow output changes from both commands and the physical GPIO13
button. The button's existing 10 ms local sampling/debounce is retained.
Firmware events follow state transitions and committed flash blocks. Domain
modules invoke their BLE listeners outside their own state locks.

Notifications are not application-acknowledged and this revision does not
claim guaranteed delivery of every intermediate event. On link loss ATX and
device flash state become unknown; reconnect resubscribes and resynchronizes.
There is no periodic ATX reconciliation read.

## Firmware transport and browser updates

The official Espressif service 8018 and characteristics 8020/8022 still own
image transfer, command ACKs and sector receipts. FFF2 is application status,
not a replacement for that protocol. ASP.NET owns build/send progress; ESP32
owns flash status. Browser `/ws` snapshots expose both `firmware` job state and
`connection.device_firmware` alongside `connection.atx_on` and `subscribed`.
The existing WebSocket stays open during ESP32 disconnect/reboot.

New firmware waits use FFF2 state changes and a 15 s flash-ready deadline;
then one INFO snapshot verifies ready/error before requesting REBOOT. Reconnect
still checks image identity, manual ping and trial confirmation.

Manual upload cancellation was removed from the UI and WebSocket command API.
Application shutdown still stops owned work, and transport errors/timeouts are
handled. Unrequested interruptions are not equivalent to successful upload.

## Compatibility migration

A legacy image without `events_version` can be connected and upgraded once.
It cannot push state, so there is no ATX polling; legacy command confirmation
uses a one-shot read. The legacy OTA flash-ready check retains its old bounded
reads only for that first upgrade. New images require successful subscription
and do not use that fallback. This allows OTA-only migration without USB.

## macOS read behavior

During this implementation, a read issued after subscribing to FFF2 hung in
`SimpleSharpBLE.Peripheral.ReadCore`; HTTP still reported `subscribed: true`
and connection `connecting`. The new image was not confirmed and the device
subsequently returned to its previous confirmed identity.

SimpleBLE's macOS implementation [read method](https://github.com/simpleble/simpleble/blob/main/simpleble/src/backends/macos/PeripheralBaseMacOS.mm)
waits for the next notification when `characteristic.isNotifying` is true.
An idle stream therefore does not complete that read. INFO over FFF1 avoids
this path. Successful physical migration/reconnect after this change is recorded
in [validation](BLE-PROTOCOL-VALIDATION.md). This reproduces and explains this
new failure; it does not prove every earlier reverted failure had the same cause.
