using Microsoft.AspNetCore.Mvc;
using Surrklank.Features.Connection;
using Surrklank.Features.Diagnostics.DTOs;
using Surrklank.Shared.Http;

namespace Surrklank.Features.Diagnostics;

[ApiController]
public sealed class DiagnosticsController(DiagnosticsService diagnostics) : ControllerBase
{
    [HttpPost("/api/bus-test")]
    public async Task<IActionResult> SetBusTestAsync(BusTestRequestDto request, CancellationToken cancellation)
    {
        if (!LocalOrigin.IsAllowed(Request)) return StatusCode(403, new { message = "Local origin required" });
        try
        {
            await diagnostics.SetBusTestAsync(request.Enabled, cancellation);
            return Ok(new { enabled = request.Enabled });
        }
        catch (DeviceBusyException ex) { return Conflict(new { message = ex.Message, operation = ex.Operation }); }
        catch (InvalidOperationException ex) { return Conflict(new { message = ex.Message }); }
    }
}
