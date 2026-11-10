# Application architecture

Surrklank runs one ASP.NET Core backend process. `Program.cs` serves the React
build from `frontend/dist`, maps controllers and starts the BLE and firmware
hosted services. Vite is a separate development server only; it proxies `/api`
and `/ws` to ASP.NET. The ESP32 is the BLE GATT server; ASP.NET is its client.

Backend code is grouped under `backend/Features/`: `Connection`, `Atx`,
`Firmware`, `Laboratory` and `Application`. Each feature owns its controller, service and
DTOs. `Shared/Http/LocalOrigin.cs` holds the origin check reused by HTTP and
WebSocket boundaries. The composition root remains `backend/Program.cs`.

## Request and state flow

| Boundary | Responsibility |
| --- | --- |
| REST controllers | Read snapshots, validate ATX/firmware requests and return HTTP status |
| `WebSocketController` | Accept `/ws`, send `state` snapshots and receive `connect`, `disconnect`, `ping` |
| `BleConnectionService` | Discover, own one BLE session, serialize native operations, decode device state |
| `AtxService` | Send explicit ATX commands and prepare maintenance |
| `LaboratoryService` | Validate stop requests and exchange Laboratory commands |
| `PlayLaboratoryBatchUseCase` | Validate, prepare, await readiness and commit an FDD batch |
| `LaboratoryState` | Merge FFF2 device telemetry and FFF1 snapshots; invalidate lost state |
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

The same `/ws` also sends a separate `laboratory` envelope with `available`,
`supported` and eight `devices`. One sender serializes both message types.
React validates the envelope and writes it to the Laboratory Zustand store.
HTTP acceptance never invents a playing or parked state. A closed browser
socket invalidates Laboratory state, TRACK0 and estimated position immediately.

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

## Laboratory batches

`POST /api/laboratory/play` accepts, for example:

```json
{"devices":[
  {"device_type":"fdd","device":1,"frequency_hz":220,"duration_ms":3000},
  {"device_type":"fdd","device":2,"frequency_hz":110,"duration_ms":5000}
]}
```

The request allows 1–8 distinct FDDs, numbered 1–8, at 1–300 Hz for
1–60000 ms. ATX output must be ON and event-capable Laboratory firmware must
be connected. Only one new batch can prepare at a time. Existing independent
batches keep playing. Each short FFF1 exchange owns the native reservation;
waiting for preparation and playing do not hold it, so STOP remains possible.

The use case stages all parameters, requests preparation and waits for every
requested drive to become `ready` over FFF2. Only then does one COMMIT start
the batch. A preparation failure aborts the new batch without starting musical
pulses; preparation itself moves heads. After eight seconds without confirmed
readiness, one FFF1 snapshot refresh has a separate five-second budget. The
use case then commits or aborts; it does not continuously poll readiness.
Request cancellation also attempts abort with an independent cleanup budget.

`POST /api/laboratory/stop` accepts `{"device_type":"fdd","device":1}`;
`POST /api/laboratory/stop/all` has no body. Stopping a preparing member
cancels its whole pending batch; unrelated playing batches continue. Accepted
play/stop requests return 202. Application validation uses 400 and conflicts
use 409, with `message` and an operation reason when available. Framework
model-binding errors retain ASP.NET ProblemDetails. An unconfirmed command
outcome uses 503; a lost COMMIT reply is never automatically retried.

ATX OFF and firmware maintenance reject active/preparing Laboratory work.
ESP32 independently locks ATX while drives are active, including parking.
Unknown outcomes keep maintenance blocked until state synchronization resolves
them. Native BLE loss invalidates Laboratory state; reconnect subscribes and
reads eight FFF1 device snapshots before publishing availability. Playing is
timed locally and can finish even if the browser/backend disconnects. Duration
expiry enters inactive `stopped` without parking; the next play request homes
the head before starting. Manual STOP retains explicit parking.

## Current limits

Only FDD Laboratory playback is implemented; LSM/HDD and MIDI playback are not.
Two physical FDDs pass playback/parking and stop checks; electrical levels,
pulse accuracy and other drive models remain unverified.
The app has no manual firmware-cancel command. FFF2 delivery is not acknowledged by the
application, so an isolated final ATX/firmware event can remain unseen until reconnect.
The backend reconciles detected sequence gaps and explicit ATX commands with a
one-shot INFO request; it does not poll ATX periodically. Physical ATX output
voltage and PWR_OK are not measured.

## Timing correspondence

LaboratoryService owns reserved, read-only clock and event-history exchanges.
LaboratoryController exposes `/api/laboratory/clock` and `/api/laboratory/events`.
The single WebSocket sender additionally publishes the last requested
`laboratory_timing` history envelope. Replay buffers can overwrite old events;
clients must detect gaps and restarts. Replay never substitutes for live state
or initiates motion. See [timing contract](BLE-PROTOCOL.md#laboratory-timing-v1).
