#!/usr/bin/env bash
#
# MORDOR Table-1 REPORT -- renders the analysis results into a new file. No builds; seconds.
#
#   bash designs/mordor_table1_report.sh [--blocked-bit] [-o FILE]
#
# Writes the paper's Table 1 -- impl1 CAM-on-path overhead vs the baseline MC, in three
# views: 45nm raw, 14nm DeepScaleTool-scaled (= the printed Table 1 values), and
# 14nm x 6 channels -- to FILE (default ./mordor_table1_report.txt) and to stdout.
#
# --blocked-bit appends the same views for the OPTIONAL impl2 blocked-bit alternative
# (NOT in the paper). Needs the artifacts from mordor_table1_analyze.sh run with the
# same option; use mordor_table1.sh to run analysis + report in one go.
# Overridables (env): MC (64), PROQS ("32 48 64 78"), WORKDIR, SC_* / NCHAN scaling.
set -uo pipefail
ORIGPWD="$PWD"
FLOW="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$FLOW"

BLOCKED=0; OUTFILE=""
while [ $# -gt 0 ]; do case "$1" in
  --blocked-bit) BLOCKED=1; shift ;;
  -o) OUTFILE="${2:?-o needs a file argument}"; shift 2 ;;
  *) echo "usage: $0 [--blocked-bit] [-o FILE]"; exit 2 ;;
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
# CACTI extractors (impl2 install CAM only)
ccarea(){ grep -iE "(CAM|Data) array: Area .mm2." "$1" 2>/dev/null | grep -oE "[0-9.]+" | tail -1; }
ccleak(){ grep -iE "Total leakage power of a bank"      "$1" 2>/dev/null | head -1 | grep -oE "[0-9.]+" | tail -1; }
ccgate(){ grep -iE "Total gate leakage power of a bank" "$1" 2>/dev/null | head -1 | grep -oE "[0-9.]+" | tail -1; }
ccsd()  { local v; v=$(grep -iE "CAM search delay" "$1" 2>/dev/null | grep -oE "[0-9.]+" | tail -1)
          [ -n "$v" ] && { echo "$v"; return; }
          grep -iE "Access time" "$1" 2>/dev/null | head -1 | grep -oE "[0-9.]+" | tail -1; }
ccen()  { grep -iE "associative search energy per access" "$1" 2>/dev/null | head -1 | sed 's/.*: *//'; }

# ---- preflight: all inputs must exist before we start writing the report ----
bA=$(garea base_$MC); bL=$(leak base_$MC); bD=$(dyn base_$MC)
[ -n "$bA" ] || { echo "ERROR: no baseline artifacts (reports/nangate45/mordor_v9/base_$MC)."; echo "       Run designs/mordor_table1_analyze.sh first (or designs/mordor_table1.sh)."; exit 1; }
if [ "$BLOCKED" = 1 ]; then
  kA=$(garea blk_$MC); kL=$(leak blk_$MC); kD=$(dyn blk_$MC)
  [ -n "$kA" ] || { echo "ERROR: no blk_$MC artifacts -- run mordor_table1_analyze.sh --blocked-bit first."; exit 1; }
  for P in $PROQS; do
    [ -f "$WORKDIR/c_proq1_$P.out" ] || { echo "ERROR: $WORKDIR/c_proq1_$P.out missing -- run mordor_table1_analyze.sh --blocked-bit first."; exit 1; }
  done
fi

# ---- render ----------------------------------------------------------------
{
  echo "############################################################################"
  echo "#  TABLE 1  --  MORDOR per-MC hardware overhead vs baseline  (NanGate45, 45nm)"
  echo "#  CAM-on-path = impl1: the per-request PROQ CAM on the scheduling path --"
  echo "#  THE implementation reported in the paper's Table 1 (MC=$MC, P in {$PROQS})."
  echo "############################################################################"
  RAW1="$WORKDIR/_impl1.txt"; : > "$RAW1"
  for P in $PROQS; do
    v=$(camv $P)
    cA=$(garea "$v"); cL=$(leak "$v"); cD=$(dyn "$v"); lt=$(lat "$v")
    awk -v P=$P -v bA="$bA" -v bL="$bL" -v bD="$bD" -v cA="$cA" -v cL="$cL" -v cD="$cD" -v lt="$lt" 'BEGIN{
      if(bA==""||cA==""){ printf "CAM-on-path %s - - - - - - -\n", P; exit }
      ORs=(cL-bL)*1000; if(lt=="")lt="-";
      printf "CAM-on-path %d %.3f %.3f %.0f - - %s %.3f\n", \
             P, ORs, (cD-bD)*1000, cA-bA, lt, ORs }' >> "$RAW1"
  done
  python3 "$FLOW/designs/render_table1.py" "$RAW1" || { echo "[render failed -- raw rows:]"; cat "$RAW1"; }

  if [ "$BLOCKED" = 1 ]; then
    echo
    echo "############################################################################"
    echo "#  SUPPLEMENTARY  --  blocked-bit (impl2): FIFO/RAM PROQ + 1-port install CAM."
    echo "#  The same measurements for the lower-cost alternative; NOT in the paper."
    echo "############################################################################"
    RAW2="$WORKDIR/_impl2.txt"; : > "$RAW2"
    for P in $PROQS; do
      cc="$WORKDIR/c_proq1_$P.out"
      xa=$(ccarea "$cc"); xl=$(ccleak "$cc"); xg=$(ccgate "$cc"); xs=$(ccsd "$cc"); xe=$(ccen "$cc")
      awk -v P=$P -v bA="$bA" -v bL="$bL" -v bD="$bD" -v kA="$kA" -v kL="$kL" -v kD="$kD" \
          -v xa="$xa" -v xl="$xl" -v xg="$xg" -v xs="$xs" -v xe="$xe" 'BEGIN{
        if(bA==""||kA==""||xa==""){ printf "blocked-bit %s - - - - - - -\n", P; exit }
        ORs=(kL-bL)*1000;
        printf "blocked-bit %d %.3f %.3f %.0f %.2f %.3f %.2f %.3f\n", \
               P, ORs, (kD-bD)*1000, (kA-bA) + xa*1e6, xe*1000, xl+xg, xs, ORs + xl+xg }' >> "$RAW2"
    done
    python3 "$FLOW/designs/render_table1.py" "$RAW2" || { echo "[render failed -- raw rows:]"; cat "$RAW2"; }
  fi
} | tee "$OUTFILE"

echo
echo "report written to $OUTFILE"
