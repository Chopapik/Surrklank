using ElectromechanicalMidi.DTOs;
using ElectromechanicalMidi.Services;
using Microsoft.AspNetCore.Mvc;

namespace ElectromechanicalMidi.Controllers;

[ApiController]
public sealed class ConnectionController(BleConnectionService connection, FirmwareService firmware) : ControllerBase
{
    [HttpGet("/api/connection")]
    public ActionResult<ApplicationDto> Get() =>
        Ok(new ApplicationDto(connection.Snapshot(), firmware.Snapshot()));

    [HttpGet("/api/connection/events")]

    public IActionResult GetEvents(int? limit) =>
        Ok(new
        {
            events = limit == null
                ? null
                : connection.Snapshot().Events.TakeLast(limit.Value),

        });
}
