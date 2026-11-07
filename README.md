# Surrklank

Surrklank contains a local ASP.NET Core application and minimal ESP-IDF
firmware for an isolated ESP32. The browser connects to the application over
HTTP and WebSocket; the application communicates with the ESP32 using BLE.

## Run the application

Install the .NET 10 SDK, Node.js 24 or newer, npm and PlatformIO Core. Build
the frontend once after cloning or updating its dependencies:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
```

Run `python3 run.py` (Windows: `py run.py`) and open <http://127.0.0.1:5173>.
The Python script only launches `dotnet run`; the backend is entirely C#. You
can also run `dotnet run --project backend/Surrklank.csproj` or
the Rider run configuration directly. ASP.NET serves the React build from
`frontend/dist`, so production use needs one application process.

For frontend development, keep ASP.NET running and run
`npm --prefix frontend run dev` in a second terminal. Open <http://127.0.0.1:5174> for live updates;
Vite forwards `/api` and `/ws` to ASP.NET. Rebuild the frontend after changes
when serving it directly from ASP.NET. The generated `dist/` and `node_modules/`
are not committed.

The application uses [SimpleSharpBLE 1.2.0](https://www.nuget.org/packages/SimpleSharpBLE/1.2.0)
for native BLE. It packages desktop libraries for Apple Silicon macOS, Windows
x64/ARM64 and Linux x64/ARM64; Intel macOS is not included. On macOS, grant
Bluetooth permission to the terminal or application launching the server. On
Linux, BlueZ and D-Bus are required. SimpleBLE uses the Business Source License
1.1, with a non-commercial production grant; check its license before commercial
use. The first .NET restore needs access to NuGet.

For compatibility with existing firmware and clients, the Surrklank device keeps
the BLE discovery identifier `EM-MIDI-IDF`. The application scans for it in the
background and connects automatically.
After link loss it searches again. Explicit disconnect pauses automatic connection;
click Connect to resume. Click **Ping** for a manual check.
There is no automatic heartbeat. Scanning pauses during device operations.
Connection, ping results and firmware progress arrive over `/ws`; the page does
not poll REST for progress. Reopening WebSocket receives the current snapshot.

## ATX control

The ATX switch sends `PUT /api/atx` with `{"state":"on"}` or `{"state":"off"}`.
There is no toggle command. GPIO19 drives the transistor described in
[WIRING.md](docs/WIRING.md); GPIO13 is the debounced physical button.
The ESP32 starts OFF. `connection.atx_on` is `true`, `false`, or `null` when
unknown/disconnected/unsupported. It represents the driven output, not voltage
or PWR_OK. The UI uses WebSocket snapshots stored in Zustand, with no optimistic
state update or persisted ATX value.

`FFF1` carries commands and replies, including `INFO` for a current snapshot.
`FFF2` carries subscribed ATX and firmware flash-state events; the backend no
longer polls ATX. On connect it reads the information once to detect capabilities,
subscribes, then requests `INFO` through FFF1. Sequence numbers prevent a late
snapshot from overwriting a newer event. SimpleBLE/macOS waits for the next event
when reading a notifying characteristic, so subscribed FFF2 must not be read.
See [BLE application protocol](docs/BLE-PROTOCOL.md) for framing and migration.

Before maintenance, a connected compatible device receives `ATX PREPARE` and
must confirm OFF. The firmware also forces OFF at OTA START. ON commands and
button presses are blocked until ESP32 restarts, including after failed or
interrupted uploads. An initial upgrade from pre-ATX firmware, or USB provisioning
without BLE, still relies on the explicit physical-isolation confirmation;
software cannot verify or switch off an unreachable device.

## Firmware upload

Keep the ESP32 isolated: USB only, no register/instrument wiring and ATX
disconnected. Select the CP2102 port for USB provisioning. A native
confirmation dialog appears when upload is clicked. The USB button builds and
uploads bootloader, partition table and application. The OTA button builds the
current sources and transfers only the application image using Espressif's BLE
OTA profile. No flash backup or eFuse/security operation is performed.

The same BLE owner handles connection and OTA; USB and BLE maintenance are
serialized. An upload is successful only after reconnecting, checking the built
image identity, ping–pong and, for a trial image, confirming the boot. There is no manual cancel command. Closing
the browser does not cancel a firmware operation. Do not restore Arduino.

| Interface | Purpose |
| --- | --- |
| `GET /` | React interface served by ASP.NET |
| `PUT /api/atx` | Explicit ON/OFF request; ESP32 remains the state source |
| `GET /api/connection` | On-demand snapshot / diagnostics |
| `GET /api/firmware/ports` | CP2102 USB port selection via PlatformIO |
| `POST /api/firmware/usb` | Build current source and provision over USB |
| `POST /api/firmware/ota` | Build current source and update over BLE |
| `WS /ws` | Push state; commands `connect`, `disconnect`, `ping` |

USB request: `{"isolatedHardwareConfirmed":true,"port":"/dev/cu.usbserial-0001"}`.
OTA request: `{"isolatedHardwareConfirmed":true}`. HTTP 202 means started;
observe `firmware.stage` over WebSocket for completion/failure. Uploads are not
retried automatically.

## Application structure

| File | Responsibility |
| --- | --- |
| `backend/Program.cs` | Start ASP.NET, configure HTTP/WebSockets and register services |
| `backend/Controllers/ConnectionController.cs` | Connection snapshot endpoint |
| `backend/Controllers/FirmwareController.cs` | USB port and firmware maintenance endpoints |
| `backend/Controllers/WebSocketController.cs` | Browser WebSocket connections, commands and snapshots |
| `backend/Services/BleConnectionService.cs` | Background discovery, single BLE session, explicit connect and manual ping |
| `backend/Services/AtxService.cs` | ATX commands and maintenance preparation |
| `backend/Controllers/AtxController.cs` | Validated explicit ATX requests |
| `backend/Services/FirmwareService.cs` | Exclusive build, USB and OTA maintenance |
| `backend/Services/BleOtaService.cs` | Sender for Espressif's official BLE OTA profile |
| `backend/Services/DeviceState.cs` | Decode typed FFF2 events and merge ordered state snapshots |
| `backend/Services/StateService.cs` | Notify connected WebSocket clients when state changes |
| `frontend/src/App.tsx` | Single React component containing the entire browser UI |
| `frontend/src/features/connection/` | WebSocket, connection state, and TypeScript types |
| `frontend/src/features/atx/useAtx.ts` | ATX HTTP mutation and switch state from Zustand |
| `frontend/src/features/firmware/` | Firmware API, React Query hooks, and TypeScript types |
| `frontend/src/styles.css` | Tailwind imports and page-level styles |
| `frontend/vite.config.ts` | React/Tailwind build and local development proxy |
| `firmware/` | ESP-IDF application and pinned PlatformIO configuration |
| `docs/FIRMWARE.md` | Protocol, dependencies, verification and historical hardware results |
| `docs/WIRING.md` | Preserved physical wiring map |

The previous Python-specific tests are preserved under `tests_legacy_python/`
as historical reference; they require the removed Python backend and do not
test the ASP.NET application. No C# test files have been added yet. Run the
frontend's offline UI tests with `npm --prefix frontend test`; they use simulated
WebSocket and HTTP responses and do not connect to physical hardware.

## Validation baseline

The previous Python backend was verified on isolated hardware: version 0.1.7,
USB upload, manual BLE ping, disconnect/reconnect and official BLE OTA. The
550160-byte OTA took 22.631 seconds; the complete operation took 27.652 seconds.
Those historical measurements do not establish the performance or hardware
behavior of the ASP.NET migration. See `docs/FIRMWARE.md` for details and limits.

ATX firmware offline test: `python3 firmware/tests/test_atx_power.py` (requires a C++ compiler).
See [ATX validation](docs/ATX-VALIDATION.md) for the two physical OTA runs and test limits.

FFF2 decoder offline check: `python3 backend/checks/test_device_state.py`.
Latest subscription validation: [BLE protocol validation](docs/BLE-PROTOCOL-VALIDATION.md).
