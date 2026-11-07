"""Compatibility launcher for the native ASP.NET application."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
if not (root / "frontend" / "dist" / "index.html").is_file():
    raise SystemExit(
        "Frontend build missing. Run: npm --prefix frontend ci, "
        "then npm --prefix frontend run build."
    )

try:
    raise SystemExit(subprocess.call(
        ["dotnet", "run", "--project", str(root / "backend" / "Surrklank.csproj"),
         "--no-launch-profile", *sys.argv[1:]],
        cwd=root,
    ))
except KeyboardInterrupt:
    raise SystemExit(130)
