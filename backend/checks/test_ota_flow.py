"""Run production OTA sender with delayed-progress-sensitive offline transport."""
from pathlib import Path
import subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
class OtaFlowTests(unittest.TestCase):
 def test_one_sector_in_flight(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   (p/'Check.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup><ItemGroup><ProjectReference Include="{ROOT}/Surrklank.csproj"/></ItemGroup></Project>''')
   (p/'Program.cs').write_text(r'''using System.Buffers.Binary;
using Surrklank.Features.Firmware.Transport;
var fake=new Fake();
await new BleOtaService().TransferAsync(fake,new byte[70000],(progress,link)=>fake.Confirmed++,default);
if(fake.Confirmed!=18 || fake.Unsubscribed!=2) throw new Exception("Transfer incomplete");
class Fake : IOtaConnection {
 public bool IsConnected=>true; public int ReportedMtu=>495; public bool HasOtaFirmware=>true;
 public int Confirmed,Unsubscribed; private Dictionary<string,Action<byte[]>> callbacks=new();
 public Task SubscribeAsync(string s,string c,Action<byte[]> cb,CancellationToken ct){callbacks[c]=cb;return Task.CompletedTask;}
 public Task UnsubscribeAsync(string s,string c){Unsubscribed++;return Task.CompletedTask;}
 public Task WriteRequestAsync(string s,string c,byte[] data,CancellationToken ct){
  byte[] ack=new byte[20];BinaryPrimitives.WriteUInt16LittleEndian(ack,3);
  data.AsSpan(0,2).CopyTo(ack.AsSpan(2));ack[6]=3;
  BinaryPrimitives.WriteUInt16LittleEndian(ack.AsSpan(18),BleOtaService.Crc(ack.AsSpan(0,18)));
  callbacks[c](ack);return Task.CompletedTask;
 }
 public Task WriteCommandAsync(string s,string c,byte[] data,CancellationToken ct){
  int sector=BinaryPrimitives.ReadUInt16LittleEndian(data);
  if(sector!=Confirmed)throw new Exception("Next sector sent before previous confirmation");
  if(data[2]==255){byte[] ack=new byte[20];BinaryPrimitives.WriteUInt16LittleEndian(ack,(ushort)sector);
   BinaryPrimitives.WriteUInt16LittleEndian(ack.AsSpan(18),BleOtaService.Crc(ack.AsSpan(0,18)));callbacks[c](ack);}
  return Task.CompletedTask;
 }
}
''')
   subprocess.run(['dotnet','run','--project',str(p/'Check.csproj')],check=True,timeout=90)
if __name__=='__main__':unittest.main()
