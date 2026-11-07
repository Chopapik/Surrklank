using Surrklank.Features.Firmware.DTOs;

namespace Surrklank.Features.Firmware.Toolchain;

public interface IFirmwareToolchain
{
    Task<IReadOnlyList<SerialPortDto>> ListPortsAsync(CancellationToken cancellationToken);
    Task<FirmwareBuild> BuildAsync(string logPath, Action<string> reportOutput, CancellationToken cancellationToken);
    Task UploadUsbAsync(string port, string logPath, Action<string> reportOutput, CancellationToken cancellationToken);
}
