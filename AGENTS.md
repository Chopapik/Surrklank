# Working conventions

- Conversation is Polish. Documentation, filenames and commits are English.
- Surrklank is the whole system; use `surrklank` for new technical names.
- Keep the simple black-and-white Web 1.0 interface and `docs/WIRING.md`.
- Preserve API routes, WebSocket messages, BLE UUIDs, `EM-MIDI-IDF` and other
  persistent identifiers unless a compatible migration is explicitly planned.
- Keep backend code grouped under `Features/<feature>` with thin controllers,
  feature services and focused use cases for substantive workflows. Inject
  external ports where offline substitutes are useful; do not add empty layers.
- After material behavior, architecture, protocol, firmware or integration
  changes, update the relevant shared docs in the same task. Describe current
  behavior; keep history in commits, not audit follow-ups or validation dumps.

# Read before changing

- [README.md](README.md): setup and user workflow.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): ownership, state flow and API.
- [docs/BLE-PROTOCOL.md](docs/BLE-PROTOCOL.md): FFF1/FFF2 contract and macOS read rule.
- [docs/FIRMWARE.md](docs/FIRMWARE.md): ESP-IDF, OTA, verification and safety.
  Read its FDD Laboratory section before changing motion, SELECT or timing.
- [docs/WIRING.md](docs/WIRING.md): physical connections and proposed wiring.

# Build and runtime checks

- Launch ASP.NET with `python3 run.py` (Windows: `py run.py`). It serves
  <http://127.0.0.1:5173>. Do not use Docker or the archived TCP gateway.
- After backend changes run `dotnet build backend/Surrklank.csproj`.
- After frontend changes run `npm --prefix frontend run build` and the ASP.NET
  build. Run `npm --prefix frontend test` for affected UI behavior.
- After firmware changes run `pio run -d firmware -e esp32` and applicable
  offline checks (`firmware/tests/test_atx_power.py`, `firmware/tests/test_fdd.py`).
  Builds and mocks are not physical-device validation.
- After runtime changes restart the application and check `GET /` and
  `GET /api/connection`. Use `BLE_AUTO_SCAN=false` for an offline smoke check.
- Run existing checks. The user wants to learn C# testing in Rider; do not
  generate a C# orchestration test suite without a request. State which new
  failure paths remain untested.

# Device and maintenance rules

- Use `BleConnectionService.ReserveAsync` (or its `IDeviceConnection` contract)
  for native BLE work. Keep the returned `IDeviceOperation` alive through every
  awaited call; firmware owns it beyond
  HTTP 202 until verification and cleanup. Do not expose the native peripheral
  or semaphore or issue parallel native calls through a reservation. Return
  HTTP 409 with the active operation when busy.
- Preserve the pinned official Espressif BLE connection manager and BLE OTA
  components. Firmware uses PlatformIO with ESP-IDF, never Arduino. Do not
  invent another OTA transport or change eFuses/flash security settings.
- Never connect to or flash physical hardware as an implicit offline check.
  Upload only with explicit authorization for the current task. Keep ATX OFF
  during maintenance; never power instruments during an upload.
- ATX state is the GPIO19 transistor output request, not PWR_OK or measured
  voltage. GPIO13 is the physical button. Read the protocol and wiring docs
  before changing these contracts. Do not read subscribed FFF2 through
  SimpleBLE on macOS; request `INFO` over FFF1 instead.
- Keep private legacy signing keys outside Git; never print or publish them.
- Laboratory owns the native reservation only during short exchanges, not
  throughout playing/preparation. Preserve batch preparation/COMMIT semantics,
  sensor-confirmed parking and independent STOP. Never automatically replay an
  unconfirmed COMMIT. Preserve firmware ATX ownership through final parking.
- New application-owned JSON errors use `message`; keep existing `detail` and
  ASP.NET ProblemDetails contracts compatible.

# Commits

Use a concise subject and short body explaining the change, motivation,
affected behavior, validation and material limits. Keep the history useful for
reconstructing project decisions and thesis evidence. Distinguish measurements
from observations and hypotheses; reference measurement artifacts when available
and never imply unperformed hardware testing. Each commit body must be understandable
without reading its diff.
