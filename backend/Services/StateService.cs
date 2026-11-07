using System.Text.Json;
using System.Threading.Channels;

namespace Surrklank.Services;

// Subscribers receive snapshots, not a history of every intermediate update.
public sealed class StateService
{
    private readonly object sync = new();
    private readonly HashSet<Channel<byte>> listeners = [];
    public static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    public Channel<byte> Subscribe()
    {
        var channel = Channel.CreateBounded<byte>(new BoundedChannelOptions(1)
        {
            FullMode = BoundedChannelFullMode.DropOldest,
            SingleReader = true
        });
        lock (sync) listeners.Add(channel);
        channel.Writer.TryWrite(0);
        return channel;
    }

    public void Unsubscribe(Channel<byte> channel)
    {
        lock (sync) listeners.Remove(channel);
        channel.Writer.TryComplete();
    }

    public void Publish()
    {
        lock (sync)
            foreach (var channel in listeners) channel.Writer.TryWrite(0);
    }
}
