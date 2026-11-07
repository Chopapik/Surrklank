namespace Surrklank.Features.Connection.DTOs;

public sealed record PingResultDto(bool Ok, double? RttMs = null,
    DateTimeOffset? At = null, string? Reply = null, string? Error = null);
