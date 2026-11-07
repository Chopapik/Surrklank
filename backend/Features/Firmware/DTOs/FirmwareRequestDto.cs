using System.Text.Json.Serialization;

namespace Surrklank.Features.Firmware.DTOs;

public sealed record FirmwareRequestDto(
    [property: JsonPropertyName("isolatedHardwareConfirmed")] bool IsolatedHardwareConfirmed,
    [property: JsonPropertyName("port")] string? Port);
