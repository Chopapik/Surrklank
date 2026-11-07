namespace Surrklank.Shared.Http;

public static class LocalOrigin
{
    public static bool IsAllowed(HttpRequest request) =>
        !request.Headers.TryGetValue("Origin", out var origin) ||
        origin.Count == 1 && origin[0] == $"{request.Scheme}://{request.Host}";
}
