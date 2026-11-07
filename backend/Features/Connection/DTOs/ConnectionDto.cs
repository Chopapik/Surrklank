using System.Text.Json;
using Surrklank.Features.Firmware.DTOs;

namespace Surrklank.Features.Connection.DTOs;

public sealed record ConnectionDto(
    string State,
    string? Error,
    int Session,
    PingResultDto? LastPing,
    JsonElement? Device,
    IReadOnlyList<ConnectionEventDto> Events,
    int? Mtu,
    string Discovery,
    bool? AtxOn = null,
    DeviceFirmwareDto? DeviceFirmware = null,
    bool Subscribed = false,
    string? Operation = null)
{
    public bool Connected => State == "connected";
}
