using System.Text.Json;

namespace Surrklank.Services;

// All ATX commands and polling share the BLE gate with firmware maintenance.
public sealed class AtxService(BleConnectionService connection, ILogger<AtxService> logger) : BackgroundService
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

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(500));
            while (await timer.WaitForNextTickAsync(stoppingToken))
            {
                if (!await connection.Gate.WaitAsync(0, stoppingToken)) continue;
                try
                {
                    var snapshot = connection.Snapshot();
                    if (!snapshot.Connected || snapshot.AtxOn is null) continue;
                    var info = await connection.ReadInfoAsync(stoppingToken);
                    if (info.GetProperty("atx_on").GetBoolean() != snapshot.AtxOn)
                        connection.SetDevice(info);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { throw; }
                catch (Exception ex)
                {
                    logger.LogWarning(ex, "ATX state refresh failed");
                    await connection.DisconnectAsync();
                }
                finally { connection.Gate.Release(); }
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { }
    }
}
