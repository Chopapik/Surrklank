using System.Buffers.Binary;
using System.Text.Json;
using Surrklank.DTOs;

namespace Surrklank.Services;

// FFF2 values and events share boot-scoped sequence numbers. The BLE owner holds its lock.
public sealed class DeviceState
{
    public bool? AtxOn { get; private set; }
    public DeviceFirmwareDto? Firmware { get; private set; }
    private uint? atxSequence;
    private uint? firmwareSequence;

    private static bool Accept(uint sequence, uint? previous) =>
        !previous.HasValue || unchecked((int)(sequence - previous.Value)) > 0;

    public void Read(JsonElement information)
    {
        if (information.TryGetProperty("atx_on", out var on))
        {
            uint? sequence = information.TryGetProperty("atx_sequence", out var seq) ? seq.GetUInt32() : null;
            if (!atxSequence.HasValue || sequence.HasValue && Accept(sequence.Value, atxSequence))
            { AtxOn = on.GetBoolean(); atxSequence = sequence; }
        }
        uint? next = information.TryGetProperty("firmware_sequence", out var fwSeq) ? fwSeq.GetUInt32() : null;
        if (!firmwareSequence.HasValue || next.HasValue && Accept(next.Value, firmwareSequence))
        {
            Firmware = new DeviceFirmwareDto(information.GetProperty("ota").GetString()!,
                information.GetProperty("received").GetUInt32(), information.GetProperty("error").GetInt32());
            firmwareSequence = next;
        }
    }

    public bool Receive(byte[] bytes)
    {
        if (bytes.Length < 6 || bytes[0] != 1) return false;
        uint sequence = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(2));
        switch (bytes[1])
        {
            case 1 when bytes.Length == 7 && bytes[6] <= 1 && Accept(sequence, atxSequence):
                AtxOn = bytes[6] == 1; atxSequence = sequence;
                return true;
            case 2 when bytes.Length == 15 && bytes[6] <= 3 && Accept(sequence, firmwareSequence):
                string stage = bytes[6] switch { 0 => "idle", 1 => "writing", 2 => "ready", _ => "failed" };
                Firmware = new DeviceFirmwareDto(stage,
                    BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(7)),
                    BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(11)));
                firmwareSequence = sequence;
                return true;
            default: return false;
        }
    }
}
