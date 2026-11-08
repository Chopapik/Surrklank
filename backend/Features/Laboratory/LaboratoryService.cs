using Surrklank.Features.Connection;
using Surrklank.Features.Laboratory.DTOs;

namespace Surrklank.Features.Laboratory;

public sealed class LaboratoryService(IDeviceConnection connection, LaboratoryState state, PlayLaboratoryBatchUseCase play, Surrklank.Features.Application.StateService updates)
{
    private readonly object _timingLock = new();
    private object? _timing;
    public object? TimingSnapshot() { lock (_timingLock) return _timing; }
    public async Task<object> ReadTimingAsync(uint after, CancellationToken token)
    {
        using var operation = await connection.ReserveAsync("laboratory_timing", token);
        RequireReady(connection, state);
        using var clock = ParseTimingReply(await operation.SendCommandAsync("LAB CLOCK", token));
        var clockValue = clock.RootElement.Clone();
        if (!clockValue.TryGetProperty("timing_version", out var version) || version.GetInt32() != 1)
            throw new InvalidOperationException("Firmware does not support timing v1");
        var events = new List<System.Text.Json.JsonElement>();
        uint cursor = after;
        bool gap = false;
        for (int i = 0; i < 128; i++)
        {
            using var response = ParseTimingReply(await operation.SendCommandAsync($"LAB EVENT {cursor}", token));
            var root = response.RootElement;
            if (root.GetProperty("esp_boot_id").GetUInt32() != clockValue.GetProperty("esp_boot_id").GetUInt32())
                throw new InvalidOperationException("ESP32 restarted during timing capture");
            var e = root.GetProperty("event");
            if (e.ValueKind == System.Text.Json.JsonValueKind.Null) {
                if (cursor > root.GetProperty("latest").GetUInt32()) gap = true;
                break;
            }
            uint sequence = e.GetProperty("event_sequence").GetUInt32();
            if (sequence <= cursor) throw new InvalidOperationException("Invalid event sequence");
            gap |= sequence != cursor + 1;
            events.Add(e.Clone()); cursor = sequence;
            if (cursor == root.GetProperty("latest").GetUInt32()) break;
        }
        object result = new { type = "laboratory_timing", clock = clockValue, after, next = cursor, gap, events };
        lock (_timingLock) _timing = result;
        updates.Publish();
        return result;
    }
    public async Task<System.Text.Json.JsonElement> ReadClockAsync(CancellationToken token)
    {
        using var operation = await connection.ReserveAsync("laboratory_clock", token);
        RequireReady(connection, state);
        using var response = ParseTimingReply(await operation.SendCommandAsync("LAB CLOCK", token));
        var root = response.RootElement;
        if (!root.TryGetProperty("timing_version", out var version) || version.GetInt32() != 1)
            throw new InvalidOperationException("Firmware does not support timing v1");
        return root.Clone();
    }
    private static System.Text.Json.JsonDocument ParseTimingReply(string reply)
    {
        try { return System.Text.Json.JsonDocument.Parse(reply); }
        catch (System.Text.Json.JsonException ex)
        {
            throw new InvalidOperationException("Firmware timing v1 is unavailable or returned an invalid reply", ex);
        }
    }
    public Task<uint> PlayAsync(LaboratoryPlayRequestDto request, CancellationToken cancellationToken) => play.ExecuteAsync(request, cancellationToken);
    public async Task StopAsync(LaboratoryStopRequestDto? request, CancellationToken cancellationToken)
    {
        if (request != null && (request.DeviceType != "fdd" || request.Device is < 1 or > 8))
            throw new ArgumentException("Select an FDD numbered 1 through 8");
        using var operation = await connection.ReserveAsync("laboratory_stop", cancellationToken);
        RequireReady(connection, state);
        try
        {
            await SendAsync(operation, request == null ? "LAB STOPALL" : $"LAB STOP {request.Device}", cancellationToken);
            await operation.RefreshLaboratoryAsync(cancellationToken);
        }
        catch (LaboratoryCommandRejectedException) { throw; }
        catch (Exception ex)
        {
            state.MarkUncertain();
            throw new LaboratoryOutcomeUnknownException("Stop outcome is unknown; inspect live state before retrying", ex);
        }
    }
    internal static void RequireReady(IDeviceConnection connection, LaboratoryState state)
    {
        var snapshot = connection.Snapshot();
        if (!snapshot.Connected || !snapshot.Subscribed || !state.Snapshot().Supported)
            throw new InvalidOperationException("Connect firmware supporting Laboratory v1 first");
    }
    internal static async Task SendAsync(IDeviceOperation operation, string command, CancellationToken token)
    {
        var reply = await operation.SendCommandAsync(command, token);
        if (reply != "LAB OK") throw new LaboratoryCommandRejectedException(reply);
    }

}

internal sealed class LaboratoryCommandRejectedException(string message) : InvalidOperationException(message);
internal sealed class LaboratoryOutcomeUnknownException(string message, Exception inner) : Exception(message, inner);
