namespace Surrklank.Features.Connection.DTOs;

public sealed record ConnectionEventDto(DateTimeOffset At, string State, string? Error, int Session);
