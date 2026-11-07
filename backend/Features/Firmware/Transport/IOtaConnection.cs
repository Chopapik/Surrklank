namespace Surrklank.Features.Firmware.Transport;

// The OTA sender only needs these BLE operations; this also allows it to be
// checked offline without connecting to a physical ESP32.
public interface IOtaConnection
{
    bool IsConnected { get; }
    int ReportedMtu { get; }
    bool HasOtaFirmware { get; }
    Task SubscribeAsync(string service, string characteristic, Action<byte[]> callback, CancellationToken cancellation);
    Task UnsubscribeAsync(string service, string characteristic);
    Task WriteRequestAsync(string service, string characteristic, byte[] data, CancellationToken cancellation);
    Task WriteCommandAsync(string service, string characteristic, byte[] data, CancellationToken cancellation);
}
