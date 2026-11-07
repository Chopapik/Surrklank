namespace Surrklank.Features.Firmware.DTOs;

public sealed record DeviceFirmwareDto(string Stage, uint Received, int Error);
