using System.Text.Json;

namespace Surrklank.DTOs;

public sealed record ConnectionDto(
    string State,
    string? Error,
    int Session,
    PingResult? LastPing,
    JsonElement? Device,
    IReadOnlyList<ConnectionEvent> Events,
    int? Mtu,
    string Discovery)
{
    public bool Connected => State == "connected";
}

public sealed record PingResult(bool Ok, double? RttMs = null,
    DateTimeOffset? At = null, string? Reply = null, string? Error = null);

public sealed record ConnectionEvent(DateTimeOffset At, string State, string? Error, int Session);
