#!/bin/sh
# Rebuild the FDD module: schematic -> ERC -> netlist check -> placement -> autoroute -> DRC.
# Usage: hardware/tools/build_fdd_module.sh [work_dir]
# Needs KiCad 10, Freerouting 2.5.0 (jar) and Java 25 (see hardware/README.md).
set -eu
HW=$(cd "$(dirname "$0")/.." && pwd)
WORK=${1:-$(mktemp -d)}
KIBIN=/Applications/KiCad/KiCad.app/Contents/MacOS
KIPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
FREEROUTING=${FREEROUTING:-$HOME/.local/share/freerouting/bin/freerouting-2.5.0.jar}
JAVA=${JAVA:-/opt/homebrew/opt/openjdk@25/bin/java}
SCH=$HW/fdd-module/surrklank-fdd-module.kicad_sch
PCB=$HW/fdd-module/surrklank-fdd-module.kicad_pcb
quiet() { grep -vE "Fontconfig|wxApp|memory leak" || true; }

python3 -I "$HW/tools/gen_fdd_module.py" "$SCH"
"$KIBIN/kicad-cli" sch erc --exit-code-violations -o "$WORK/erc.rpt" "$SCH" 2>&1 | quiet
"$KIBIN/kicad-cli" sch export netlist --format kicadxml -o "$WORK/fdd.xml" "$SCH" 2>&1 | quiet
python3 -I "$HW/tools/check_fdd_module.py" "$WORK/fdd.xml" | tail -1
"$KIPY" "$HW/tools/gen_fdd_pcb.py" place "$WORK/fdd.xml" "$PCB" 2>&1 | quiet
"$KIPY" "$HW/tools/gen_fdd_pcb.py" dsn "$PCB" "$WORK/fdd.dsn" 2>&1 | quiet
# Headless, telemetry off, multi-threaded optimizer.
(cd "$WORK" && "$JAVA" -jar "$FREEROUTING" -de fdd.dsn -do fdd.ses --gui.enabled=false \
    --usage_and_diagnostic_data.disable_analytics=true --profile.allow_telemetry=false \
    --router.autorouter.max_passes=100 --router.automatic_neckdown=false -mt 9 > freerouting.log 2>&1)
grep -E "Auto-routing stage completed" "$WORK/freerouting.log" | sed 's/.*final score/final score/'
"$KIPY" "$HW/tools/gen_fdd_pcb.py" import "$PCB" "$WORK/fdd.ses" 2>&1 | quiet
"$KIBIN/kicad-cli" pcb drc --schematic-parity -o "$WORK/drc.rpt" "$PCB" 2>&1 | quiet
grep -E "^\*\* Found" "$WORK/drc.rpt"
echo "work files: $WORK"
