using Surrklank.Features.Connection.DTOs;
using Surrklank.Features.Firmware.DTOs;

namespace Surrklank.Features.Application.DTOs;

public sealed record ApplicationDto(ConnectionDto Connection, FirmwareDto Firmware);
