#!/bin/sh
# Rebuild one module board: schematic -> ERC -> netlist check -> placement ->
# autoroute -> zone fill -> DRC.
# Usage: hardware/tools/build_module.sh fdd|lsm-hdd|mainboard|panel [work_dir]
# Needs KiCad 10, Freerouting 2.5.0 (jar) and Java 25 (see hardware/README.md).
set -eu
# A failing step must stop the build even though its output is filtered.
set -o pipefail
BOARD=$1
case $BOARD in
    fdd) NAME=fdd; DIR=fdd-module; GEN=gen_fdd_module.py; CHECK=check_fdd_module.py ;;
    lsm-hdd) NAME=lsm_hdd; DIR=lsm-hdd-module; GEN=gen_lsm_hdd_module.py; CHECK=check_lsm_hdd_module.py ;;
    mainboard) NAME=mainboard; DIR=mainboard; GEN=gen_mainboard.py; CHECK=check_mainboard.py ;;
    panel) NAME=panel; DIR=panel; GEN=gen_panel.py; CHECK=check_panel.py ;;
    *) echo "unknown board: $BOARD" >&2; exit 2 ;;
esac
HW=$(cd "$(dirname "$0")/.." && pwd)
WORK=${2:-$(mktemp -d)}
KIBIN=/Applications/KiCad/KiCad.app/Contents/MacOS
KIPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
FREEROUTING=${FREEROUTING:-$HOME/.local/share/freerouting/bin/freerouting-2.5.0.jar}
JAVA=${JAVA:-/opt/homebrew/opt/openjdk@25/bin/java}
SCH=$HW/$DIR/surrklank-$DIR.kicad_sch
PCB=$HW/$DIR/surrklank-$DIR.kicad_pcb
PCBGEN="$HW/tools/gen_module_pcb.py"
quiet() { grep -vE "Fontconfig|wxApp|memory leak|stdpbase" || true; }

python3 -I "$HW/tools/$GEN" "$SCH"
"$KIBIN/kicad-cli" sch erc --exit-code-violations -o "$WORK/erc.rpt" "$SCH" 2>&1 | quiet
"$KIBIN/kicad-cli" sch export netlist --format kicadxml -o "$WORK/$NAME.xml" "$SCH" 2>&1 | quiet
python3 -I "$HW/tools/$CHECK" "$WORK/$NAME.xml" | tail -1
"$KIPY" "$PCBGEN" "$BOARD" place "$WORK/$NAME.xml" "$PCB" 2>&1 | quiet
"$KIPY" "$PCBGEN" "$BOARD" dsn "$PCB" "$WORK/$NAME.dsn" 2>&1 | quiet
# Headless, telemetry off, multi-threaded optimizer.
(cd "$WORK" && "$JAVA" -jar "$FREEROUTING" -de "$NAME.dsn" -do "$NAME.ses" --gui.enabled=false \
    --usage_and_diagnostic_data.disable_analytics=true --profile.allow_telemetry=false \
    --router.autorouter.max_passes=100 --router.automatic_neckdown=false -mt 9 > freerouting.log 2>&1)
grep -E "Auto-routing stage completed" "$WORK/freerouting.log" | sed 's/.*final score/final score/'
"$KIPY" "$PCBGEN" "$BOARD" import "$PCB" "$WORK/$NAME.ses" 2>&1 | quiet
"$KIBIN/kicad-cli" pcb drc --schematic-parity --severity-all -o "$WORK/drc.rpt" "$PCB" 2>&1 | quiet
grep -E "^\*\* Found" "$WORK/drc.rpt"
echo "work files: $WORK"
