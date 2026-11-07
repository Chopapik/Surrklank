# Commit descriptions

Every commit must have a concise, descriptive subject and a short body explaining
what changed, why, and which components or behavior are affected. Include relevant
validation results and material limitations, especially whether hardware changes
were tested only offline or in VIRTUAL rather than on physical devices.
Keep the description specific and self-contained so a person or AI can understand
the commit without reading its diff. Avoid vague summaries and exhaustive file lists.

Treat commit history as a potential source for the master's thesis documenting
the project's evolution. Preserve the motivation for changes, relevant design
decisions and tradeoffs, and observed before/after behavior when supported by
evidence. Reference relevant tests or measurement artifacts when available.
Clearly distinguish measured results from informal observations, hypotheses,
and intended improvements; never invent findings or imply unperformed validation.
Keep this context proportional to the change so the history remains useful
for reconstructing the development process without relying on chat history.

# Language and application

The official name of the complete system is Surrklank; use `surrklank` for
new technical names. Preserve existing API routes, WebSocket messages, BLE
UUIDs, the `EM-MIDI-IDF` BLE discovery name and other persistent identifiers
unless a compatible migration is explicitly planned. Historical measurements
and paths must remain identifiable as historical evidence.

Conversation is Polish. Documentation, filenames and commits are English.
Run the ASP.NET application with `python3 run.py` (Windows: `py run.py`); the script launches the C# backend.
It serves http://127.0.0.1:5173. Do not run Docker or the archived TCP gateway.
After changes restart this process and verify GET / and GET /api/connection.
BLE connection and firmware progress are published through /ws; ping is manual.

# Firmware and hardware

Firmware uses PlatformIO with ESP-IDF, never Arduino. Use pinned official Espressif
BLE connection-manager and BLE OTA components; do not invent another OTA protocol.
USB upload is permitted when requested by the user, including PlatformIO's upload
target. The application serializes USB/BLE maintenance and releases BLE before USB.
Physical USB and BLE OTA tests are explicitly authorized in this chat. The board
was confirmed isolated from registers/instruments, with ATX disconnected; never
power instruments or ATX during maintenance. No GPIO/instrument control belongs
in this minimal firmware. Do not change eFuses or flash security settings.
Never connect/flash physical hardware as an implicit offline software test.
Private legacy signing keys remain outside Git; never print or publish them.
This clean repository contains only the native application, ESP-IDF firmware,
tests and documentation. Do not restore experiments or archived upload scripts.
Keep the simple black-and-white Web 1.0 HTML interface and preserve docs/WIRING.md.

# Verified hardware baseline

On 2026-11-06, this clean repository independently passed 19 offline tests and
ESP-IDF compilation. The isolated ESP32 was provisioned through USB, verified
with manual WebSocket ping and disconnect/reconnect, then updated through the
official BLE OTA profile. Version 0.1.7 is installed and confirmed.
USB upload took 36.294 s. The 550160-byte OTA took
22.631 s (27.652 s including build/restart/verification).
The accepted transfer target is <=60 s. See docs/FIRMWARE.md for evidence and limits.
Cancelled-transfer recovery and physical trial rollback were tested in the source
project before extraction; do not report them as repeated in this migration.
