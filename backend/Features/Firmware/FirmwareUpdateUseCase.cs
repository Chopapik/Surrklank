using System.Diagnostics;
using System.Text.Json;
using Surrklank.Features.Atx;
using Surrklank.Features.Connection;
using Surrklank.Features.Firmware.Toolchain;
using Surrklank.Features.Firmware.Transport;

namespace Surrklank.Features.Firmware;

public sealed class FirmwareUpdateUseCase(IDeviceConnection connection, BleOtaService ota,
    AtxService atx, IFirmwareToolchain toolchain, FirmwareJobState job)
{
    public async Task ExecuteAsync(IDeviceOperation operation, string transport,
        string? port, CancellationToken token)
    {
        // The reservation remains owned by this job through build, transfer and verification.
        if (transport == "ble")
            await operation.ConnectAsync(token);
        await atx.PrepareWhileLockedAsync(operation, token);
        if (transport == "usb")
            await operation.DisconnectAsync();
        job.Record("building");
        var build = await toolchain.BuildAsync(job.GetLogPath(), job.ReportOutput, token);
        byte[] image = build.Image;
        string identity = build.Identity;
        string digest = build.Digest;
        double buildSeconds = build.DurationSeconds;
        job.Record("built", details: new()
        {
            ["bytes"] = image.Length,
            ["sha256"] = digest,
            ["identity"] = identity,
            ["build_seconds"] = buildSeconds
        });
        var overall = Stopwatch.StartNew();
        double transferSeconds;
        int? intervalUs = null;
        if (transport == "usb")
        {
            job.Record("usb_upload");
            await toolchain.UploadUsbAsync(port!, job.GetLogPath(), job.ReportOutput, token);
            transferSeconds = Math.Round(overall.Elapsed.TotalSeconds, 3);
        }
        else
        {
            await operation.ConnectAsync(token);
            job.Record("ble_upload", 0);
            var transfer = Stopwatch.StartNew();
            try
            {
                await operation.TransferAsync(ota, image, (value, link) =>
                    job.Record("ble_upload", value, details: new()
                    {
                        ["link"] = link
                    }), token);
            }
            catch (TimeoutException)
            {
                // A lost final sector receipt can coexist with a complete, validated flash.
                // Reconcile once; never resend the image on an uncertain outcome.
                using var reconciliation = CancellationTokenSource.CreateLinkedTokenSource(token);
                reconciliation.CancelAfter(TimeSpan.FromSeconds(10));
                var flash = await operation.ReadInfoAsync(reconciliation.Token);
                if (flash.GetProperty("ota").GetString() != "ready" ||
                    flash.GetProperty("error").GetInt32() != 0 ||
                    flash.GetProperty("received").GetInt32() != image.Length)
                    throw new FirmwareOutcomeUnknownException("OTA receipt timed out; complete flash was not confirmed");
                job.Record("reconciled_transfer", details: new() { ["received"] = image.Length });
            }
            var info = await ConfirmFlashAsync(operation, token);
            transferSeconds = Math.Round(transfer.Elapsed.TotalSeconds, 3);
            if (info.TryGetProperty("interval_us", out var interval))
                intervalUs = interval.GetInt32();
            job.Record("verified_flash", details: new()
            {
                ["transfer_seconds"] = transferSeconds,
                ["transfer_interval_us"] = intervalUs
            });
            if (await operation.SendCommandAsync("REBOOT", token) != "REBOOTING")
                throw new InvalidOperationException("Restart was not accepted");
        }
        job.Record("reconnecting");
        await operation.DisconnectAsync();
        await Task.Delay(1000, token);
        await operation.ConnectAsync(token);
        var verified = await VerifyAsync(operation, identity, token);
        var data = JsonSerializer.Deserialize<Dictionary<string, object?>>(verified.GetRawText())!;
        data["transfer_seconds"] = transferSeconds;
        data["transfer_interval_us"] = intervalUs;
        data["build_seconds"] = buildSeconds;
        data["total_seconds"] = Math.Round(overall.Elapsed.TotalSeconds, 3);
        data["transport"] = transport;
        job.Record("complete", 100, result: data);
    }

    private async Task<JsonElement> VerifyAsync(IDeviceOperation operation, string identity, CancellationToken token)
    {
        var info = await operation.ReadInfoAsync(token);
        if (info.GetProperty("identity").GetString() != identity)
            throw new InvalidOperationException("Running firmware identity does not match the built image");
        await operation.PingAsync(token);
        if (info.GetProperty("trial").GetBoolean())
        {
            if (await operation.SendCommandAsync("CONFIRM", token) != "VALID")
                throw new InvalidOperationException("Trial confirmation failed");
            info = await operation.ReadInfoAsync(token);
            if (info.GetProperty("trial").GetBoolean())
                throw new InvalidOperationException("Trial still pending after confirmation");
        }
        connection.SetDevice(info);
        return info;
    }

    private async Task<JsonElement> ConfirmFlashAsync(IDeviceOperation operation, CancellationToken token)
    {
        bool timedOut = false;
        using (var readyTimeout = CancellationTokenSource.CreateLinkedTokenSource(token))
        {
            readyTimeout.CancelAfter(TimeSpan.FromSeconds(15));
            if (connection.Snapshot().Subscribed)
            {
                try
                {
                    await operation.WaitForFlashReadyAsync(readyTimeout.Token);
                }
                catch (OperationCanceledException) when (!token.IsCancellationRequested && readyTimeout.IsCancellationRequested)
                {
                    timedOut = true;
                    job.Record("reconciling_flash");
                }
                catch (InvalidOperationException ex) when (!connection.Snapshot().Connected)
                {
                    throw new FirmwareOutcomeUnknownException("Firmware outcome is unknown: BLE disconnected before ready confirmation", ex);
                }
            }
            else
            {
                // One-time migration from an image that cannot notify.
                while (true)
                {
                    var legacy = await operation.ReadInfoAsync(readyTimeout.Token);
                    if (legacy.GetProperty("error").GetInt32() != 0)
                        throw new InvalidOperationException("ESP flash write failed");
                    if (legacy.GetProperty("ota").GetString() == "ready")
                        break;
                    await Task.Delay(100, readyTimeout.Token);
                }
            }
        }
        if (!connection.Snapshot().Connected)
            throw new FirmwareOutcomeUnknownException("Firmware outcome is unknown: BLE disconnected; reconnect and inspect device before retrying");
        // A new budget permits one INFO after the ready deadline, without releasing ownership.
        using var infoTimeout = CancellationTokenSource.CreateLinkedTokenSource(token);
        infoTimeout.CancelAfter(TimeSpan.FromSeconds(10));
        JsonElement info;
        try
        {
            info = await operation.ReadInfoAsync(infoTimeout.Token);
        }
        catch (Exception ex) when (!token.IsCancellationRequested)
        {
            throw new FirmwareOutcomeUnknownException("Firmware outcome is unknown: INFO reconciliation failed; inspect device before retrying", ex);
        }
        connection.SetDevice(info);
        if (info.GetProperty("error").GetInt32() != 0)
            throw new InvalidOperationException($"ESP flash write failed: {info.GetProperty("error")}");
        if (info.GetProperty("ota").GetString() != "ready")
            throw new FirmwareOutcomeUnknownException("Firmware outcome is unknown: ESP32 did not confirm ready; no transfer replay was attempted");
        if (timedOut)
            job.Record("flash_reconciled", details: new()
            {
                ["confirmed_by_info"] = true
            });
        return info;
    }

}
