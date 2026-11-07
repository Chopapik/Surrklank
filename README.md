# Surrklank

Surrklank is a local application for an ESP32 device. ASP.NET Core serves the
React interface and communicates with the ESP32 over BLE. The firmware currently
supports connection, ATX control and USB/BLE firmware maintenance; instrument
playback is not implemented.

## Run

Install the .NET 10 SDK, Node.js 24 or newer, npm and PlatformIO Core. Build the
frontend before starting ASP.NET:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python3 run.py
```

On Windows, use `py run.py`. Open <http://127.0.0.1:5173>. `run.py` launches the
C# application; ASP.NET serves `frontend/dist` in the same process. Rider can
also run `backend/Surrklank.csproj` directly. Rebuild the frontend when serving
changed UI files through ASP.NET.

For frontend development, keep ASP.NET running, start
`npm --prefix frontend run dev`, and open <http://127.0.0.1:5174>. Vite forwards
`/api` and `/ws` to ASP.NET. `frontend/dist` and `node_modules` are generated.

The backend uses SimpleSharpBLE 1.2.0. Its packaged native libraries support
Apple Silicon macOS, Windows x64/ARM64 and Linux x64/ARM64, but not Intel macOS.
macOS needs Bluetooth permission for the application or terminal running the
server; Linux needs BlueZ and D-Bus. Check the library's Business Source License
1.1 before commercial use. The first .NET restore needs NuGet access.

## Use the device

The ESP32 advertises the compatibility name `EM-MIDI-IDF`. The application scans
and connects automatically, including after link loss. **Disconnect** pauses
automatic connection until **Connect** is selected. **Ping** is manual; there is
no heartbeat. Browser connection and firmware status arrive over `/ws`.

The ATX switch requests an explicit ON or OFF state. GPIO19 drives the transistor
and the physical GPIO13 button can also change the request. The displayed state
comes from the ESP32's driven output, not from browser storage or a measured
power rail. An unknown state disables the switch. See [wiring](docs/WIRING.md).

## Firmware maintenance

Isolate the ESP32 before an upload: USB only, with ATX and register/instrument
wiring disconnected. The interface asks for this confirmation. USB provisioning
requires selecting the connected CP2102 port; BLE OTA transfers only the
application image. The application builds from the current `firmware/` sources.
Neither mode changes eFuses or flash security settings.

Maintenance blocks conflicting device controls. An upload request returns HTTP
202 when the job starts; completion or failure is reported over `/ws`. A busy
device returns HTTP 409 with a reason. If the flash outcome cannot be confirmed,
the job is `uncertain` and does not resend the image automatically. Closing the
browser does not cancel an upload. See [firmware operation](docs/FIRMWARE.md).

## Interfaces and checks

| Interface | Purpose |
| --- | --- |
| `GET /` | React interface |
| `GET /api/connection` | Current connection and firmware snapshot |
| `GET /api/connection/events?limit=10` | Recent connection events |
| `PUT /api/atx` | Explicit `{"state":"on"}` or `{"state":"off"}` request |
| `GET /api/firmware/ports` | Available CP2102 ports |
| `POST /api/firmware/usb`, `POST /api/firmware/ota` | Start a firmware job |
| `WS /ws` | State snapshots and `connect`, `disconnect`, `ping` actions |

Firmware requests require `{"isolatedHardwareConfirmed":true}`; USB also needs
`"port":"<selected CP2102 port>"`. Local-origin checks apply to mutating HTTP
requests and browser WebSockets. See [application architecture](docs/ARCHITECTURE.md)
and [BLE application protocol](docs/BLE-PROTOCOL.md) for the state flow.

Offline checks:

```sh
dotnet build backend/Surrklank.csproj
npm --prefix frontend run build
npm --prefix frontend test
python3 backend/checks/test_device_state.py
python3 firmware/tests/test_atx_power.py
pio run -d firmware -e esp32
```

The backend check compiles the production state decoder in a temporary .NET
harness; the ATX check compiles the production C++ module with GPIO/FreeRTOS
stubs. These checks and builds do not exercise a physical ESP32. No C# test
suite for the orchestration layer is included.
