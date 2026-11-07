namespace Surrklank.Features.Firmware;

internal sealed class FirmwareOutcomeUnknownException(string message, Exception? inner = null)
    : Exception(message, inner);
