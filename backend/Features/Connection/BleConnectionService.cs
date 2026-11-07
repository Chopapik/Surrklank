using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using SimpleSharpBLE;
using Surrklank.Features.Application;
using Surrklank.Features.Connection.DTOs;
using Surrklank.Features.Firmware.Transport;

namespace Surrklank.Features.Connection;

public sealed class BleConnectionService(StateService updates, ILogger<BleConnectionService> logger) : IHostedService, IDeviceConnection
{
    public const string Service = "0000fff0-0000-1000-8000-00805f9b34fb";
    public const string Command = "0000fff1-0000-1000-8000-00805f9b34fb";
    public const string Info = "0000fff2-0000-1000-8000-00805f9b34fb";
    private readonly object _sync = new();
    private Peripheral? _peripheral;
    private string _state = "unknown";
    private string? _error;
    private int _session;
    private PingResultDto? _lastPing;
    private JsonElement? _device;
    private int? _mtu;
    private DeviceState _deviceState = new();
    private bool _subscribed;
    private TaskCompletionSource _stateChanged = NewSignal();
    private static TaskCompletionSource NewSignal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private void SignalState()
    {
        var previous = _stateChanged;
        _stateChanged = NewSignal();
        previous.TrySetResult();
    }
    private readonly List<ConnectionEventDto> _events = [];
    private readonly CancellationTokenSource _stopping = new();
    private Task? _observer;
    private Task? _discovery;
    private string _discoveryState = "searching";
    private bool _autoConnect = true;

    private readonly SemaphoreSlim _gate = new(1, 1);
    private DeviceOperation? _activeOperation;
    private readonly Channel<byte> _refreshRequests = Channel.CreateBounded<byte>(
        new BoundedChannelOptions(1) { FullMode = BoundedChannelFullMode.DropOldest, SingleReader = true });
    private Task? _reconciliation;
    private Peripheral Current => _peripheral ?? throw new InvalidOperationException("ESP32 is not connected");

    public ConnectionDto Snapshot()
    {
        lock (_sync)
        {
            return new ConnectionDto(_state, _error, _session, _lastPing, _device, _events.ToArray(), _mtu, _discoveryState,
                _state == "connected" ? _deviceState.AtxOn : null,
                _state == "connected" ? _deviceState.Firmware : null, _subscribed, _activeOperation?.Reason);
        }
    }

    public IReadOnlyList<ConnectionEventDto>? GetEvents(int? limit) =>
        limit.HasValue ? Snapshot().Events.TakeLast(limit.Value).ToArray() : null;

    private void Change(string next, string? reason = null)
    {
        lock (_sync)
        {
            _state = next;
            _error = reason;
            _events.Add(new ConnectionEventDto(DateTimeOffset.UtcNow, _state, _error, _session));
            if (_events.Count > 30)
                _events.RemoveAt(0);
        }
        updates.Publish();
    }

    public void ReportError(Exception exception)
    {
        lock (_sync)
            _error = exception.Message;
        updates.Publish();
    }

    public async Task<DeviceOperation> ReserveAsync(string reason, CancellationToken cancellation = default)
    {
        var operation = await TryReserveAsync(reason, TimeSpan.FromSeconds(2), cancellation);
        if (operation != null)
            return operation;
        lock (_sync)
            throw new DeviceBusyException(_activeOperation?.Reason);
    }

    async Task<IDeviceOperation> IDeviceConnection.ReserveAsync(string reason, CancellationToken cancellation) =>
        await ReserveAsync(reason, cancellation);

    private async Task<DeviceOperation?> TryReserveAsync(string reason, TimeSpan timeout, CancellationToken cancellation)
    {
        if (!await _gate.WaitAsync(timeout, cancellation))
            return null;
        DeviceOperation operation;
        lock (_sync)
        {
            operation = new DeviceOperation(this, reason);
            _activeOperation = operation;
        }
        updates.Publish();
        return operation;
    }

    public async Task ExecuteActionAsync(string? action)
    {
        if (action is not ("connect" or "disconnect" or "ping"))
            throw new ArgumentException("Unknown action");
        using var operation = await ReserveAsync(action);
        switch (action)
        {
            case "connect":
                _autoConnect = true;
                await operation.ConnectAsync();
                break;
            case "disconnect":
                _autoConnect = false;
                await operation.DisconnectAsync();
                SetDiscovery("paused");
                break;
            case "ping":
                await operation.PingAsync();
                break;
        }
    }

    public sealed class DeviceOperation : IDisposable, IDeviceOperation
    {
        private BleConnectionService? _owner;
        public string Reason { get; }
        internal DeviceOperation(BleConnectionService owner, string reason)
        {
            this._owner = owner;
            Reason = reason;
        }
        private BleConnectionService Owner
        {
            get
            {
                var service = _owner ?? throw new ObjectDisposedException(nameof(DeviceOperation));
                lock (service._sync)
                    if (service._activeOperation != this)
                        throw new InvalidOperationException("Inactive device reservation");
                return service;
            }
        }
        public Task ConnectAsync(CancellationToken token = default) => Owner.ConnectAsync(token);
        public Task DisconnectAsync() => Owner.DisconnectAsync();
        public Task PingAsync(CancellationToken token = default) => Owner.PingAsync(token);
        public Task<string> SendCommandAsync(string command, CancellationToken token = default) => Owner.SendCommandAsync(command, token);
        public Task<JsonElement> ReadInfoAsync(CancellationToken token = default) => Owner.ReadInfoAsync(token);
        public Task WaitForFlashReadyAsync(CancellationToken token) => Owner.WaitForFlashReadyAsync(token);
        public Task TransferAsync(BleOtaService ota, byte[] image, Action<double, object> progress, CancellationToken token) =>
            ota.TransferAsync(Owner.Current, image, progress, token);
        public void Dispose()
        {
            var service = Interlocked.Exchange(ref _owner, null);
            if (service == null)
                return;
            service.ReleaseReservation();
        }
    }

    private void ReleaseReservation()
    {
        lock (_sync)
            _activeOperation = null;
        _gate.Release();
        updates.Publish();
    }

    // Called by the reservation owner. Native operations cannot be interrupted after they begin.
    private async Task ConnectAsync(CancellationToken cancellation = default)
    {
        if (_peripheral is { IsConnected: true })
            return;
        if (_peripheral != null)
            await DisconnectAsync();
        int thisSession;
        lock (_sync)
        {
            thisSession = ++_session;
            _deviceState = new();
            _subscribed = false;
            SignalState();
        }
        Change("scanning");
        Peripheral? selected = null;
        IReadOnlyList<Adapter> adapters = [];
        try
        {
            adapters = Adapter.GetAdapters();
            if (adapters.Count == 0)
                throw new InvalidOperationException("No Bluetooth adapter is available");
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
                        if (e.Peripheral.Identifier == "EM-MIDI-IDF" && found.TrySetResult(e.Peripheral))
                            return;
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
                    if (scanning)
                        adapter.ScanStop();
                    adapter.ScanFound -= OnFound;
                    adapter.ScanUpdated -= OnFound;
                }
                if (selected != null)
                    break;
            }
            if (selected == null)
                throw new InvalidOperationException("Surrklank ESP32 was not found");
            cancellation.ThrowIfCancellationRequested();
            Change("connecting");
            var current = selected;
            current.Disconnected += (_, _) => LinkLost(current, thisSession);
            lock (_sync)
                _peripheral = current;
            selected = null; // Ownership moves to this service, including setup-failure cleanup.
            await current.ConnectAsync(cancellation);
            cancellation.ThrowIfCancellationRequested();
            if (!current.IsConnected)
                throw new InvalidOperationException("BLE connection was not established");
            var information = await ReadInfoAsync(cancellation);
            // Old images remain readable for the first OTA migration. New images must subscribe.
            if (information.TryGetProperty("events_version", out var version) && version.GetInt32() == 1)
            {
                await current.NotifyAsync(Service, Info, bytes => ReceiveState(current, thisSession, bytes), cancellation);
                lock (_sync)
                    _subscribed = true;
                // Close the read/subscribe gap; sequence numbers prevent stale reads overwriting events.
                information = await ReadInfoAsync(cancellation);
            }
            lock (_sync)
            {
                if (_peripheral != current || _session != thisSession || !current.IsConnected)
                    throw new InvalidOperationException("BLE disconnected while reading device information");
                _device = information;
                _deviceState.Read(information);
                SignalState();
                // SimpleBLE's macOS implementation reports payload length, not ATT MTU.
                _mtu = current.Mtu + (OperatingSystem.IsMacOS() ? 3 : 0);
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
        lock (_sync)
        {
            if (_peripheral == client && _session == clientSession && _state is "connected" or "connecting")
            {
                _subscribed = false;
                Change("disconnected", "BLE connection lost");
                SignalState();
            }
        }
    }

    private async Task DisconnectAsync()
    {
        Peripheral? old;
        lock (_sync)
        {
            old = _peripheral;
            _peripheral = null;
            _mtu = null;
            _subscribed = false;
            _deviceState = new();
            SignalState();
        }
        if (old != null)
        {
            try
            {
                if (old.IsConnected)
                    await old.DisconnectAsync();
            }
            catch (Exception ex) { logger.LogWarning(ex, "BLE disconnect failed"); }
            finally { old.Dispose(); }
        }
        Change("disconnected");
    }

    private async Task<JsonElement> ReadInfoAsync(CancellationToken cancellation = default)
    {
        bool notifications;
        lock (_sync)
            notifications = _subscribed;
        // SimpleBLE/macOS Read on a notifying characteristic waits for its next event.
        // FFF1 INFO is a request/response snapshot while FFF2 remains subscribed.
        if (notifications)
            return JsonSerializer.Deserialize<JsonElement>(await SendCommandAsync("INFO", cancellation));
        return JsonSerializer.Deserialize<JsonElement>(await Current.ReadAsync(Service, Info, cancellation));
    }

    private async Task<string> SendCommandAsync(string text, CancellationToken cancellation = default)
    {
        var client = Current;
        await client.WriteRequestAsync(Service, Command, Encoding.ASCII.GetBytes(text), cancellation);
        return Encoding.ASCII.GetString(await client.ReadAsync(Service, Command, cancellation));
    }

    private async Task PingAsync(CancellationToken cancellation = default)
    {
        var token = RandomNumberGenerator.GetInt32(1_000_000_000).ToString();
        var watch = Stopwatch.StartNew();
        try
        {
            var reply = await SendCommandAsync("PING " + token, cancellation);
            if (reply != "PONG " + token)
                throw new InvalidOperationException("Mismatched PONG");
            lock (_sync)
            {
                _error = null;
                _lastPing = new PingResultDto(true, Math.Round(watch.Elapsed.TotalMilliseconds, 1), DateTimeOffset.UtcNow, reply);
            }
        }
        catch (Exception ex)
        {
            lock (_sync)
                _lastPing = new PingResultDto(false, Error: ex.Message);
            updates.Publish();
            throw;
        }
        updates.Publish();
    }

    public void SetDevice(JsonElement information)
    {
        lock (_sync)
        {
            _device = information;
            _deviceState.Read(information);
            SignalState();
        }
        updates.Publish();
    }

    private void ReceiveState(Peripheral client, int clientSession, byte[] bytes)
    {
        lock (_sync)
        {
            if (_peripheral != client || _session != clientSession || _state is not ("connecting" or "connected"))
                return;
            if (!_deviceState.Receive(bytes))
                return;
            SignalState();
            if (_deviceState.NeedsRefresh)
                _refreshRequests.Writer.TryWrite(0);
        }
        updates.Publish();
    }

    private async Task WaitForFlashReadyAsync(CancellationToken cancellation)
    {
        while (true)
        {
            Task changed;
            lock (_sync)
            {
                if (_state != "connected")
                    throw new InvalidOperationException("BLE disconnected while waiting for flash");
                var firmware = _deviceState.Firmware;
                if (firmware?.Error is not (null or 0))
                    throw new InvalidOperationException($"ESP flash write failed: {firmware.Error}");
                if (firmware?.Stage == "ready")
                    return;
                changed = _stateChanged.Task;
            }
            await changed.WaitAsync(cancellation);
        }
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        _observer = ObserveAsync(_stopping.Token);
        _reconciliation = ReconcileAsync(_stopping.Token);
        if (Environment.GetEnvironmentVariable("BLE_AUTO_SCAN") != "false")
            _discovery = DiscoverAsync(_stopping.Token);
        return Task.CompletedTask;
    }

    private void SetDiscovery(string value)
    {
        lock (_sync)
        {
            if (_discoveryState == value)
                return;
            _discoveryState = value;
            // Discovery establishes that this service has no active connection.
            // Finding an advertisement does not mean the ESP32 is connected.
            if (_state == "unknown" && value is "found" or "not_found")
                Change("disconnected");
        }
        updates.Publish();
    }

    // Gap reconciliation is event-triggered. It waits for maintenance ownership to end.
    private async Task ReconcileAsync(CancellationToken cancellation)
    {
        try
        {
            await foreach (var _ in _refreshRequests.Reader.ReadAllAsync(cancellation))
            {
                using var operation = await TryReserveAsync("state_refresh", Timeout.InfiniteTimeSpan, cancellation);
                lock (_sync)
                {
                    if (_state != "connected" || !_deviceState.NeedsRefresh)
                        continue;
                }
                try
                {
                    SetDevice(await operation!.ReadInfoAsync(cancellation));
                }
                catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { throw; }
                catch (Exception ex)
                {
                    logger.LogWarning(ex, "Could not reconcile a device-state sequence gap");
                    await operation!.DisconnectAsync();
                }
            }
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
    }

    // Keep existing short scans and retry timing; all native work uses a reservation.
    private async Task DiscoverAsync(CancellationToken cancellation)
    {
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                bool connected;
                lock (_sync)
                    connected = _state == "connected";
                if (connected)
                    SetDiscovery("connected");
                else if (!_autoConnect)
                    SetDiscovery("paused");
                else
                {
                    using var operation = await TryReserveAsync("discovery", TimeSpan.Zero, cancellation);
                    if (operation == null)
                        SetDiscovery("paused");
                    else
                    {
                        try
                        {
                            var adapters = Adapter.GetAdapters();
                            try
                            {
                                if (adapters.Count == 0)
                                    SetDiscovery("unavailable");
                                else
                                {
                                    bool found = false;
                                    foreach (var adapter in adapters)
                                    {
                                        await adapter.ScanForAsync(TimeSpan.FromSeconds(1), cancellation);
                                        var devices = adapter.ScanGetResults();
                                        try
                                        {
                                            found |= devices.Any(device => device.Identifier == "EM-MIDI-IDF");
                                        }
                                        finally { foreach (var device in devices) device.Dispose(); }
                                        if (found)
                                            break;
                                    }
                                    if (found)
                                    {
                                        SetDiscovery("connecting");
                                        await operation.ConnectAsync(cancellation);
                                        SetDiscovery("connected");
                                    }
                                    else
                                        SetDiscovery("not_found");
                                }
                            }
                            finally { foreach (var adapter in adapters) adapter.Dispose(); }
                        }
                        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { throw; }
                        catch (Exception ex) { logger.LogWarning(ex, "BLE discovery failed"); SetDiscovery("unavailable"); }
                    }
                }
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
                Peripheral? client;
                int currentSession;
                string currentState;
                lock (_sync)
                {
                    client = _peripheral;
                    currentSession = _session;
                    currentState = _state;
                }
                if (client != null && currentState == "connected")
                {
                    try
                    {
                        if (!client.IsConnected)
                            LinkLost(client, currentSession);
                    }
                    catch (ObjectDisposedException) { }
                    catch (Exception ex) { logger.LogDebug(ex, "Could not inspect BLE link state"); }
                }
            }
        }
        catch (OperationCanceledException) { }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        _stopping.Cancel();
        if (_observer != null)
            await _observer;
        if (_discovery != null)
            await _discovery;
        if (_reconciliation != null)
            await _reconciliation;
        using var operation = await ReserveAsync("disconnect", cancellationToken);
        await operation.DisconnectAsync();
    }
}
