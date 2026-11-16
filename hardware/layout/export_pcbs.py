"""Export every Surrklank KiCad board to GLB for the Blender layout.

    python3 hardware/layout/export_pcbs.py [--light]

Writes hardware/layout/pcb/<board>.glb (ignored by Git). Boards without an
Edge.Cuts outline are skipped. The default export includes tracks, pads,
zones, silkscreen and soldermask; --light exports only the board body and
component models (far fewer triangles for the full stack view).
The kicad-cli path comes from $KICAD_CLI, then PATH, then the macOS app.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARDWARE = HERE.parent
OUT = HERE / "pcb"
MAC_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def find_cli():
    for cand in (os.environ.get("KICAD_CLI"), shutil.which("kicad-cli"), MAC_CLI):
        if cand and Path(cand).is_file():
            return cand
    sys.exit("kicad-cli not found; set KICAD_CLI")


def boards():
    for pcb in sorted(HARDWARE.glob("*/*.kicad_pcb")):
        if "Edge.Cuts" in pcb.read_text(errors="ignore"):
            yield pcb
        else:
            print(f"skip {pcb.relative_to(HARDWARE)}: no board outline")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--light", action="store_true", help="board body and components only")
    args = ap.parse_args()
    cli = find_cli()
    OUT.mkdir(exist_ok=True)
    extra = [] if args.light else ["--include-tracks", "--include-pads", "--include-zones",
                                   "--include-silkscreen", "--include-soldermask"]
    failed = 0
    for pcb in boards():
        out = OUT / f"{pcb.stem}.glb"
        cmd = [cli, "pcb", "export", "glb", "--subst-models", *extra, "-o", str(out), str(pcb)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and out.is_file():
            print(f"ok   {out.relative_to(HARDWARE)} ({out.stat().st_size // 1024} KiB)")
        else:
            failed += 1
            print(f"FAIL {pcb.relative_to(HARDWARE)}\n{res.stderr.strip()[-2000:]}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
