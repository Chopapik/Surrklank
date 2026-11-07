using System.Net.WebSockets;
using System.Text.Json;
using Surrklank.DTOs;
using Surrklank.Services;
using Microsoft.AspNetCore.Mvc;

namespace Surrklank.Controllers;

[ApiController]
public sealed class WebSocketController(StateService updates, BleConnectionService connection,
    FirmwareService firmware, ILogger<WebSocketController> logger) : ControllerBase
{
    [HttpGet("/ws")]
    public async Task Connect()
    {
        if (!HttpContext.WebSockets.IsWebSocketRequest) { Response.StatusCode = 400; return; }
        if (Request.Headers.TryGetValue("Origin", out var origin) &&
            (origin.Count != 1 || origin[0] != $"{Request.Scheme}://{Request.Host}"))
        { Response.StatusCode = 403; return; }
        using var socket = await HttpContext.WebSockets.AcceptWebSocketAsync();
        var listener = updates.Subscribe();
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(HttpContext.RequestAborted);
        async Task SendSnapshots()
        {
            try
            {
                await foreach (var _ in listener.Reader.ReadAllAsync(stop.Token))
                {
                    var bytes = JsonSerializer.SerializeToUtf8Bytes(new StateMessage(connection.Snapshot(), firmware.Snapshot()), StateService.JsonOptions);
                    await socket.SendAsync(bytes, WebSocketMessageType.Text, true, stop.Token);
                }
            }
            catch (OperationCanceledException) { }
            catch (WebSocketException ex) { logger.LogDebug(ex, "WebSocket sender closed"); stop.Cancel(); }
        }
        var sender = SendSnapshots();
        try
        {
            var buffer = new byte[4096];
            while (socket.State == WebSocketState.Open && !stop.IsCancellationRequested)
            {
                using var message = new MemoryStream();
                WebSocketReceiveResult result;
                do
                {
                    result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), stop.Token);
                    if (result.MessageType == WebSocketMessageType.Close) return;
                    if (result.MessageType != WebSocketMessageType.Text || message.Length + result.Count > 16384)
                        throw new InvalidOperationException("Invalid WebSocket message");
                    message.Write(buffer, 0, result.Count);
                } while (!result.EndOfMessage);
                try
                {
                    using var request = JsonDocument.Parse(message.ToArray());
                    string? action = request.RootElement.TryGetProperty("action", out var value) ? value.GetString() : null;
                    if (action == "cancel") await firmware.CancelAsync();
                    else await connection.ExecuteActionAsync(action);
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                { connection.ReportError(ex); }
            }
        }
        catch (OperationCanceledException) { }
        catch (WebSocketException ex) { logger.LogDebug(ex, "WebSocket receiver closed"); }
        catch (InvalidOperationException ex) { logger.LogDebug(ex, "Invalid WebSocket message"); }
        finally
        {
            updates.Unsubscribe(listener);
            stop.Cancel();
            await sender;
            if (socket.State == WebSocketState.CloseReceived)
                await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None);
        }
    }
}
