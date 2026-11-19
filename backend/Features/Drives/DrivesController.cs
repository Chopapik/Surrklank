using Microsoft.AspNetCore.Mvc;
using Surrklank.Features.Connection;
using Surrklank.Features.Drives.DTOs;
using Surrklank.Shared.Http;

namespace Surrklank.Features.Drives;

[ApiController]
[Route("api/drives")]
public sealed class DrivesController(DrivesService drives) : ControllerBase
{
    [HttpPut("select")]
    public async Task<IActionResult> SetSelectAsync(DriveSelectRequestDto request, CancellationToken cancellation)
    {
        if (!LocalOrigin.IsAllowed(Request)) return StatusCode(403, new { message = "Local origin required" });
        if (request.Device is < 1 or > 8 || !DrivesService.Lines.Contains(request.Line))
            return BadRequest(new { message = "Device must be 1-8 and line DS0, DS1 or DS2" });
        try
        {
            await drives.SetSelectAsync(request.Device, request.Line, cancellation);
            return Ok(new { device = request.Device, line = request.Line });
        }
        catch (DeviceBusyException ex) { return Conflict(new { message = ex.Message, operation = ex.Operation }); }
        catch (InvalidOperationException ex) { return Conflict(new { message = ex.Message }); }
    }
}
