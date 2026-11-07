using Surrklank.Features.Laboratory;
using System.Text.Json;
using Surrklank.Features.Connection;

namespace Surrklank.Features.Atx;

// ATX commands share the BLE gate with firmware maintenance; state arrives through FFF2.
public sealed class AtxService(IDeviceConnection connection, LaboratoryState laboratory)
{
    public async Task SetAsync(bool on, CancellationToken cancellation)
    {
        using var operation = await connection.ReserveAsync("atx", cancellation);
        if (!on && laboratory.HasActivity)
            throw new DeviceBusyException("laboratory");
        if (connection.Snapshot().AtxOn is null)
            throw new InvalidOperationException("ATX state is unavailable; connect compatible firmware first");
        string command = on ? "ATX ON" : "ATX OFF";
        var reply = await operation.SendCommandAsync(command, cancellation);
        // A one-shot read reconciles a missed command-result event without periodic polling.
        connection.SetDevice(await operation.ReadInfoAsync(cancellation));
        if (reply != command)
            throw new InvalidOperationException(reply);
    }

    // Caller holds the BLE gate. Older firmware has no ATX control; isolation confirmation
    // remains mandatory for its first update. Never send an unsupported command to it.
    public async Task PrepareWhileLockedAsync(IDeviceOperation operation, CancellationToken cancellation)
    {
        if (laboratory.HasActivity)
            throw new DeviceBusyException("laboratory");
        var snapshot = connection.Snapshot();
        if (!snapshot.Connected || snapshot.AtxOn is null)
            return;
        if (await operation.SendCommandAsync("ATX PREPARE", cancellation) != "ATX OFF")
            throw new InvalidOperationException("ESP32 did not accept ATX maintenance lock");
        var info = await operation.ReadInfoAsync(cancellation);
        connection.SetDevice(info);
        if (!info.TryGetProperty("atx_on", out var on) || on.ValueKind != JsonValueKind.False)
            throw new InvalidOperationException("ESP32 did not confirm ATX OFF");
    }

}
