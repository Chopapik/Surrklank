namespace Surrklank.Features.Firmware.Toolchain;

public sealed record FirmwareBuild(byte[] Image, string Identity, string Digest, double DurationSeconds);
