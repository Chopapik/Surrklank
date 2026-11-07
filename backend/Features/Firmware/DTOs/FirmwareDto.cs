namespace Surrklank.Features.Firmware.DTOs;

public sealed record FirmwareDto(
    string Stage,
    double? Progress,
    string? Error,
    IReadOnlyDictionary<string, object?>? Result,
    bool Busy,
    IReadOnlyList<IReadOnlyDictionary<string, object?>> Events);
