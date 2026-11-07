using Microsoft.AspNetCore.Mvc;
using Surrklank.Features.Atx.DTOs;
using Surrklank.Features.Connection;
using Surrklank.Shared.Http;

namespace Surrklank.Features.Atx;

[ApiController]
[Route("api/atx")]
public sealed class AtxController(AtxService atx) : ControllerBase
{
    [HttpPut]
    public async Task<IActionResult> SetAsync(AtxRequestDto request, CancellationToken cancellation)
    {
        if (!LocalOrigin.IsAllowed(Request))
            return StatusCode(403, new
            {
                detail = "Local origin required"
            });
        if (request.State is not ("on" or "off"))
            return BadRequest(new
            {
                detail = "State must be on or off"
            });
        try
        {
            await atx.SetAsync(request.State == "on", cancellation);
            return Ok(new
            {
                requested_state = request.State
            });
        }
        catch (DeviceBusyException ex) { return Conflict(new { detail = ex.Message, operation = ex.Operation }); }
        catch (InvalidOperationException ex) { return Conflict(new { detail = ex.Message }); }
    }
}
