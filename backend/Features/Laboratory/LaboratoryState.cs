using System.Buffers.Binary;
using System.Text.Json;
using Surrklank.Features.Application;
using Surrklank.Features.Laboratory.DTOs;

namespace Surrklank.Features.Laboratory;

public sealed class LaboratoryState(StateService updates)
{
    private readonly object _sync = new();
    private LaboratoryDeviceDto[] _devices = Enumerable.Range(1, 8).Select(id => new LaboratoryDeviceDto("fdd", id)).ToArray();
    private readonly uint?[] _status = new uint?[8];
    private readonly uint?[] _parameters = new uint?[8];
    private bool _available, _supported, _preparing, _uncertain, _needsRefresh;
    public static bool IsActive(string value) => value is not ("unknown" or "parked" or "error" or "stopped");
    public bool HasActivity { get { lock (_sync) return _preparing || _uncertain || _devices.Any(d => IsActive(d.State)); } }
    public void SetPreparing(bool value) { lock (_sync) _preparing = value; updates.Publish(); }
    public void MarkUncertain() { lock (_sync) { _uncertain = true; _available = false; NeedsRefresh = true; } updates.Publish(); }
    public bool NeedsRefresh { get { lock (_sync) return _needsRefresh; } private set => _needsRefresh = value; }
    public LaboratoryMessageDto Snapshot()
    {
        lock (_sync) return new(_available ? _devices.ToArray() : _devices.Select(d => d with { State = "unknown", Track0 = null, PositionEstimate = null }).ToArray(), _available, _supported);
    }
    public void Reset(bool supported = false)
    {
        lock (_sync)
        {
            _uncertain |= _preparing || _devices.Any(d => IsActive(d.State));
            _available = false; _supported = supported; NeedsRefresh = false;
            Array.Clear(_status); Array.Clear(_parameters);
            _devices = Enumerable.Range(1, 8).Select(id => new LaboratoryDeviceDto("fdd", id)).ToArray();
        }
        updates.Publish();
    }
    public void SetAvailable() { lock (_sync) _available = true; updates.Publish(); }
    private static bool Accept(uint next, uint? previous) => !previous.HasValue || unchecked((int)(next - previous.Value)) >= 0;
    public void Read(JsonElement json)
    {
        int index = json.GetProperty("device").GetInt32() - 1;
        if (index is < 0 or > 7) throw new InvalidOperationException("Invalid laboratory device snapshot");
        uint sequence = json.GetProperty("sequence").GetUInt32();
        lock (_sync)
        {
            var next = JsonSerializer.Deserialize<LaboratoryDeviceDto>(json.GetRawText(), StateService.JsonOptions)!;
            var old = _devices[index];
            if (Accept(sequence, _status[index]))
            {
                old = old with { Sequence = sequence, Batch = next.Batch, State = next.State, ElapsedMs = next.ElapsedMs,
                    Track0 = next.Track0, LeftTrack0 = next.LeftTrack0, TowardZero = next.TowardZero,
                    StepsIssued = next.StepsIssued, ErrorCode = next.ErrorCode, Message = ErrorMessage(next.ErrorCode) };
                _status[index] = sequence;
            }
            if (Accept(sequence, _parameters[index]))
            {
                old = old with { FrequencyHz = next.FrequencyHz, DurationMs = next.DurationMs, ReturnSteps = next.ReturnSteps, PositionEstimate = next.PositionEstimate >= 0 ? next.PositionEstimate : null };
                _parameters[index] = sequence;
            }
            _devices[index] = old;
        }
        updates.Publish();
    }
    public void Refreshed() { lock (_sync) { NeedsRefresh = false; _uncertain = false; } }
    public bool Receive(byte[] bytes)
    {
        if (bytes.Length != 20 || bytes[0] != 1 || bytes[1] is not (3 or 4) || bytes[6] is < 1 or > 8) return false;
        int index = bytes[6] - 1;
        uint sequence = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(2));
        lock (_sync)
        {
            if (!_supported) return false;
            var sequences = bytes[1] == 3 ? _status : _parameters;
            if (!Accept(sequence, sequences[index])) return false;
            if (sequences[index].HasValue && unchecked(sequence - sequences[index]!.Value) > 1) NeedsRefresh = true;
            var state = _devices[index];
            if (bytes[1] == 3)
            {
                if (bytes[7] > 10 || bytes[12] > 7) return false;
                string[] names = ["unknown", "staged", "homing", "checking_out", "checking_return", "ready", "playing", "parking", "parked", "error", "stopped"];
                if (bytes[7] >= names.Length) return false;
                int flags = bytes[13];
                state = state with { Sequence = sequence, State = names[bytes[7]], Batch = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(8)),
                    ErrorCode = bytes[12], Message = ErrorMessage(bytes[12]), Track0 = (flags & 1) == 0 ? null : (flags & 2) != 0,
                    LeftTrack0 = (flags & 4) != 0, TowardZero = (flags & 8) != 0,
                    StepsIssued = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(14)), ElapsedMs = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(16)) };
            }
            else
            {
                int position = BinaryPrimitives.ReadInt16LittleEndian(bytes.AsSpan(17));
                state = state with { FrequencyHz = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(7)) / 1000.0,
                    DurationMs = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(11)), ReturnSteps = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(15)), PositionEstimate = position >= 0 ? position : null };
            }
            sequences[index] = sequence; _devices[index] = state;
        }
        updates.Publish(); return true;
    }
    public static string? ErrorMessage(int code) => code switch
    {
        0 => null, 1 => "TRACK0 not confirmed; check drive, power and wiring", 2 => "TRACK0 did not release",
        3 => "TRACK0 return limit exceeded", 4 => "Step scheduling deadline missed", 5 => "Batch aborted",
        6 => "Power request off; position unknown", _ => "Preparation lease expired"
    };
}
