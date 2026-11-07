using Microsoft.AspNetCore.Mvc;
using Surrklank.Features.Connection;
using Surrklank.Features.Laboratory.DTOs;
using Surrklank.Shared.Http;

namespace Surrklank.Features.Laboratory;

[ApiController]
[Route("api/laboratory")]
public sealed class LaboratoryController(LaboratoryService laboratory) : ControllerBase
{
    [HttpPost("play")]
    public async Task<IActionResult> PlayAsync(LaboratoryPlayRequestDto request, CancellationToken cancellationToken)
    {
        if (!LocalOrigin.IsAllowed(Request)) return StatusCode(403, new { message = "Local origin required" });
        try { return StatusCode(202, new { batch = await laboratory.PlayAsync(request, cancellationToken), message = "Batch start accepted" }); }
        catch (ArgumentException ex) { return BadRequest(new { message = ex.Message }); }
        catch (DeviceBusyException ex) { return Conflict(new { message = ex.Message, operation = ex.Operation }); }
        catch (InvalidOperationException ex) { return Conflict(new { message = ex.Message }); }
        catch (Exception ex) when (ex is not OperationCanceledException) { return StatusCode(503, new { message = "Laboratory outcome unknown: " + ex.Message }); }
    }
    [HttpPost("stop")]
    public Task<IActionResult> StopAsync(LaboratoryStopRequestDto request, CancellationToken cancellationToken) => StopCoreAsync(request, cancellationToken);
    [HttpPost("stop/all")]
    public Task<IActionResult> StopAllAsync(CancellationToken cancellationToken) => StopCoreAsync(null, cancellationToken);
    private async Task<IActionResult> StopCoreAsync(LaboratoryStopRequestDto? request, CancellationToken token)
    {
        if (!LocalOrigin.IsAllowed(Request)) return StatusCode(403, new { message = "Local origin required" });
        try { await laboratory.StopAsync(request, token); return StatusCode(202, new { message = "Stop accepted; observe parking state" }); }
        catch (ArgumentException ex) { return BadRequest(new { message = ex.Message }); }
        catch (DeviceBusyException ex) { return Conflict(new { message = ex.Message, operation = ex.Operation }); }
        catch (InvalidOperationException ex) { return Conflict(new { message = ex.Message }); }
        catch (Exception ex) when (ex is not OperationCanceledException) { return StatusCode(503, new { message = "Stop not confirmed: " + ex.Message }); }
    }
}
