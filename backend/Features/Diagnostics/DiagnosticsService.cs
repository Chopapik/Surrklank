using Surrklank.Features.Connection;
using Surrklank.Features.Laboratory;

namespace Surrklank.Features.Diagnostics;

// Bring-up tools for the PCB modules; actuator-chain state arrives in INFO.
public sealed class DiagnosticsService(IDeviceConnection connection, LaboratoryState laboratory)
{
    public async Task SetBusTestAsync(bool enabled, CancellationToken cancellation)
    {
        using var operation = await connection.ReserveAsync("bus_test", cancellation);
        if (enabled && laboratory.HasActivity)
            throw new DeviceBusyException("laboratory");
        if (connection.Snapshot().BusTest is null)
            throw new InvalidOperationException("Bus test is unavailable; connect compatible firmware first");
        string command = enabled ? "BUS TEST ON" : "BUS TEST OFF";
        var reply = await operation.SendCommandAsync(command, cancellation);
        connection.SetDevice(await operation.ReadInfoAsync(cancellation));
        if (reply != command)
            throw new InvalidOperationException(reply == "ERR BUS BUSY"
                ? "Bus test needs ATX ON with PWR_OK and no active drive" : reply);
    }
}
