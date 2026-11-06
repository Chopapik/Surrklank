# ESP32 BLE / ESP-IDF

This project contains a local ASP.NET Core application and minimal ESP-IDF
firmware for an isolated ESP32. The browser connects to the application over
HTTP and WebSocket; the application communicates with the ESP32 using BLE.

## Run the application

Install the .NET 10 SDK and PlatformIO Core. Run `python3 run.py` (Windows:
`py run.py`) and open <http://127.0.0.1:5173>. The Python script is only a
launcher for `dotnet run`; the backend itself is entirely C#. You can also run
`dotnet run --project backend/ElectromechanicalMidi.csproj` directly.

The application uses [SimpleSharpBLE 1.2.0](https://www.nuget.org/packages/SimpleSharpBLE/1.2.0)
for native BLE. It packages desktop libraries for Apple Silicon macOS, Windows
x64/ARM64 and Linux x64/ARM64; Intel macOS is not included. On macOS, grant
Bluetooth permission to the terminal or application launching the server. On
Linux, BlueZ and D-Bus are required. SimpleBLE uses the Business Source License
1.1, with a non-commercial production grant; check its license before commercial
use. The first .NET restore needs access to NuGet.

The application scans for EM-MIDI-IDF in the background and connects automatically.
After link loss it searches again. Explicit disconnect pauses automatic connection;
click Connect to resume. Click **Ping** for a manual check.
There is no automatic heartbeat. Scanning pauses during device operations.
Connection, ping results and firmware progress arrive over `/ws`; the page does
not poll REST for progress. Reopening WebSocket receives the current snapshot.

## Firmware upload

Keep the ESP32 isolated: USB only, no register/instrument wiring and ATX
disconnected. Select the CP2102 port for USB provisioning. A native
confirmation dialog appears when upload is clicked. The USB button builds and
uploads bootloader, partition table and application. The OTA button builds the
current sources and transfers only the application image using Espressif's BLE
OTA profile. No flash backup or eFuse/security operation is performed.

The same BLE owner handles connection and OTA; USB and BLE maintenance are
serialized. An upload is successful only after reconnecting, checking the built
image identity, ping–pong and, for a trial image, confirming the boot. Closing
the browser does not cancel a firmware operation. Do not restore Arduino.

| Interface | Purpose |
| --- | --- |
| `GET /` | Single HTML interface |
| `GET /api/connection` | On-demand snapshot / diagnostics |
| `GET /api/firmware/ports` | CP2102 USB port selection via PlatformIO |
| `POST /api/firmware/usb` | Build current source and provision over USB |
| `POST /api/firmware/ota` | Build current source and update over BLE |
| `WS /ws` | Push state; commands `connect`, `disconnect`, `ping`, `cancel` |

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
| `backend/Services/FirmwareService.cs` | Exclusive build, USB and OTA maintenance |
| `backend/Services/BleOtaService.cs` | Sender for Espressif's official BLE OTA profile |
| `backend/Services/StateService.cs` | Notify connected WebSocket clients when state changes |
| `backend/wwwroot/index.html` | Entire browser UI |
| `firmware/` | ESP-IDF application and pinned PlatformIO configuration |
| `docs/FIRMWARE.md` | Protocol, dependencies, verification and historical hardware results |
| `docs/WIRING.md` | Preserved physical wiring map |

The previous Python-specific tests are preserved under `tests_legacy_python/`
as historical reference; they require the removed Python backend and do not
test the ASP.NET application. No C# test files have been added yet.

## Validation baseline

The previous Python backend was verified on isolated hardware: version 0.1.7,
USB upload, manual BLE ping, disconnect/reconnect and official BLE OTA. The
550160-byte OTA took 22.631 seconds; the complete operation took 27.652 seconds.
Those historical measurements do not establish the performance or hardware
behavior of the ASP.NET migration. See `docs/FIRMWARE.md` for details and limits.
