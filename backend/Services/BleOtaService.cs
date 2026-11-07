using System.Buffers.Binary;
using System.Threading.Channels;
using SimpleSharpBLE;

namespace Surrklank.Services;

// The OTA sender only needs these BLE operations; this also allows it to be
// checked offline without connecting to a physical ESP32.
public interface IOtaConnection
{
    bool IsConnected { get; }
    int ReportedMtu { get; }
    bool HasOtaFirmware { get; }
    Task SubscribeAsync(string service, string characteristic, Action<byte[]> callback, CancellationToken cancellation);
    Task UnsubscribeAsync(string service, string characteristic);
    Task WriteRequestAsync(string service, string characteristic, byte[] data, CancellationToken cancellation);
    Task WriteCommandAsync(string service, string characteristic, byte[] data, CancellationToken cancellation);
}

// Sender for Espressif's ble_ota_raw profile. This does not define a new protocol.
public sealed class BleOtaService
{
    private const string Service = "00008018-0000-1000-8000-00805f9b34fb";
    private const string Firmware = "00008020-0000-1000-8000-00805f9b34fb";
    private const string Command = "00008022-0000-1000-8000-00805f9b34fb";

    public static ushort Crc(ReadOnlySpan<byte> data)
    {
        ushort crc = 0;
        foreach (byte value in data)
        {
            crc ^= (ushort)(value << 8);
            for (int bit = 0; bit < 8; bit++)
                crc = (ushort)((crc & 0x8000) != 0 ? (crc << 1) ^ 0x1021 : crc << 1);
        }
        return crc;
    }

    public static byte[] CommandPacket(ushort code, uint size = 0)
    {
        byte[] packet = new byte[20];
        BinaryPrimitives.WriteUInt16LittleEndian(packet, code);
        BinaryPrimitives.WriteUInt32LittleEndian(packet.AsSpan(2), size);
        BinaryPrimitives.WriteUInt16LittleEndian(packet.AsSpan(18), Crc(packet.AsSpan(0, 18)));
        return packet;
    }

    public static IReadOnlyList<byte[]> SectorPackets(ushort index, byte[] block, int capacity)
    {
        if (block.Length is 0 or > 4096 || capacity < 20)
            throw new ArgumentException("Invalid sector or ATT capacity");
        var packets = new List<byte[]>();
        int position = 0;
        int sequence = 0;
        while (block.Length - position > capacity - 5)
        {
            int length = Math.Min(capacity - 3, block.Length - position);
            byte[] packet = new byte[length + 3];
            BinaryPrimitives.WriteUInt16LittleEndian(packet, index);
            packet[2] = (byte)sequence;
            block.AsSpan(position, length).CopyTo(packet.AsSpan(3));
            packets.Add(packet);
            position += length;
            if (++sequence >= 255) throw new ArgumentException("Too many packets in sector");
        }
        byte[] last = new byte[block.Length - position + 5];
        BinaryPrimitives.WriteUInt16LittleEndian(last, index);
        last[2] = 255;
        block.AsSpan(position).CopyTo(last.AsSpan(3));
        BinaryPrimitives.WriteUInt16LittleEndian(last.AsSpan(last.Length - 2), Crc(block));
        packets.Add(last);
        return packets;
    }

    public Task TransferAsync(Peripheral client, byte[] image,
        Action<double, object> progress, CancellationToken cancellation) =>
        TransferAsync(new NativeOtaConnection(client), image, progress, cancellation);

    public async Task TransferAsync(IOtaConnection client, byte[] image,
        Action<double, object> progress, CancellationToken cancellation)
    {
        if (!client.HasOtaFirmware)
            throw new InvalidOperationException("Official BLE OTA service is unavailable");
        // In SimpleBLE 1.2.0 on macOS, Mtu is CoreBluetooth's maximum
        // write-without-response payload, not the ATT MTU including its header.
        // Use the standard minimum payload on other, as-yet-unverified platforms.
        int reported = client.ReportedMtu;
        int capacity = OperatingSystem.IsMacOS() ? Math.Min(495, reported) : 20;
        int mtu = OperatingSystem.IsMacOS() ? reported + 3 : reported;
        if (reported < 20 || capacity < 20) throw new InvalidOperationException("Invalid ATT payload capacity");
        var commands = Channel.CreateBounded<byte[]>(8);
        var receipts = Channel.CreateBounded<byte[]>(64);
        var streamError = new TaskCompletionSource<Exception>(TaskCreationOptions.RunContinuationsAsynchronously);
        void Receive(Channel<byte[]> queue, byte[] frame)
        {
            if (frame.Length != 20 || Crc(frame.AsSpan(0, 18)) != BinaryPrimitives.ReadUInt16LittleEndian(frame.AsSpan(18)))
                streamError.TrySetResult(new InvalidOperationException("Invalid official OTA acknowledgement CRC/length"));
            else if (!queue.Writer.TryWrite(frame))
                streamError.TrySetResult(new InvalidOperationException("OTA receipt queue overflow"));
        }
        async Task<byte[]> Receipt(Channel<byte[]> queue, TimeSpan timeout)
        {
            using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            timeoutSource.CancelAfter(timeout);
            if (streamError.Task.IsCompleted) throw await streamError.Task;
            var read = queue.Reader.ReadAsync(timeoutSource.Token).AsTask();
            var completed = await Task.WhenAny(read, streamError.Task);
            if (completed == streamError.Task) { timeoutSource.Cancel(); throw await streamError.Task; }
            try
            {
                var frame = await read;
                if (streamError.Task.IsCompleted) throw await streamError.Task;
                return frame;
            }
            catch (OperationCanceledException) when (!cancellation.IsCancellationRequested)
            { throw new TimeoutException("Timed out waiting for an OTA acknowledgement"); }
        }
        async Task<byte[]> Control(ushort code, uint size = 0)
        {
            await client.WriteRequestAsync(Service, Command, CommandPacket(code, size), cancellation);
            byte[] reply = await Receipt(commands, TimeSpan.FromSeconds(30));
            var ack = BinaryPrimitives.ReadUInt16LittleEndian(reply);
            var command = BinaryPrimitives.ReadUInt16LittleEndian(reply.AsSpan(2));
            var status = BinaryPrimitives.ReadUInt16LittleEndian(reply.AsSpan(4));
            if (ack != 3 || command != code || status != 0)
                throw new InvalidOperationException($"ESP OTA command rejected: {command}/{status}");
            return reply;
        }

        bool commandSubscribed = false, firmwareSubscribed = false;
        try
        {
            await client.SubscribeAsync(Service, Command, data => Receive(commands, data), cancellation);
            commandSubscribed = true;
            await client.SubscribeAsync(Service, Firmware, data => Receive(receipts, data), cancellation);
            firmwareSubscribed = true;
            var ack = await Control(1, checked((uint)image.Length));
            int window = Math.Max(1, Math.Min(capacity >= 495 ? 3 : 1, (int)ack[6]));
            int sectors = (image.Length + 4095) / 4096;
            if (sectors > ushort.MaxValue + 1) throw new InvalidOperationException("Firmware image exceeds OTA sector limit");
            int acknowledged = 0, duplicates = 0;
            for (int first = 0; first < sectors; first += window)
            {
                var pending = new HashSet<int>(Enumerable.Range(first, Math.Min(window, sectors - first)));
                foreach (int index in pending.Order())
                {
                    byte[] block = image.AsSpan(index * 4096, Math.Min(4096, image.Length - index * 4096)).ToArray();
                    foreach (var packet in SectorPackets((ushort)index, block, capacity))
                    {
                        cancellation.ThrowIfCancellationRequested();
                        if (streamError.Task.IsCompleted) throw await streamError.Task;
                        await client.WriteCommandAsync(Service, Firmware, packet, cancellation);
                    }
                }
                using var groupTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                groupTimeout.CancelAfter(TimeSpan.FromSeconds(15));
                while (pending.Count > 0)
                {
                    // A single deadline covers the whole window, including duplicate receipts.
                    if (streamError.Task.IsCompleted) throw await streamError.Task;
                    var readTask = receipts.Reader.ReadAsync(groupTimeout.Token).AsTask();
                    var completed = await Task.WhenAny(readTask, streamError.Task);
                    if (completed == streamError.Task) throw await streamError.Task;
                    byte[] frame;
                    try { frame = await readTask; }
                    catch (OperationCanceledException) when (!cancellation.IsCancellationRequested)
                    { throw new TimeoutException("Timed out waiting for OTA sector receipts"); }
                    if (streamError.Task.IsCompleted) throw await streamError.Task;
                    int sector = BinaryPrimitives.ReadUInt16LittleEndian(frame);
                    int status = BinaryPrimitives.ReadUInt16LittleEndian(frame.AsSpan(2));
                    if (status != 0 || sector >= first + window || sector >= sectors)
                        throw new InvalidOperationException($"ESP OTA receipt {sector}/{status}; no replay");
                    if (!pending.Remove(sector)) { duplicates++; continue; }
                    acknowledged += Math.Min(4096, image.Length - sector * 4096);
                    progress(Math.Round(100.0 * acknowledged / image.Length, 1),
                        new { mtu, packet_bytes = capacity, sector_window = window, duplicate_receipts = duplicates });
                }
            }
            await Control(2);
        }
        finally
        {
            // Never replay an uncertain transfer. The caller disconnects after failure.
            if (client.IsConnected)
            {
                if (firmwareSubscribed) { try { await client.UnsubscribeAsync(Service, Firmware); } catch { } }
                if (commandSubscribed) { try { await client.UnsubscribeAsync(Service, Command); } catch { } }
            }
        }
    }
    private sealed class NativeOtaConnection(Peripheral client) : IOtaConnection
    {
        public bool IsConnected => client.IsConnected;
        public int ReportedMtu => client.Mtu;
        public bool HasOtaFirmware => client.Services
            .FirstOrDefault(s => s.Uuid.Equals(Service, StringComparison.OrdinalIgnoreCase))?
            .Characteristics.FirstOrDefault(c => c.Uuid.Equals(Firmware, StringComparison.OrdinalIgnoreCase))
            is { CanWriteCommand: true, CanNotify: true };
        public Task SubscribeAsync(string service, string characteristic, Action<byte[]> callback, CancellationToken cancellation) =>
            client.NotifyAsync(service, characteristic, callback, cancellation);
        public Task UnsubscribeAsync(string service, string characteristic) => client.UnsubscribeAsync(service, characteristic);
        public Task WriteRequestAsync(string service, string characteristic, byte[] data, CancellationToken cancellation) =>
            client.WriteRequestAsync(service, characteristic, data, cancellation);
        public Task WriteCommandAsync(string service, string characteristic, byte[] data, CancellationToken cancellation) =>
            client.WriteCommandAsync(service, characteristic, data, cancellation);
    }
}
