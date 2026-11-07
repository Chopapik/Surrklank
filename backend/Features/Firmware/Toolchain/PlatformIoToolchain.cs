using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using Surrklank.Features.Firmware.DTOs;

namespace Surrklank.Features.Firmware.Toolchain;

public sealed class PlatformIoToolchain(IWebHostEnvironment environment) : IFirmwareToolchain
{
    private readonly string _root = Path.GetFullPath(Path.Combine(environment.ContentRootPath, ".."));

    public async Task<IReadOnlyList<SerialPortDto>> ListPortsAsync(CancellationToken cancellationToken)
    {
        using var process = Start(["device", "list", "--json-output"]);
        var output = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderr = process.StandardError.ReadToEndAsync(cancellationToken);
        try
        {
            await process.WaitForExitAsync(cancellationToken);
        }
        catch
        {
            if (!process.HasExited)
                process.Kill(true);
            throw;
        }

        if (process.ExitCode != 0)
            throw new InvalidOperationException("Could not list USB ports: " + await stderr);

        using var json = JsonDocument.Parse(await output);
        return json.RootElement.EnumerateArray()
            .Where(item => item.TryGetProperty("hwid", out var id) &&
                (id.GetString() ?? "").Contains("VID:PID=10C4:EA60", StringComparison.OrdinalIgnoreCase))
            .Select(item => new SerialPortDto(item.GetProperty("port").GetString() ?? "",
                item.GetProperty("description").GetString() ?? ""))
            .ToArray();
    }

    public async Task<FirmwareBuild> BuildAsync(string logPath, Action<string> reportOutput,
        CancellationToken cancellationToken)
    {
        var watch = Stopwatch.StartNew();
        await RunAsync(["run", "-d", "firmware", "-e", "esp32"], logPath, reportOutput, cancellationToken);
        byte[] image = await File.ReadAllBytesAsync(Path.Combine(_root, "firmware/.pio/build/esp32/firmware.bin"), cancellationToken);
        if (image.Length < 256 || image[0] != 0xE9)
            throw new InvalidOperationException("Invalid ESP32 application image");

        return new FirmwareBuild(image, Convert.ToHexStringLower(image.AsSpan(176, 32)),
            Convert.ToHexStringLower(SHA256.HashData(image)), Math.Round(watch.Elapsed.TotalSeconds, 3));
    }

    public Task UploadUsbAsync(string port, string logPath, Action<string> reportOutput,
        CancellationToken cancellationToken) =>
        RunAsync(["run", "-d", "firmware", "-e", "esp32", "-t", "upload", "--upload-port", port],
            logPath, reportOutput, cancellationToken);

    private Process Start(string[] arguments)
    {
        var start = new ProcessStartInfo("pio")
        {
            WorkingDirectory = _root,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };
        foreach (var argument in arguments)
            start.ArgumentList.Add(argument);
        return Process.Start(start) ?? throw new InvalidOperationException("PlatformIO Core is not installed");
    }

    private async Task RunAsync(string[] arguments, string logPath, Action<string> reportOutput,
        CancellationToken cancellationToken)
    {
        using var process = Start(arguments);
        Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
        using var log = new StreamWriter(logPath, append: false) { AutoFlush = true };
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromMinutes(20));
        using var logLock = new SemaphoreSlim(1, 1);

        async Task ReadOutputAsync(StreamReader reader)
        {
            while (await reader.ReadLineAsync(timeout.Token) is { } line)
            {
                await logLock.WaitAsync(timeout.Token);
                try
                {
                    await log.WriteLineAsync(line);
                }
                finally { logLock.Release(); }
                reportOutput(line);
            }
        }

        try
        {
            await Task.WhenAll(ReadOutputAsync(process.StandardOutput), ReadOutputAsync(process.StandardError),
                process.WaitForExitAsync(timeout.Token));
            if (process.ExitCode != 0)
                throw new InvalidOperationException($"Build/upload failed ({process.ExitCode}); log: {logPath}");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            if (!process.HasExited)
            {
                process.Kill(true);
                await process.WaitForExitAsync();
            }
            throw new TimeoutException($"Build/upload timed out; log: {logPath}");
        }
        catch
        {
            if (!process.HasExited)
            {
                process.Kill(true);
                await process.WaitForExitAsync();
            }
            throw;
        }
    }
}
