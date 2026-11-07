using Surrklank.Features.Application.DTOs;
using Surrklank.Features.Connection;
using Surrklank.Features.Firmware;

namespace Surrklank.Features.Application;

public sealed class ApplicationStateService(IDeviceConnection connection, FirmwareService firmware)
{
    public ApplicationDto Snapshot() => new(connection.Snapshot(), firmware.Snapshot());

    public StateMessageDto Message() => new(connection.Snapshot(), firmware.Snapshot());
}
