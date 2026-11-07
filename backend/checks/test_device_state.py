"""Compile the production FFF2 decoder in a temporary offline .NET harness."""
from pathlib import Path
import subprocess
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[1]


class DeviceStateTest(unittest.TestCase):
    def test_notifications_and_snapshot_races(self):
        with tempfile.TemporaryDirectory(prefix="surrklank-state-") as directory:
            root = Path(directory)
            (root / "Check.csproj").write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup>
<ItemGroup><Compile Include="{BACKEND / 'Features/Connection/DeviceState.cs'}" />
<Compile Include="{BACKEND / 'Features/Connection/DTOs/*.cs'}" /><Compile Include="{BACKEND / 'Features/Firmware/DTOs/DeviceFirmwareDto.cs'}" /></ItemGroup></Project>''')
            (root / "Program.cs").write_text('''using System.Buffers.Binary;
using System.Text.Json;
using Surrklank.Features.Connection;
static void Check(bool ok) { if (!ok) throw new Exception("State check failed"); }
static byte[] Atx(uint sequence, bool on) {
    byte[] bytes=[1,1,0,0,0,0,(byte)(on?1:0)];
    BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(2), sequence); return bytes;
}
static JsonElement Info(uint sequence, bool on) => JsonSerializer.SerializeToElement(new {
    atx_on=on, atx_sequence=sequence, firmware_sequence=sequence, ota="idle", received=0, error=0
});
var state=new DeviceState();
state.Read(Info(1,false));
Check(state.AtxOn==false);
Check(state.Receive(Atx(3,true)));
state.Read(Info(2,false)); // A late initial read must not revert a newer notification.
Check(state.AtxOn==true);
Check(!state.Receive(Atx(2,false)) && !state.Receive(Atx(3,false)));
Check(state.AtxOn==true);
Check(!state.Receive([]) && !state.Receive([9,1,0,0,0,0,0]));
Check(!state.Receive([1,1,0,0,0,0,2]));
byte[] firmware=new byte[15]; firmware[0]=1;firmware[1]=2;firmware[6]=2;
BinaryPrimitives.WriteUInt32LittleEndian(firmware.AsSpan(2),10);
BinaryPrimitives.WriteUInt32LittleEndian(firmware.AsSpan(7),550160);
Check(state.Receive(firmware));
Check(state.Firmware is { Stage:"ready", Received:550160, Error:0 });
state.Read(Info(2,false));
Check(state.Firmware?.Stage=="ready");
firmware[6]=3;
BinaryPrimitives.WriteUInt32LittleEndian(firmware.AsSpan(2),11);
BinaryPrimitives.WriteInt32LittleEndian(firmware.AsSpan(11),-1);
Check(state.Receive(firmware) && state.Firmware?.Error==-1);
var wrap=new DeviceState();wrap.Read(Info(uint.MaxValue,false));
Check(wrap.Receive(Atx(0,true)) && wrap.AtxOn==true);
var reconnect=new DeviceState();reconnect.Read(Info(0,false));
Check(reconnect.AtxOn==false); // A new BLE session must accept a new boot's sequence zero.
Console.WriteLine("FFF2 decoder: malformed frames, ordering, snapshot races, firmware and wrap checks passed");
''')
            subprocess.run(["dotnet", "run", "--project", str(root / "Check.csproj")], check=True)


if __name__ == "__main__":
    unittest.main()
