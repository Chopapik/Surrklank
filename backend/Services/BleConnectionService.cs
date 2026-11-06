using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ElectromechanicalMidi.DTOs;
using SimpleSharpBLE;

namespace ElectromechanicalMidi.Services;

// One device connection shared by WebSocket commands and firmware maintenance.
public sealed class BleConnectionService(StateService updates, ILogger<BleConnectionService> logger) : IHostedService
{
    public const string Service = "0000fff0-0000-1000-8000-00805f9b34fb";
    public const string Command = "0000fff1-0000-1000-8000-00805f9b34fb";
    public const string Info = "0000fff2-0000-1000-8000-00805f9b34fb";
    private readonly object sync = new();
    private Peripheral? peripheral;
    private string state = "unknown";
    private string? error;
    private int session;
    private PingResult? lastPing;
    private JsonElement? device;
    private int? mtu;
    private readonly List<ConnectionEvent> events = [];
    private readonly CancellationTokenSource stopping = new();
    private Task? observer;
    private Task? discovery;
    private string discoveryState = "searching";
    private bool autoConnect = true;

    // Every operation touching the device, including firmware maintenance, holds this gate.
    public SemaphoreSlim Gate { get; } = new(1, 1);
    public Peripheral Current => peripheral ?? throw new InvalidOperationException("ESP32 is not connected");

    public ConnectionDto Snapshot()
    {
        lock (sync)
        {
            return new ConnectionDto(state, error, session, lastPing, device, events.ToArray(), mtu, discoveryState);
        }
    }

    private void Change(string next, string? reason = null)
    {
        lock (sync)
        {
            state = next;
            error = reason;
            events.Add(new ConnectionEvent(DateTimeOffset.UtcNow, state, error, session));
            if (events.Count > 30) events.RemoveAt(0);
        }
        updates.Publish();
    }

    public void ReportError(Exception exception)
    {
        lock (sync) error = exception.Message;
        updates.Publish();
    }

    public async Task ExecuteActionAsync(string? action)
    {
        // A short discovery scan may be running; let it finish before a manual action.
        if (!await Gate.WaitAsync(TimeSpan.FromSeconds(2))) throw new InvalidOperationException("Device is busy");
        try
        {
            switch (action)
            {
                case "connect":
                    autoConnect = true;
                    await ConnectAsync();
                    break;
                case "disconnect":
                    autoConnect = false;
                    await DisconnectAsync();
                    SetDiscovery("paused");
                    break;
                case "ping": await PingAsync(); break;
                default: throw new ArgumentException("Unknown action");
            }
        }
        finally { Gate.Release(); }
    }

    // Caller holds Gate. Native operations cannot be interrupted after they begin.
    public async Task ConnectAsync(CancellationToken cancellation = default)
    {
        if (peripheral is { IsConnected: true }) return;
        if (peripheral != null) await DisconnectAsync();
        int thisSession;
        lock (sync) thisSession = ++session;
        Change("scanning");
        Peripheral? selected = null;
        IReadOnlyList<Adapter> adapters = [];
        try
        {
            adapters = Adapter.GetAdapters();
            if (adapters.Count == 0) throw new InvalidOperationException("No Bluetooth adapter is available");
            foreach (var adapter in adapters)
            {
                cancellation.ThrowIfCancellationRequested();
                using var scanTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                scanTimeout.CancelAfter(TimeSpan.FromSeconds(12));
                var found = new TaskCompletionSource<Peripheral>(TaskCreationOptions.RunContinuationsAsynchronously);
                using var registration = scanTimeout.Token.Register(() => found.TrySetCanceled(scanTimeout.Token));
                void OnFound(object? sender, PeripheralEventArgs e)
                {
                    try
                    {
                        if (e.Peripheral.Identifier == "EM-MIDI-IDF" && found.TrySetResult(e.Peripheral)) return;
                    }
                    catch (Exception ex) { logger.LogDebug(ex, "Could not read BLE advertisement"); }
                    e.Peripheral.Dispose();
                }
                adapter.ScanFound += OnFound;
                adapter.ScanUpdated += OnFound;
                bool scanning = false;
                try
                {
                    adapter.ScanStart();
                    scanning = true;
                    selected = await found.Task;
                }
                catch (OperationCanceledException) when (!cancellation.IsCancellationRequested) { }
                finally
                {
                    if (scanning) adapter.ScanStop();
                    adapter.ScanFound -= OnFound;
                    adapter.ScanUpdated -= OnFound;
                }
                if (selected != null) break;
            }
            if (selected == null) throw new InvalidOperationException("ESP32 EM-MIDI-IDF was not found");
            cancellation.ThrowIfCancellationRequested();
            Change("connecting");
            var current = selected;
            current.Disconnected += (_, _) => LinkLost(current, thisSession);
            lock (sync) peripheral = current;
            selected = null; // Ownership moves to this service, including setup-failure cleanup.
            await current.ConnectAsync(cancellation);
            cancellation.ThrowIfCancellationRequested();
            if (!current.IsConnected) throw new InvalidOperationException("BLE connection was not established");
            var information = await ReadInfoAsync(cancellation);
            lock (sync)
            {
                if (peripheral != current || session != thisSession || !current.IsConnected)
                    throw new InvalidOperationException("BLE disconnected while reading device information");
                device = information;
                // SimpleBLE's macOS implementation reports payload length, not ATT MTU.
                mtu = current.Mtu + (OperatingSystem.IsMacOS() ? 3 : 0);
                Change("connected");
            }
        }
        catch (Exception ex)
        {
            await DisconnectAsync();
            // DisconnectAsync disposes a selected peripheral once it has been registered.
            selected?.Dispose();
            Change("error", ex.Message);
            throw;
        }
        finally { foreach (var adapter in adapters) adapter.Dispose(); }
    }

    private void LinkLost(Peripheral client, int clientSession)
    {
        lock (sync)
        {
            if (peripheral == client && session == clientSession && state is "connected" or "connecting")
                Change("disconnected", "BLE connection lost");
        }
    }

    public async Task DisconnectAsync()
    {
        Peripheral? old;
        lock (sync) { old = peripheral; peripheral = null; mtu = null; }
        if (old != null)
        {
            try { if (old.IsConnected) await old.DisconnectAsync(); }
            catch (Exception ex) { logger.LogWarning(ex, "BLE disconnect failed"); }
            finally { old.Dispose(); }
        }
        Change("disconnected");
    }

    public async Task<JsonElement> ReadInfoAsync(CancellationToken cancellation = default)
    {
        var bytes = await Current.ReadAsync(Service, Info, cancellation);
        return JsonSerializer.Deserialize<JsonElement>(bytes);
    }

    public async Task<string> SendCommandAsync(string text, CancellationToken cancellation = default)
    {
        var client = Current;
        await client.WriteRequestAsync(Service, Command, Encoding.ASCII.GetBytes(text), cancellation);
        return Encoding.ASCII.GetString(await client.ReadAsync(Service, Command, cancellation));
    }

    public async Task PingAsync(CancellationToken cancellation = default)
    {
        var token = RandomNumberGenerator.GetInt32(1_000_000_000).ToString();
        var watch = Stopwatch.StartNew();
        try
        {
            var reply = await SendCommandAsync("PING " + token, cancellation);
            if (reply != "PONG " + token) throw new InvalidOperationException("Mismatched PONG");
            lock (sync) { error = null; lastPing = new PingResult(true, Math.Round(watch.Elapsed.TotalMilliseconds, 1), DateTimeOffset.UtcNow, reply); }
        }
        catch (Exception ex)
        {
            lock (sync) lastPing = new PingResult(false, Error: ex.Message);
            updates.Publish();
            throw;
        }
        updates.Publish();
    }

    public void SetDevice(JsonElement information) { lock (sync) device = information; updates.Publish(); }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        observer = ObserveAsync(stopping.Token);
        if (Environment.GetEnvironmentVariable("BLE_AUTO_SCAN") != "false")
            discovery = DiscoverAsync(stopping.Token);
        return Task.CompletedTask;
    }

    private void SetDiscovery(string value)
    {
        lock (sync)
        {
            if (discoveryState == value) return;
            discoveryState = value;
            // Discovery establishes that this service has no active connection.
            // Finding an advertisement does not mean the ESP32 is connected.
            if (state == "unknown" && value is "found" or "not_found")
                Change("disconnected");
        }
        updates.Publish();
    }

    // Search in short scans so manual commands and firmware maintenance can take the gate.
    private async Task DiscoverAsync(CancellationToken cancellation)
    {
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                if (await Gate.WaitAsync(0, cancellation))
                {
                    try
                    {
                        bool connected;
                        lock (sync) connected = state == "connected";
                        if (connected) SetDiscovery("connected");
                        else if (!autoConnect) SetDiscovery("paused");
                        else
                        {
                            var adapters = Adapter.GetAdapters();
                            try
                            {
                                if (adapters.Count == 0) SetDiscovery("unavailable");
                                else
                                {
                                    bool found = false;
                                    foreach (var adapter in adapters)
                                    {
                                        await adapter.ScanForAsync(TimeSpan.FromSeconds(1), cancellation);
                                        var devices = adapter.ScanGetResults();
                                        try { found |= devices.Any(device => device.Identifier == "EM-MIDI-IDF"); }
                                        finally { foreach (var device in devices) device.Dispose(); }
                                        if (found) break;
                                    }
                                    if (found)
                                    {
                                        SetDiscovery("connecting");
                                        await ConnectAsync(cancellation);
                                        SetDiscovery("connected");
                                    }
                                    else SetDiscovery("not_found");
                                }
                            }
                            finally { foreach (var adapter in adapters) adapter.Dispose(); }
                        }
                    }
                    catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { throw; }
                    catch (Exception ex)
                    {
                        logger.LogWarning(ex, "BLE discovery failed");
                        SetDiscovery("unavailable");
                    }
                    finally { Gate.Release(); }
                }
                else SetDiscovery("paused");
                await Task.Delay(TimeSpan.FromSeconds(2), cancellation);
            }
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
    }

    private async Task ObserveAsync(CancellationToken cancellation)
    {
        try
        {
            using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(100));
            while (await timer.WaitForNextTickAsync(cancellation))
            {
                Peripheral? client; int currentSession; string currentState;
                lock (sync) { client = peripheral; currentSession = session; currentState = state; }
                if (client != null && currentState == "connected")
                {
                    try { if (!client.IsConnected) LinkLost(client, currentSession); }
                    catch (ObjectDisposedException) { }
                    catch (Exception ex) { logger.LogDebug(ex, "Could not inspect BLE link state"); }
                }
            }
        }
        catch (OperationCanceledException) { }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        stopping.Cancel();
        if (observer != null) await observer;
        if (discovery != null) await discovery;
        await Gate.WaitAsync(cancellationToken);
        try { await DisconnectAsync(); }
        finally { Gate.Release(); }
    }
}
