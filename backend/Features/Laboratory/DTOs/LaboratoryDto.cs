namespace Surrklank.Features.Laboratory.DTOs;

public sealed record LaboratoryDeviceRequestDto(string DeviceType, int Device, double FrequencyHz, int DurationMs);
public sealed record LaboratoryPlayRequestDto(IReadOnlyList<LaboratoryDeviceRequestDto> Devices);
public sealed record LaboratoryStopRequestDto(string DeviceType, int Device);
public sealed record LaboratoryDeviceDto(
    string DeviceType, int Device, uint Sequence = 0, uint Batch = 0, string State = "unknown",
    double FrequencyHz = 0, uint DurationMs = 0, uint ElapsedMs = 0, bool? Track0 = null,
    bool LeftTrack0 = false, bool TowardZero = true, ushort StepsIssued = 0,
    ushort ReturnSteps = 0, int? PositionEstimate = null, int ErrorCode = 0, string? Message = null);
public sealed record LaboratoryMessageDto(IReadOnlyList<LaboratoryDeviceDto> Devices, bool Available, bool Supported)
{
    public string Type => "laboratory";
}
