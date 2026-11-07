using Microsoft.AspNetCore.Mvc;
using Surrklank.Features.Application;
using Surrklank.Features.Application.DTOs;

namespace Surrklank.Features.Connection;

[ApiController]
public sealed class ConnectionController(ApplicationStateService application, BleConnectionService connection) : ControllerBase
{
    [HttpGet("/api/connection")]
    public ActionResult<ApplicationDto> Get() => Ok(application.Snapshot());

    [HttpGet("/api/connection/events")]
    public IActionResult GetEvents([FromQuery] int? limit) =>
        Ok(new
        {
            events = connection.GetEvents(limit)
        });
}
