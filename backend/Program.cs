using Surrklank.Services;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(new WebApplicationOptions
{
    Args = args,
    WebRootPath = "../frontend/dist",
});
builder.WebHost.UseUrls(Environment.GetEnvironmentVariable("ASPNETCORE_URLS") ?? "http://127.0.0.1:5173");
builder.Services.AddControllers().AddJsonOptions(options =>
    options.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower);
builder.Services.AddSingleton<StateService>();
builder.Services.AddSingleton<BleConnectionService>();
builder.Services.AddSingleton<BleOtaService>();
builder.Services.AddSingleton<AtxService>();
builder.Services.AddSingleton<FirmwareService>();
builder.Services.AddHostedService(provider => provider.GetRequiredService<BleConnectionService>());
builder.Services.AddHostedService(provider => provider.GetRequiredService<FirmwareService>());
var app = builder.Build();
app.UseWebSockets();
app.UseDefaultFiles();
app.UseStaticFiles();
app.MapControllers();
app.Run();
