using System.Buffers.Binary;
using System.Text.Json;
using Surrklank.Features.Firmware.DTOs;

namespace Surrklank.Features.Connection;

// FFF2 values and events share boot-scoped sequence numbers. The BLE owner holds its lock.
public sealed class DeviceState
{
    public bool? AtxOn { get; private set; }
    public DeviceFirmwareDto? Firmware { get; private set; }
    public bool NeedsRefresh { get; private set; }
    private uint? _atxSequence;
    private uint? _firmwareSequence;

    private static bool Accept(uint sequence, uint? previous) =>
        !previous.HasValue || unchecked((int)(sequence - previous.Value)) > 0;

    public void Read(JsonElement information)
    {
        NeedsRefresh = false;
        if (information.TryGetProperty("atx_on", out var on))
        {
            uint? sequence = information.TryGetProperty("atx_sequence", out var seq) ? seq.GetUInt32() : null;
            if (!_atxSequence.HasValue || sequence.HasValue && Accept(sequence.Value, _atxSequence))
            {
                AtxOn = on.GetBoolean();
                _atxSequence = sequence;
            }
        }
        uint? next = information.TryGetProperty("firmware_sequence", out var fwSeq) ? fwSeq.GetUInt32() : null;
        if (!_firmwareSequence.HasValue || next.HasValue && Accept(next.Value, _firmwareSequence))
        {
            Firmware = new DeviceFirmwareDto(information.GetProperty("error").GetInt32() != 0 ? "failed" : information.GetProperty("ota").GetString()!,
                information.GetProperty("received").GetUInt32(), information.GetProperty("error").GetInt32());
            _firmwareSequence = next;
        }
    }

    public bool Receive(byte[] bytes)
    {
        if (bytes.Length < 6 || bytes[0] != 1)
            return false;
        uint sequence = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(2));
        switch (bytes[1])
        {
            case 1 when bytes.Length == 7 && bytes[6] <= 1 && Accept(sequence, _atxSequence):
                if (_atxSequence.HasValue && unchecked(sequence - _atxSequence.Value) > 1)
                    NeedsRefresh = true;
                AtxOn = bytes[6] == 1;
                _atxSequence = sequence;
                return true;
            case 2 when bytes.Length == 15 && bytes[6] <= 3 && Accept(sequence, _firmwareSequence):
                if (_firmwareSequence.HasValue && unchecked(sequence - _firmwareSequence.Value) > 1)
                    NeedsRefresh = true;
                string stage = bytes[6] switch
                {
                    0 => "idle",
                    1 => "writing",
                    2 => "ready",
                    _ => "failed"
                };
                Firmware = new DeviceFirmwareDto(stage,
                    BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(7)),
                    BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(11)));
                _firmwareSequence = sequence;
                return true;
            default:
                return false;
        }
    }
}
