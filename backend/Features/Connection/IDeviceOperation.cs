using System.Text.Json;
using Surrklank.Features.Firmware.Transport;

namespace Surrklank.Features.Connection;

// A reservation is transferred to the firmware job, so HTTP 202 never releases maintenance.
// It exposes serialized device operations without exposing the native peripheral or semaphore.
public interface IDeviceOperation : IDisposable
{
    string Reason { get; }
    Task ConnectAsync(CancellationToken token = default);
    Task DisconnectAsync();
    Task PingAsync(CancellationToken token = default);
    Task<string> SendCommandAsync(string command, CancellationToken token = default);
    Task<JsonElement> ReadInfoAsync(CancellationToken token = default);
    Task WaitForFlashReadyAsync(CancellationToken token);
    Task TransferAsync(BleOtaService ota, byte[] image, Action<double, object> progress, CancellationToken token);
}
