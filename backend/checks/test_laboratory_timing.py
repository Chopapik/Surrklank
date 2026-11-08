"""Exercise production timing service against an offline native-operation substitute."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class TimingServiceTests(unittest.TestCase):
    def test_replay_gap_restart_and_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Check.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Compile Include="{ROOT}/Features/Laboratory/LaboratoryService.cs"/><Compile Include="{ROOT}/Features/Laboratory/DTOs/LaboratoryDto.cs"/></ItemGroup></Project>''')
            (root / 'Program.cs').write_text(r'''using System.Text.Json;
using Surrklank.Features.Laboratory;
using Surrklank.Features.Application;
using Surrklank.Features.Connection;
static void Check(bool ok) { if (!ok) throw new Exception("Timing check failed"); }
var connection = new FakeConnection();
var updates = new StateService();
var service = new LaboratoryService(connection, new LaboratoryState(), new PlayLaboratoryBatchUseCase(), updates);
connection.Operation.Replies.Enqueue("{\"timing_version\":1,\"esp_boot_id\":7}");
connection.Operation.Replies.Enqueue("{\"esp_boot_id\":7,\"latest\":3,\"event\":{\"event_sequence\":3,\"esp_event_time_us\":42}}");
var result = JsonSerializer.SerializeToElement(await service.ReadTimingAsync(0, default));
Check(result.GetProperty("gap").GetBoolean());
Check(result.GetProperty("events")[0].GetProperty("esp_event_time_us").GetInt64()==42);
Check(connection.Operation.Disposed && updates.Published);
connection.Operation.Disposed=false;
connection.Operation.Replies.Enqueue("{\"timing_version\":1,\"esp_boot_id\":7}");
connection.Operation.Replies.Enqueue("{\"esp_boot_id\":8,\"latest\":0,\"event\":null}");
try { await service.ReadTimingAsync(3, default); throw new Exception("Restart accepted"); }
catch (InvalidOperationException) { Check(connection.Operation.Disposed); }
namespace Surrklank.Features.Application {
 public class StateService { public bool Published; public void Publish() => Published=true; }
}
namespace Surrklank.Features.Connection {
 public record Snapshot(bool Connected=true, bool Subscribed=true);
 public interface IDeviceConnection { Snapshot Snapshot(); Task<FakeOperation> ReserveAsync(string reason, CancellationToken token); }
 public interface IDeviceOperation { Task<string> SendCommandAsync(string command, CancellationToken token); }
 public class FakeConnection : IDeviceConnection {
  public FakeOperation Operation=new(); public Snapshot Snapshot()=>new();
  public Task<FakeOperation> ReserveAsync(string reason, CancellationToken token)=>Task.FromResult(Operation);
 }
 public class FakeOperation : IDeviceOperation, IDisposable {
  public Queue<string> Replies=new(); public bool Disposed;
  public Task<string> SendCommandAsync(string command, CancellationToken token)=>Task.FromResult(Replies.Dequeue());
  public Task RefreshLaboratoryAsync(CancellationToken token)=>Task.CompletedTask;
  public void Dispose()=>Disposed=true;
 }
}
namespace Surrklank.Features.Laboratory {
 public class LaboratoryState { public LaboratorySnapshot Snapshot()=>new(); public void MarkUncertain(){} }
 public record LaboratorySnapshot(bool Supported=true);
 public class PlayLaboratoryBatchUseCase {
  public Task<uint> ExecuteAsync(Surrklank.Features.Laboratory.DTOs.LaboratoryPlayRequestDto request, CancellationToken token)=>Task.FromResult(1u);
 }
}
''')
            subprocess.run(['dotnet', 'run', '--project', str(root / 'Check.csproj')], check=True, timeout=90)
if __name__ == '__main__': unittest.main()
