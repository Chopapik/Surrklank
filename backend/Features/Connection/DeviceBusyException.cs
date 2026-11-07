namespace Surrklank.Features.Connection;

public sealed class DeviceBusyException(string? operation)
    : InvalidOperationException(operation == "firmware_update"
        ? "Cannot perform this operation while firmware update is in progress"
        : $"Cannot perform this operation: device is busy with {operation ?? "another operation"}")
{
    public string? Operation { get; } = operation;
}
