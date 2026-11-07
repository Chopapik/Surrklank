using Surrklank.Features.Connection;
using Surrklank.Features.Firmware.DTOs;
using Surrklank.Features.Firmware.Toolchain;

namespace Surrklank.Features.Firmware;

// Owns the background job and its reservation beyond the HTTP request lifetime.
public sealed class FirmwareService(IDeviceConnection connection, FirmwareUpdateUseCase update,
    IFirmwareToolchain toolchain, FirmwareJobState job, ILogger<FirmwareService> logger) : IHostedService
{
    private readonly object _sync = new();
    private CancellationTokenSource? _cancellation;
    private Task? _task;

    public FirmwareDto Snapshot() => job.Snapshot();

    public Task<IReadOnlyList<SerialPortDto>> PortsAsync(CancellationToken cancellation = default) =>
        toolchain.ListPortsAsync(cancellation);

    public async Task StartAsync(string transport, FirmwareRequestDto request, CancellationToken requestCancellation)
    {
        if (!request.IsolatedHardwareConfirmed)
            throw new ArgumentException("Confirm isolated ESP32: USB only, ATX and register/instrument wiring disconnected");
        if (transport is not ("usb" or "ble"))
            throw new ArgumentException("Unknown transport");

        var operation = await connection.ReserveAsync("firmware_update", requestCancellation);
        try
        {
            if (transport == "usb")
            {
                var ports = await PortsAsync(requestCancellation);
                if (string.IsNullOrWhiteSpace(request.Port) || !ports.Any(port => port.Port == request.Port))
                    throw new ArgumentException("Select the connected ESP32 CP2102 port explicitly");
            }
            lock (_sync)
            {
                job.Begin();
                _cancellation = new CancellationTokenSource();
                var token = _cancellation.Token;
                _task = Task.Run(() => RunAsync(operation, transport, request.Port, token));
            }
        }
        catch
        {
            operation.Dispose();
            throw;
        }
    }

    private async Task RunAsync(IDeviceOperation operation, string transport,
        string? port, CancellationToken cancellationToken)
    {
        try
        {
            await update.ExecuteAsync(operation, transport, port, cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            job.Record("cancelled", error: "Operation cancelled; inspect device state before retrying (boot selection may already be committed)");
            await operation.DisconnectAsync();
        }
        catch (FirmwareOutcomeUnknownException ex)
        {
            logger.LogWarning(ex, "Firmware outcome is uncertain");
            job.Record("uncertain", error: ex.Message);
            await operation.DisconnectAsync();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Firmware maintenance failed");
            job.Record("failed", error: ex.Message);
            await operation.DisconnectAsync();
        }
        finally
        {
            lock (_sync)
            {
                _cancellation?.Dispose();
                _cancellation = null;
            }
            job.Finish();
            operation.Dispose();
        }
    }

    public Task StartAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        Task? current;
        lock (_sync)
        {
            _cancellation?.Cancel();
            current = _task;
        }
        if (current != null)
            await current.WaitAsync(cancellationToken);
    }
}
