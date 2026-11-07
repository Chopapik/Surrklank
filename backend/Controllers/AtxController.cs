using Microsoft.AspNetCore.Mvc;
using Surrklank.Services;

namespace Surrklank.Controllers;

public sealed record AtxRequest(string State);

[ApiController]
[Route("api/atx")]
public sealed class AtxController(AtxService atx) : ControllerBase
{
    [HttpPut]
    public async Task<IActionResult> Set(AtxRequest request, CancellationToken cancellation)
    {
        if (Request.Headers.TryGetValue("Origin", out var origin) &&
            (origin.Count != 1 || origin[0] != $"{Request.Scheme}://{Request.Host}"))
            return StatusCode(403, new { detail = "Local origin required" });
        if (request.State is not ("on" or "off"))
            return BadRequest(new { detail = "State must be on or off" });
        try
        {
            await atx.SetAsync(request.State == "on", cancellation);
            return Ok(new { requested_state = request.State });
        }
        catch (InvalidOperationException ex) { return Conflict(new { detail = ex.Message }); }
    }
}
