# FFF1/FFF2 subscription validation — 2026-11-07

## Change and observed failure

The ATX background read loop was removed. FFF1 handles commands and INFO
snapshots; FFF2 publishes ATX and flash state with boot-scoped sequence numbers.
Manual upload cancellation was removed from the browser and WebSocket command
API. The official Espressif OTA transfer protocol was retained.

The first development trial added FFF2 Notify and attempted to read that same
characteristic after subscribing. Transfer/flash verification completed, but
reconnect did not finish. HTTP remained available and reported `connecting`,
`subscribed: true`, and firmware stage `reconnecting`. Rider attached to the
running process; a worker stack was suspended in
`SimpleSharpBLE.Peripheral.ReadCore.lambda`. Local managed values were unavailable
at the native instruction pointer, limiting direct inspection inside the call.

The native macOS [SimpleBLE read implementation](https://github.com/simpleble/simpleble/blob/main/simpleble/src/backends/macos/PeripheralBaseMacOS.mm)
waits for the next event if the characteristic is notifying. With no new ATX or
flash transition, the read can wait indefinitely. The development image was not
confirmed. The next backend connection observed the prior confirmed identity
`121cd484162b032a810d7eb9cf8ba54cbea64b9b0b00c90b1b6ac667dd9b9c92`.
This is evidence for the failure in this trial, not a proof of every prior
reverted connection issue.

The fix uses INFO over FFF1 after subscribing. It retains a read of FFF2 before
subscription for compatibility/capability detection. Sequence merging closes
the initial-read/subscription race without another read of subscribed FFF2.

## Successful physical checks

| Check | Result |
| --- | --- |
| Migration OTA from confirmed legacy firmware | 26.178 s transfer/flash, 29.677 s after build; trial confirmed |
| Subsequent OTA with FFF2 already subscribed | 24.726 s transfer/flash, 28.394 s after build; trial confirmed |
| Final OTA after correcting the committed-byte counter | 23.510 s transfer/flash, 26.951 s after build; trial confirmed |
| FFF2 flash events during subsequent OTA | writing at 0, then committed blocks 65536 through 524288 bytes, ready at 558848 bytes |
| Browser WebSocket during subsequent OTA | Same connection, 163 snapshots; no reconnect |
| Two BLE disconnect/reconnect cycles | Same observer WebSocket; unknown ATX while disconnected; OFF restored; ping 65.9/75.9 ms |
| Final running image | `3e2277046eb616db832703b4ef01afdfe2f8a3e2ca11cdcf3f3614a0e7e05111`, trial false |

The final run again delivered writing/ready through FFF2 with a continuous
WebSocket; ready reported 558864 bytes. The committed-byte counter now advances
only after successful flash writes, including when reporting failures.

The initial migration retained bounded legacy flash-ready reads because the old
image cannot notify. The subscribed OTA used state-change waits. Initial and
verification snapshots are explicit INFO requests, not a periodic ATX poll.

## Offline checks and limitations

ASP.NET and React production builds passed. Nine frontend tests passed,
including server readiness independent of BLE, state updates from WebSocket and
absence of a manual cancel control. The real ATX C++ module passed its GPIO/
FreeRTOS-stub test, including callback sequence and unchanged-state checks.
The production C# decoder passed a temporary offline harness covering malformed
frames, stale/duplicate events, late snapshot merging, sequence wrap and reset.
No C# test source files were added to the repository.

Physical ATX ON/button, USB provisioning, abrupt power loss and long-duration
endurance were not tested. BLE notifications have no application-level delivery
acknowledgment; this revision does not promise lossless intermediate events.

See [2026-11-07-fff2.json](validation/2026-11-07-fff2.json) for image hash,
measurements and observed flash-state progression. Previous polling-implementation
measurements remain historical in [ATX validation](ATX-VALIDATION.md).
