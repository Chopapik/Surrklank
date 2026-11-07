using Surrklank.Features.Connection.DTOs;
using Surrklank.Features.Firmware.DTOs;

namespace Surrklank.Features.Application.DTOs;

public sealed record StateMessageDto(ConnectionDto Connection, FirmwareDto Firmware)
{
    public string Type => "state";
}
