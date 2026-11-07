using Surrklank.Services;
using Microsoft.AspNetCore.Mvc;

namespace Surrklank.Controllers;

[ApiController]
[Route("api/firmware")]
public sealed class FirmwareController(FirmwareService firmware) : ControllerBase
{
    private bool LocalOrigin() => !Request.Headers.TryGetValue("Origin", out var origin) ||
        origin.Count == 1 && origin[0] == $"{Request.Scheme}://{Request.Host}";

    [HttpGet("ports")]
    public async Task<IActionResult> Ports(CancellationToken cancellation)
    {
        try { return Ok(await firmware.PortsAsync(cancellation)); }
        catch (Exception ex) { return StatusCode(503, new { detail = ex.Message }); }
    }

    [HttpPost("usb")]
    public Task<IActionResult> Usb([FromBody] FirmwareRequest request, CancellationToken cancellation) => Start("usb", request, cancellation);

    [HttpPost("ota")]
    public Task<IActionResult> Ota([FromBody] FirmwareRequest request, CancellationToken cancellation) => Start("ble", request, cancellation);

    private async Task<IActionResult> Start(string transport, FirmwareRequest request, CancellationToken cancellation)
    {
        if (!LocalOrigin()) return StatusCode(403, new { detail = "Local origin required" });
        try
        {
            await firmware.StartAsync(transport, request, cancellation);
            return StatusCode(202, firmware.Snapshot());
        }
        catch (ArgumentException ex) { return BadRequest(new { detail = ex.Message }); }
        catch (InvalidOperationException ex) { return BadRequest(new { detail = ex.Message }); }
    }
}
