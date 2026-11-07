# Application architecture

Surrklank runs one ASP.NET Core backend process. `Program.cs` serves the React
build from `frontend/dist`, maps controllers and starts the BLE and firmware
hosted services. Vite is a separate development server only; it proxies `/api`
and `/ws` to ASP.NET. The ESP32 is the BLE GATT server; ASP.NET is its client.

Backend code is grouped under `backend/Features/`: `Connection`, `Atx`,
`Firmware` and `Application`. Each feature owns its controller, service and
DTOs. `Shared/Http/LocalOrigin.cs` holds the origin check reused by HTTP and
WebSocket boundaries. The composition root remains `backend/Program.cs`.

## Request and state flow

| Boundary | Responsibility |
| --- | --- |
| REST controllers | Read snapshots, validate ATX/firmware requests and return HTTP status |
| `WebSocketController` | Accept `/ws`, send `state` snapshots and receive `connect`, `disconnect`, `ping` |
| `BleConnectionService` | Discover, own one BLE session, serialize native operations, decode device state |
| `AtxService` | Send explicit ATX commands and prepare maintenance |
| `ApplicationStateService` | Combine feature snapshots for HTTP and WebSocket responses |
| `FirmwareService` | Start/stop the background job and retain the device reservation |
| `FirmwareUpdateUseCase` | Coordinate preparation, build, transfer, reboot and image verification |
| `FirmwareJobState` | Own job snapshots, progress events and maintenance logs |
| `PlatformIoToolchain` | Enumerate CP2102 ports and execute PlatformIO builds/USB uploads |
| `BleOtaService` | Transfer the image using Espressif's official BLE OTA profile |
| `StateService` | Wake browser WebSocket senders when snapshots change |

`GET /api/connection` returns an on-demand `ApplicationDto` with `connection`
and `firmware`. `/ws` sends the same state when subscribed and after changes;
the browser keeps this socket during ESP32 reboot. Firmware progress is pushed,
not polled through REST. The React connection hook stores WebSocket snapshots in
Zustand; the firmware hook receives job snapshots through React Query's cache.
Browser storage contains only a last-known connection label for startup display,
not an authoritative ATX state. A closed browser socket makes device actions
unavailable until it reconnects.

The frontend keeps one presentation component, `App.tsx`, with behavior in
feature hooks and HTTP operations in each feature's `.api.ts` module.
`useDeviceControls` coordinates availability and labels across connection, ATX
and firmware features. Shared
HTTP error decoding lives in `shared/http/readResponse.ts`. Zod schemas at the
HTTP/WebSocket boundaries validate incoming data and supply TypeScript types;
invalid socket messages do not update caches or stores. Optional fields from
older connection snapshots are normalized before entering application state.

The firmware reports ATX output and flash state through FFF2 notifications.
On connection the backend reads an initial device snapshot, subscribes and
requests a follow-up FFF1 `INFO` snapshot. `DeviceState` merges snapshots and
events by per-stream sequence. ESP32 state becomes unknown on BLE link loss.
The backend also watches the native library's cached connection state every
100 ms as a fallback for a missed disconnect callback; this is not an ATX poll.
See [BLE protocol](BLE-PROTOCOL.md) for event framing and delivery limits.

## Native-device ownership

`BleConnectionService.ReserveAsync` returns a disposable `DeviceOperation`.
It owns access to the private BLE semaphore and peripheral. Discovery, manual
WebSocket actions, ATX commands, state reconciliation and maintenance share this
reservation. Await all native calls before disposing it; overlapping calls on
one reservation are unsupported. The reason is visible as
`connection.operation`; a conflicting ATX or firmware HTTP request returns 409
with `detail` and `operation`. The UI disables conflicting controls and shows
the maintenance reason. WebSocket publication does not need a reservation.

ATX and firmware workflows depend on `IDeviceConnection` and `IDeviceOperation`,
which expose owned operations without a native peripheral or semaphore. The
production implementation is the same singleton `BleConnectionService` used by
the hosted service. `IFirmwareToolchain` separates build/USB process execution
from the update policy. These contracts allow offline substitutes for future
workflow tests; there is no persistence repository in this application.

`FirmwareService` retains the reservation after returning HTTP 202. It runs
`FirmwareUpdateUseCase` inside the background job and releases the reservation
during cleanup. For USB the use case releases BLE before PlatformIO upload;
for BLE OTA it uses the existing session and the official OTA profile. Both
require physical-isolation confirmation. See [firmware operation](FIRMWARE.md)
for the update sequence and uncertain outcomes.

## Current limits

There is no instrument playback or drive/register control. The app has no
manual firmware-cancel command. FFF2 delivery is not acknowledged by the
application, so an isolated final lost event can remain unseen until reconnect.
The backend reconciles detected sequence gaps and explicit ATX commands with a
one-shot INFO request; it does not poll ATX periodically. Physical ATX output
voltage and PWR_OK are not measured.
