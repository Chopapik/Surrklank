using Surrklank.Features.Connection;
using Surrklank.Features.Laboratory;

namespace Surrklank.Features.Drives;

// The select line of each FDD lives in ESP32 NVS; the backend only sends FDD SELECT.
public sealed class DrivesService(IDeviceConnection connection, LaboratoryState laboratory)
{
    public static readonly string[] Lines = ["DS0", "DS1", "DS2"];

    public async Task SetSelectAsync(int device, string line, CancellationToken cancellation)
    {
        using var operation = await connection.ReserveAsync("drive_select", cancellation);
        if (laboratory.HasActivity)
            throw new DeviceBusyException("laboratory");
        var lines = connection.Snapshot().SelectLines;
        if (lines is null)
            throw new InvalidOperationException("Select lines are unavailable; connect compatible firmware first");
        // The firmware reports one select line per drive it drives.
        if (device > lines.Count)
            throw new InvalidOperationException($"The connected firmware drives FDD 1-{lines.Count}");
        string command = $"FDD SELECT {device} {line}";
        var reply = await operation.SendCommandAsync(command, cancellation);
        connection.SetDevice(await operation.ReadInfoAsync(cancellation));
        if (reply == "ERR FDD BUSY")
            throw new DeviceBusyException("laboratory");
        if (reply != command)
            throw new InvalidOperationException(reply == "ERR FDD STORAGE"
                ? "ESP32 could not store the select line" : reply);
    }
}
