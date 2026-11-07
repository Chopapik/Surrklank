using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Surrklank.DTOs;

namespace Surrklank.Services;

public sealed record SerialPortInfo(string Port, string Name);

public sealed record FirmwareRequest(
    [property: JsonPropertyName("isolatedHardwareConfirmed")] bool IsolatedHardwareConfirmed,
    [property: JsonPropertyName("port")] string? Port);

// Coordinates one exclusive firmware operation. The browser can disconnect while it runs.
public sealed class FirmwareService(BleConnectionService connection, BleOtaService ota, AtxService atx,
    StateService updates, IWebHostEnvironment environment, ILogger<FirmwareService> logger) : IHostedService
{
    private readonly object sync = new();
    private readonly string root = Path.GetFullPath(Path.Combine(environment.ContentRootPath, ".."));
    private readonly string logRoot = Path.Combine(Path.GetTempPath(), "surrklank-idf");
    private readonly List<Dictionary<string, object?>> events = [];
    private string stage = "idle";
    private double? progress;
    private string? error;
    private IReadOnlyDictionary<string, object?>? result;
    private string? job;
    private bool busy;
    private CancellationTokenSource? cancellation;
    private Task? task;

    public bool Busy { get { lock (sync) return busy; } }

    public FirmwareDto Snapshot()
    {
        lock (sync)
        {
            return new FirmwareDto(stage, progress, error, result, busy, events.ToArray());
        }
    }

    private void Event(string newStage, double? newProgress = null, string? newError = null,
        IReadOnlyDictionary<string, object?>? newResult = null, Dictionary<string, object?>? details = null)
    {
        Dictionary<string, object?> entry;
        lock (sync)
        {
            stage = newStage;
            if (newProgress.HasValue) progress = newProgress;
            if (newError != null) error = newError;
            if (newResult != null) result = newResult;
            entry = new() { ["at"] = DateTimeOffset.UtcNow, ["job"] = job, ["stage"] = newStage };
            if (newProgress.HasValue) entry["progress"] = newProgress;
            if (newError != null) entry["error"] = newError;
            if (newResult != null) entry["result"] = newResult;
            if (details != null) foreach (var item in details) entry[item.Key] = item.Value;
            events.Add(entry);
            if (events.Count > 30) events.RemoveAt(0);
        }
        try
        {
            Directory.CreateDirectory(logRoot);
            File.AppendAllText(Path.Combine(logRoot, "validation.jsonl"), JsonSerializer.Serialize(entry, StateService.JsonOptions) + "\n");
        }
        catch (Exception ex) { logger.LogWarning(ex, "Could not write maintenance event"); }
        updates.Publish();
    }

    public async Task<IReadOnlyList<SerialPortInfo>> PortsAsync(CancellationToken cancellation = default)
    {
        var start = new ProcessStartInfo("pio") { WorkingDirectory = root, RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add("device"); start.ArgumentList.Add("list"); start.ArgumentList.Add("--json-output");
        using var process = Process.Start(start) ?? throw new InvalidOperationException("PlatformIO Core is not installed");
        var output = process.StandardOutput.ReadToEndAsync(cancellation);
        var stderr = process.StandardError.ReadToEndAsync(cancellation);
        try { await process.WaitForExitAsync(cancellation); }
        catch { if (!process.HasExited) process.Kill(true); throw; }
        if (process.ExitCode != 0) throw new InvalidOperationException("Could not list USB ports: " + await stderr);
        using var json = JsonDocument.Parse(await output);
        return json.RootElement.EnumerateArray()
            .Where(item => item.TryGetProperty("hwid", out var id) &&
                (id.GetString() ?? "").Contains("VID:PID=10C4:EA60", StringComparison.OrdinalIgnoreCase))
            .Select(item => new SerialPortInfo(item.GetProperty("port").GetString() ?? "", item.GetProperty("description").GetString() ?? ""))
            .ToArray();
    }

    public async Task StartAsync(string transport, FirmwareRequest request, CancellationToken requestCancellation)
    {
        if (!request.IsolatedHardwareConfirmed)
            throw new ArgumentException("Confirm isolated ESP32: USB only, ATX and register/instrument wiring disconnected");
        if (transport is not ("usb" or "ble")) throw new ArgumentException("Unknown transport");
        // Wait for a short discovery scan to finish before starting maintenance.
        if (!await connection.Gate.WaitAsync(TimeSpan.FromSeconds(2), requestCancellation))
            throw new InvalidOperationException("Device is busy");
        try
        {
            if (transport == "usb")
            {
                var ports = await PortsAsync(requestCancellation);
                if (string.IsNullOrWhiteSpace(request.Port) || !ports.Any(p => p.Port == request.Port))
                    throw new ArgumentException("Select the connected ESP32 CP2102 port explicitly");
            }
            lock (sync)
            {
                job = DateTime.UtcNow.ToString("yyyyMMdd'T'HHmmssfffffff");
                stage = "starting"; progress = null; error = null; result = null; busy = true;
                cancellation = new CancellationTokenSource();
                // Task.Run prevents completion before the task reference is stored.
                task = Task.Run(() => RunAsync(transport, request.Port, cancellation.Token));
            }
            updates.Publish();
        }
        catch { connection.Gate.Release(); throw; }
    }

    public async Task CancelAsync()
    {
        Task? current;
        lock (sync) { cancellation?.Cancel(); current = task; }
        if (current != null) await current;
    }

    private async Task ProcessAsync(string[] args, CancellationToken cancellationToken)
    {
        var start = new ProcessStartInfo("pio") { WorkingDirectory = root, RedirectStandardOutput = true,
            RedirectStandardError = true, UseShellExecute = false };
        foreach (var arg in args) start.ArgumentList.Add(arg);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("PlatformIO Core is not installed");
        string logPath;
        lock (sync) logPath = Path.Combine(logRoot, $"{job}-{stage}.log");
        Directory.CreateDirectory(logRoot);
        using var log = new StreamWriter(logPath, append: false) { AutoFlush = true };
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromMinutes(20));
        using var logLock = new SemaphoreSlim(1, 1);
        async Task ReadOutput(StreamReader reader)
        {
            while (await reader.ReadLineAsync(timeout.Token) is { } line)
            {
                await logLock.WaitAsync(timeout.Token);
                try { await log.WriteLineAsync(line); }
                finally { logLock.Release(); }
                if (line.Contains("Writing at") || line.Contains("Wrote "))
                {
                    var match = Regex.Match(line, @"(\d+)\s*%");
                    string currentStage; lock (sync) currentStage = stage;
                    Event(currentStage, match.Success ? int.Parse(match.Groups[1].Value) : null,
                        details: new() { ["message"] = line.Length > 200 ? line[^200..] : line });
                }
            }
        }
        try
        {
            await Task.WhenAll(ReadOutput(process.StandardOutput), ReadOutput(process.StandardError), process.WaitForExitAsync(timeout.Token));
            if (process.ExitCode != 0) throw new InvalidOperationException($"Build/upload failed ({process.ExitCode}); log: {logPath}");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            if (!process.HasExited) { process.Kill(true); await process.WaitForExitAsync(); }
            throw new TimeoutException($"Build/upload timed out; log: {logPath}");
        }
        catch
        {
            if (!process.HasExited) { process.Kill(true); await process.WaitForExitAsync(); }
            throw;
        }
    }

    private async Task<JsonElement> VerifyAsync(string identity, CancellationToken token)
    {
        var info = await connection.ReadInfoAsync(token);
        if (info.GetProperty("identity").GetString() != identity)
            throw new InvalidOperationException("Running firmware identity does not match the built image");
        await connection.PingAsync(token);
        if (info.GetProperty("trial").GetBoolean())
        {
            if (await connection.SendCommandAsync("CONFIRM", token) != "VALID")
                throw new InvalidOperationException("Trial confirmation failed");
            info = await connection.ReadInfoAsync(token);
            if (info.GetProperty("trial").GetBoolean()) throw new InvalidOperationException("Trial still pending after confirmation");
        }
        connection.SetDevice(info);
        return info;
    }

    private async Task RunAsync(string transport, string? port, CancellationToken token)
    {
        try
        {
            // Preserve the working OTA path; the shared gate excludes ATX polling here.
            if (transport == "ble") await connection.ConnectAsync(token);
            await atx.PrepareWhileLockedAsync(token);
            if (transport == "usb") await connection.DisconnectAsync();
            Event("building");
            var buildWatch = Stopwatch.StartNew();
            await ProcessAsync(["run", "-d", "firmware", "-e", "esp32"], token);
            byte[] image = await File.ReadAllBytesAsync(Path.Combine(root, "firmware/.pio/build/esp32/firmware.bin"), token);
            if (image.Length < 256 || image[0] != 0xE9) throw new InvalidOperationException("Invalid ESP32 application image");
            string identity = Convert.ToHexStringLower(image.AsSpan(176, 32));
            string digest = Convert.ToHexStringLower(SHA256.HashData(image));
            double buildSeconds = Math.Round(buildWatch.Elapsed.TotalSeconds, 3);
            Event("built", details: new() { ["bytes"] = image.Length, ["sha256"] = digest, ["identity"] = identity, ["build_seconds"] = buildSeconds });
            var overall = Stopwatch.StartNew();
            double transferSeconds;
            int? intervalUs = null;
            if (transport == "usb")
            {
                Event("usb_upload");
                await ProcessAsync(["run", "-d", "firmware", "-e", "esp32", "-t", "upload", "--upload-port", port!], token);
                transferSeconds = Math.Round(overall.Elapsed.TotalSeconds, 3);
            }
            else
            {
                await connection.ConnectAsync(token);
                Event("ble_upload", 0);
                var transfer = Stopwatch.StartNew();
                await ota.TransferAsync(connection.Current, image, (value, link) =>
                    Event("ble_upload", value, details: new() { ["link"] = link }), token);
                using var readyTimeout = CancellationTokenSource.CreateLinkedTokenSource(token);
                readyTimeout.CancelAfter(TimeSpan.FromSeconds(15));
                JsonElement info;
                while (true)
                {
                    readyTimeout.Token.ThrowIfCancellationRequested();
                    info = await connection.ReadInfoAsync(readyTimeout.Token);
                    if (info.GetProperty("error").GetInt32() != 0)
                        throw new InvalidOperationException($"ESP flash write failed: {info.GetProperty("error")}");
                    if (info.GetProperty("ota").GetString() == "ready") break;
                    await Task.Delay(100, readyTimeout.Token);
                }
                transferSeconds = Math.Round(transfer.Elapsed.TotalSeconds, 3);
                if (info.TryGetProperty("interval_us", out var interval)) intervalUs = interval.GetInt32();
                Event("verified_flash", details: new() { ["transfer_seconds"] = transferSeconds, ["transfer_interval_us"] = intervalUs });
                if (await connection.SendCommandAsync("REBOOT", token) != "REBOOTING")
                    throw new InvalidOperationException("Restart was not accepted");
            }
            Event("reconnecting");
            await connection.DisconnectAsync();
            await Task.Delay(1000, token);
            await connection.ConnectAsync(token);
            var verified = await VerifyAsync(identity, token);
            var data = JsonSerializer.Deserialize<Dictionary<string, object?>>(verified.GetRawText())!;
            data["transfer_seconds"] = transferSeconds; data["transfer_interval_us"] = intervalUs;
            data["build_seconds"] = buildSeconds; data["total_seconds"] = Math.Round(overall.Elapsed.TotalSeconds, 3);
            data["transport"] = transport;
            Event("complete", 100, newResult: data);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested)
        {
            Event("cancelled", newError: "Operation cancelled; inspect device state before retrying (boot selection may already be committed)");
            await connection.DisconnectAsync();
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Firmware maintenance failed");
            Event("failed", newError: ex.Message);
            await connection.DisconnectAsync();
        }
        finally
        {
            lock (sync) { busy = false; cancellation?.Dispose(); cancellation = null; }
            connection.Gate.Release();
            updates.Publish();
        }
    }

    public Task StartAsync(CancellationToken cancellationToken) => Task.CompletedTask;
    public Task StopAsync(CancellationToken cancellationToken) => CancelAsync();
}
