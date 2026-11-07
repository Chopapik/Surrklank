using System.Text.Json;

namespace Surrklank.Services;

// ATX commands share the BLE gate with firmware maintenance; state arrives through FFF2.
public sealed class AtxService(BleConnectionService connection)
{
    public async Task SetAsync(bool on, CancellationToken cancellation)
    {
        if (!await connection.Gate.WaitAsync(TimeSpan.FromSeconds(2), cancellation))
            throw new InvalidOperationException("Device is busy");
        try
        {
            if (connection.Snapshot().AtxOn is null)
                throw new InvalidOperationException("ATX state is unavailable; connect compatible firmware first");
            string command = on ? "ATX ON" : "ATX OFF";
            var reply = await connection.SendCommandAsync(command, cancellation);
            // Read-after-command is needed only for the one-time upgrade from old firmware.
            if (!connection.Snapshot().Subscribed)
                connection.SetDevice(await connection.ReadInfoAsync(cancellation));
            if (reply != command) throw new InvalidOperationException(reply);
        }
        finally { connection.Gate.Release(); }
    }

    // Caller holds the BLE gate. Older firmware has no ATX control; isolation confirmation
    // remains mandatory for its first update. Never send an unsupported command to it.
    public async Task PrepareWhileLockedAsync(CancellationToken cancellation)
    {
        var snapshot = connection.Snapshot();
        if (!snapshot.Connected || snapshot.AtxOn is null) return;
        if (await connection.SendCommandAsync("ATX PREPARE", cancellation) != "ATX OFF")
            throw new InvalidOperationException("ESP32 did not accept ATX maintenance lock");
        var info = await connection.ReadInfoAsync(cancellation);
        connection.SetDevice(info);
        if (!info.TryGetProperty("atx_on", out var on) || on.ValueKind != JsonValueKind.False)
            throw new InvalidOperationException("ESP32 did not confirm ATX OFF");
    }

}
