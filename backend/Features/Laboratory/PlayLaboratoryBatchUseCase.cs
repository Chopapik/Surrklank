using System.Security.Cryptography;
using Surrklank.Features.Application;
using Surrklank.Features.Connection;
using Surrklank.Features.Laboratory.DTOs;

namespace Surrklank.Features.Laboratory;

public sealed class PlayLaboratoryBatchUseCase(IDeviceConnection connection, LaboratoryState state, StateService updates)
{
    private readonly SemaphoreSlim _preparation = new(1, 1);
    public async Task<uint> ExecuteAsync(LaboratoryPlayRequestDto request, CancellationToken cancellationToken)
    {
        if (request.Devices == null || request.Devices.Count is < 1 or > 8)
            throw new ArgumentException("Provide 1 to 8 distinct FDD devices");
        if (request.Devices.Any(d => d == null || d.DeviceType != "fdd" || d.Device is < 1 or > 8 || !double.IsFinite(d.FrequencyHz) || d.FrequencyHz is < 1 or > 300 || d.DurationMs is < 1 or > 60000))
            throw new ArgumentException("FDD limits: device 1–8, frequency 1–300 Hz, duration 1–60000 ms");
        if (request.Devices.Select(d => d.Device).Distinct().Count() != request.Devices.Count)
            throw new ArgumentException("A device must appear only once in a batch");
        if (!await _preparation.WaitAsync(0, cancellationToken)) throw new DeviceBusyException("laboratory_preparation");
        uint batch = (uint)RandomNumberGenerator.GetInt32(1, int.MaxValue);
        bool began = false, commitAttempted = false;
        var listener = updates.Subscribe();
        try
        {
            using (var operation = await connection.ReserveAsync("laboratory_prepare", cancellationToken))
            {
                LaboratoryService.RequireReady(connection, state);
                if (connection.Snapshot().AtxOn != true) throw new InvalidOperationException("ATX output must be ON before starting Laboratory");
                if (request.Devices.Any(d => LaboratoryState.IsActive(state.Snapshot().Devices[d.Device - 1].State)))
                    throw new DeviceBusyException("laboratory_device");
                state.SetPreparing(true);
                int mask = request.Devices.Sum(d => 1 << (d.Device - 1));
                began = true;
                await LaboratoryService.SendAsync(operation, $"LAB BEGIN {batch} {mask}", cancellationToken);
                foreach (var device in request.Devices)
                    await LaboratoryService.SendAsync(operation, FormattableString.Invariant($"LAB SET {batch} {device.Device} {(uint)Math.Round(device.FrequencyHz * 1000)} {device.DurationMs}"), cancellationToken);
                await LaboratoryService.SendAsync(operation, $"LAB PREPARE {batch}", cancellationToken);
            }
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(8));
            try
            {
                while (!Ready(batch, request)) await listener.Reader.ReadAsync(timeout.Token);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                using var refresh = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                using var operation = await connection.ReserveAsync("laboratory_refresh", refresh.Token);
                await operation.RefreshLaboratoryAsync(refresh.Token);
                if (!Ready(batch, request)) throw new InvalidOperationException("Laboratory preparation timed out; TRACK0 readiness was not confirmed");
            }
            using (var operation = await connection.ReserveAsync("laboratory_start", cancellationToken))
            {
                LaboratoryService.RequireReady(connection, state);
                if (!Ready(batch, request)) throw new InvalidOperationException("Batch is no longer ready");
                commitAttempted = true;
                await LaboratoryService.SendAsync(operation, $"LAB COMMIT {batch}", cancellationToken);
                await operation.RefreshLaboratoryAsync(cancellationToken);
            }
            return batch;
        }
        catch (Exception ex)
        {
            if (commitAttempted && ex is not LaboratoryCommandRejectedException)
            {
                state.MarkUncertain();
                throw new LaboratoryOutcomeUnknownException("Batch start outcome is unknown; inspect live state before retrying", ex);
            }
            if (began)
            {
                try
                {
                    using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                    using var operation = await connection.ReserveAsync("laboratory_abort", cleanup.Token);
                    await LaboratoryService.SendAsync(operation, $"LAB ABORT {batch}", cleanup.Token);
                    await operation.RefreshLaboratoryAsync(cleanup.Token);
                }
                catch { state.MarkUncertain(); }
            }
            throw;
        }
        finally
        {
            state.SetPreparing(false);
            updates.Unsubscribe(listener);
            _preparation.Release();
        }
    }
    private bool Ready(uint batch, LaboratoryPlayRequestDto request)
    {
        var snapshot = state.Snapshot();
        if (!snapshot.Available) throw new InvalidOperationException("Laboratory state unavailable; reconnect before retrying");
        var devices = request.Devices.Select(d => snapshot.Devices[d.Device - 1]).ToArray();
        var failed = devices.OrderBy(d => d.ErrorCode == 5).FirstOrDefault(d => d.Batch == batch && d.ErrorCode != 0);
        if (failed != null) throw new InvalidOperationException($"FDD {failed.Device}: {failed.Message}");
        if (devices.Any(d => d.Batch == batch && d.State is "parking" or "parked")) throw new InvalidOperationException("Batch was stopped during preparation");
        return devices.All(d => d.Batch == batch && d.State == "ready");
    }
}
