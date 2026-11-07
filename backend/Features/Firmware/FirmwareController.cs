using Microsoft.AspNetCore.Mvc;
using Surrklank.Features.Connection;
using Surrklank.Features.Firmware.DTOs;
using Surrklank.Shared.Http;

namespace Surrklank.Features.Firmware;

[ApiController]
[Route("api/firmware")]
public sealed class FirmwareController(FirmwareService firmware) : ControllerBase
{
    [HttpGet("ports")]
    public async Task<IActionResult> PortsAsync(CancellationToken cancellation)
    {
        try
        {
            return Ok(await firmware.PortsAsync(cancellation));
        }
        catch (Exception ex) { return StatusCode(503, new { detail = ex.Message }); }
    }

    [HttpPost("usb")]
    public Task<IActionResult> UsbAsync([FromBody] FirmwareRequestDto request, CancellationToken cancellation) => StartAsync("usb", request, cancellation);

    [HttpPost("ota")]
    public Task<IActionResult> OtaAsync([FromBody] FirmwareRequestDto request, CancellationToken cancellation) => StartAsync("ble", request, cancellation);

    private async Task<IActionResult> StartAsync(string transport, FirmwareRequestDto request, CancellationToken cancellation)
    {
        if (!LocalOrigin.IsAllowed(Request))
            return StatusCode(403, new
            {
                detail = "Local origin required"
            });
        try
        {
            await firmware.StartAsync(transport, request, cancellation);
            return StatusCode(202, firmware.Snapshot());
        }
        catch (DeviceBusyException ex) { return Conflict(new { detail = ex.Message, operation = ex.Operation }); }
        catch (ArgumentException ex) { return BadRequest(new { detail = ex.Message }); }
        catch (InvalidOperationException ex) { return BadRequest(new { detail = ex.Message }); }
    }
}
