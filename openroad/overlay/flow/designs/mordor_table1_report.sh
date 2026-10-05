#!/usr/bin/env bash
#
# Render the OpenROAD measurements and their scaled paper values.
set -uo pipefail
ORIGPWD="$PWD"
FLOW="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$FLOW"

OUTFILE=""
while [ $# -gt 0 ]; do case "$1" in
  -o) OUTFILE="${2:?-o needs a file argument}"; shift 2 ;;
  *) echo "usage: $0 [-o FILE]"; exit 2 ;;
esac; done
[ -z "$OUTFILE" ] && OUTFILE="mordor_table1_report.txt"
case "$OUTFILE" in /*) ;; *) OUTFILE="$ORIGPWD/$OUTFILE" ;; esac

MC="${MC:-64}"
PROQS="${PROQS:-32 48 64 78}"
HEADP=32
WORKDIR="${WORKDIR:-/tmp/mordor_table1}"; mkdir -p "$WORKDIR"
LIB="$FLOW/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib"
CLK=10.0    # the mordor_v9 SDC clock, ns

# ---- extractors over the analysis artifacts --------------------------------
SYN(){ echo "$FLOW/reports/nangate45/mordor_v9/$1/synth_stat.txt"; }
RPT(){ echo "$FLOW/logs/nangate45/mordor_v9/$1/6_report.log"; }
camv(){ [ "$1" = "$HEADP" ] && echo cam_$MC || echo cam_m${MC}_p$1; }
garea(){ grep -E "Chip area for module" "$(SYN $1)" 2>/dev/null | grep -oE "[0-9.]+$"; }
leak() { grep -E "^Total " "$(RPT $1)" 2>/dev/null | tail -1 | awk '{print $4}'; }       # W
dyn()  { grep -E "^Total " "$(RPT $1)" 2>/dev/null | tail -1 | awk '{print ($2+$3)}'; }  # W
lat()  { # synthesized per-cycle scheduling-path delay, reg -> ready_o, ns (needs `sta`)
  local D="$FLOW/results/nangate45/mordor_v9/$1"
  [ -f "$D/6_final.v" ] || { echo ""; return; }
  cat > "$WORKDIR/lat_$1.tcl" <<EOF
read_liberty $LIB
read_verilog $D/6_final.v
link_design mordor_v9
read_sdc $D/6_final.sdc
report_checks -path_delay max -from [all_registers] -to [get_pins {*ready_o*/D}] -fields {} -format summary -group_count 1
EOF
  local s=$(sta -no_init -exit "$WORKDIR/lat_$1.tcl" 2>/dev/null | grep -iE "ready_o.*/D" | head -1 | awk '{print $NF}')
  awk -v c="$CLK" -v s="$s" 'BEGIN{if(s=="")print"";else printf "%.2f", c-s}'
}
# ---- preflight: all inputs must exist before we start writing the report ----
bA=$(garea base_$MC); bL=$(leak base_$MC); bD=$(dyn base_$MC)
[ -n "$bA" ] || { echo "ERROR: no baseline artifacts (reports/nangate45/mordor_v9/base_$MC)."; echo "       Run designs/mordor_table1_analyze.sh first (or designs/mordor_table1.sh)."; exit 1; }

# ---- render ----------------------------------------------------------------
{
  echo "MORDOR hardware overhead (MC=$MC, PROQ entries {$PROQS})"
  RAW1="$WORKDIR/_paper.txt"; : > "$RAW1"
  for P in $PROQS; do
    v=$(camv $P)
    cA=$(garea "$v"); cL=$(leak "$v"); cD=$(dyn "$v"); lt=$(lat "$v")
    awk -v P=$P -v bA="$bA" -v bL="$bL" -v bD="$bD" -v cA="$cA" -v cL="$cL" -v cD="$cD" -v lt="$lt" 'BEGIN{
      if(bA==""||cA==""){ printf "CAM-on-path %s - - - -\n", P; exit }
      ORs=(cL-bL)*1000; if(lt=="")lt="-";
      printf "CAM-on-path %d %.6f %.6f %.6f %s\n", \
             P, ORs, (cD-bD)*1000, cA-bA, lt }' >> "$RAW1"
  done
  python3 "$FLOW/designs/render_table1.py" "$RAW1" || { echo "[render failed -- raw rows:]"; cat "$RAW1"; }
} | tee "$OUTFILE"

echo
echo "report written to $OUTFILE"
