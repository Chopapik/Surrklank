using Surrklank.Features.Connection;
using Surrklank.Features.Laboratory.DTOs;

namespace Surrklank.Features.Laboratory;

public sealed class LaboratoryService(IDeviceConnection connection, LaboratoryState state, PlayLaboratoryBatchUseCase play)
{
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
