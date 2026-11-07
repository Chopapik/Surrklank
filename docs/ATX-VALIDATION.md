# ATX implementation validation — 2026-11-07

The implementation extends the working BLE command/info service without adding
characteristics or changing UUIDs. This avoids another GATT layout migration;
it does not establish the cause of the earlier reverted connection failures.
State reporting uses a 500 ms read interval outside maintenance, trading a small
button-reporting delay for retaining the verified GATT layout.

## Results

- ASP.NET build: passed, zero warnings/errors.
- React production build: passed. Vitest: 8 tests passed, including explicit
  ON payload, no optimistic switch update, snapshots in Zustand, and disabled
  control during maintenance or BLE loss.
- ESP-IDF build: passed.
- `python3 firmware/tests/test_atx_power.py`: passed. Compiles the actual ATX
  C++ module with GPIO/FreeRTOS stubs. Checks startup OFF, idempotent ON/OFF,
  button bounce/held press, startup-held release requirement, and maintenance
  blocking both software ON and the button.
- Physical BLE OTA from the pre-ATX image: 22.051 s transfer/flash verification;
  25.886 s after build (build 2.873 s).
- Second physical OTA with ATX preparation and polling installed: 22.418 s
  transfer/flash verification; 25.919 s after build (build 4.061 s).
- Both runs completed reconnect, matching ELF identity, ping and trial
  confirmation. Each observer retained one WebSocket across the ESP32 reboot.
- Physical API checks: `toggle` rejected with 400, two explicit OFF calls
  accepted with 200, and ESP32 reported OFF.
- Two subsequent BLE disconnect/reconnect cycles preserved one WebSocket,
  reported ATX unknown while disconnected, rejected an OFF command with 409
  while disconnected, and restored OFF after reconnect. Pings: 57.6/71.1 ms.
- HTTP `GET /` and `GET /api/connection`: 200 after application restart.

Machine-readable observations and image identity are in
[2026-11-07-atx.json](validation/2026-11-07-atx.json).

## Limits

No USB upload was performed; USB was disconnected. No physical ON or button
press was performed. Those paths were exercised with host GPIO stubs and UI
mocks, not a powered ATX/instrument assembly. The physical checks kept the
output OFF. No voltage/PWR_OK sensing is implemented. Cancelled OTA recovery,
abrupt power loss and long-duration endurance were not tested here.

The maintenance lock deliberately remains OFF until ESP32 restarts. It is not
released on BLE disconnect or failed upload. Pre-ATX firmware and USB without
BLE rely on confirmed physical isolation; a disconnected device cannot be
made safe through BLE. Native SimpleBLE operations retain their existing
cancellation limits; this change does not add process termination or a bypass.
