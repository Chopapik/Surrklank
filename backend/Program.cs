using System.Text.Json;
using Surrklank.Features.Application;
using Surrklank.Features.Atx;
using Surrklank.Features.Connection;
using Surrklank.Features.Firmware;
using Surrklank.Features.Firmware.Toolchain;
using Surrklank.Features.Firmware.Transport;

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
builder.Services.AddSingleton<IDeviceConnection>(provider => provider.GetRequiredService<BleConnectionService>());
builder.Services.AddSingleton<BleOtaService>();
builder.Services.AddSingleton<AtxService>();
builder.Services.AddSingleton<FirmwareJobState>();
builder.Services.AddSingleton<IFirmwareToolchain, PlatformIoToolchain>();
builder.Services.AddSingleton<FirmwareUpdateUseCase>();
builder.Services.AddSingleton<FirmwareService>();
builder.Services.AddSingleton<ApplicationStateService>();
builder.Services.AddHostedService(provider => provider.GetRequiredService<BleConnectionService>());
builder.Services.AddHostedService(provider => provider.GetRequiredService<FirmwareService>());
var app = builder.Build();
app.UseWebSockets();
app.UseDefaultFiles();
app.UseStaticFiles();
app.MapControllers();
app.Run();
