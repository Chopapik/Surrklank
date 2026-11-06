namespace ElectromechanicalMidi.DTOs;

public sealed record ApplicationDto(ConnectionDto Connection, FirmwareDto Firmware);

public sealed record StateMessage(ConnectionDto Connection, FirmwareDto Firmware)
{
    public string Type => "state";
}
