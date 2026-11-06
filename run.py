"""Compatibility launcher for the native ASP.NET application."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
try:
    raise SystemExit(subprocess.call(
        ["dotnet", "run", "--project", str(root / "backend" / "ElectromechanicalMidi.csproj"),
         "--no-launch-profile", *sys.argv[1:]],
        cwd=root,
    ))
except KeyboardInterrupt:
    raise SystemExit(130)
