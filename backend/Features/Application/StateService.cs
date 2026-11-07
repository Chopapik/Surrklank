using System.Text.Json;
using System.Threading.Channels;

namespace Surrklank.Features.Application;

// Subscribers receive snapshots, not a history of every intermediate update.
public sealed class StateService
{
    private readonly object _sync = new();
    private readonly HashSet<Channel<byte>> _listeners = [];
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
        lock (_sync)
            _listeners.Add(channel);
        channel.Writer.TryWrite(0);
        return channel;
    }

    public void Unsubscribe(Channel<byte> channel)
    {
        lock (_sync)
            _listeners.Remove(channel);
        channel.Writer.TryComplete();
    }

    public void Publish()
    {
        lock (_sync)
            foreach (var channel in _listeners)
                channel.Writer.TryWrite(0);
    }
}
