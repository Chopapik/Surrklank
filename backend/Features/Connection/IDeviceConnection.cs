using System.Text.Json;
using Surrklank.Features.Connection.DTOs;

namespace Surrklank.Features.Connection;

public interface IDeviceConnection
{
    ConnectionDto Snapshot();
    Task<IDeviceOperation> ReserveAsync(string reason, CancellationToken cancellation = default);
    void SetDevice(JsonElement information);
}
