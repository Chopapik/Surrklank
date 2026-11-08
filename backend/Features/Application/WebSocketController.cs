using Surrklank.Features.Laboratory;
using System.Net.WebSockets;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Surrklank.Features.Application.DTOs;
using Surrklank.Features.Connection;
using Surrklank.Features.Firmware;
using Surrklank.Shared.Http;

namespace Surrklank.Features.Application;

[ApiController]
public sealed class WebSocketController(StateService updates, BleConnectionService connection,
    ApplicationStateService application, ILogger<WebSocketController> logger, LaboratoryState laboratory, LaboratoryService laboratoryService) : ControllerBase
{
    [HttpGet("/ws")]
    public async Task ConnectAsync()
    {
        if (!HttpContext.WebSockets.IsWebSocketRequest)
        {
            Response.StatusCode = 400;
            return;
        }
        if (!LocalOrigin.IsAllowed(Request))
        {
            Response.StatusCode = 403;
            return;
        }
        using var socket = await HttpContext.WebSockets.AcceptWebSocketAsync();
        var listener = updates.Subscribe();
        using var stop = CancellationTokenSource.CreateLinkedTokenSource(HttpContext.RequestAborted);
        async Task SendSnapshots()
        {
            try
            {
                await foreach (var _ in listener.Reader.ReadAllAsync(stop.Token))
                {
                    var bytes = JsonSerializer.SerializeToUtf8Bytes(application.Message(), StateService.JsonOptions);
                    await socket.SendAsync(bytes, WebSocketMessageType.Text, true, stop.Token);
                    var labBytes = JsonSerializer.SerializeToUtf8Bytes(laboratory.Snapshot(), StateService.JsonOptions);
                    await socket.SendAsync(labBytes, WebSocketMessageType.Text, true, stop.Token);
                    var timing = laboratoryService.TimingSnapshot();
                    if (timing != null)
                        await socket.SendAsync(JsonSerializer.SerializeToUtf8Bytes(timing, StateService.JsonOptions), WebSocketMessageType.Text, true, stop.Token);
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
                    if (result.MessageType == WebSocketMessageType.Close)
                        return;
                    if (result.MessageType != WebSocketMessageType.Text || message.Length + result.Count > 16384)
                        throw new InvalidOperationException("Invalid WebSocket message");
                    message.Write(buffer, 0, result.Count);
                } while (!result.EndOfMessage);
                try
                {
                    using var request = JsonDocument.Parse(message.ToArray());
                    string? action = request.RootElement.TryGetProperty("action", out var value) ? value.GetString() : null;
                    await connection.ExecuteActionAsync(action);
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    connection.ReportError(ex);
                }
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
