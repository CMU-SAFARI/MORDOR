#!/usr/bin/env bash
#
# MORDOR Table-1 ANALYSIS -- runs the OpenROAD synth+P&R behind the paper's Table 1.
#
#   bash designs/mordor_table1_analyze.sh [--blocked-bit]
#
# Builds, on NanGate45 at MC=64 (the paper's design points):
#   base_64                        baseline MC request-queue array          (MODE 0)
#   cam_64 / cam_m64_p{48,64,78}   impl1 CAM-on-path at PROQ=32/48/64/78   (MODE 1)
# The paper's Table 1 uses ONLY these OpenROAD results -- no CACTI.
#
# --blocked-bit additionally analyzes the OPTIONAL impl2 blocked-bit alternative
# (NOT in the paper): the blk_64 variant (MODE 2) + CACTI models of its P-entry
# 1-port install CAM. CACTI is needed only for this option.
#
# make is incremental: variants already built are skipped. From scratch: ~2-2.5 h
# (P=78 routes on a bigger die and takes ~1 h alone).
# Overridables (env): MC (64), PROQS ("32 48 64 78"), WORKDIR, CACTI_DIR.
set -uo pipefail
FLOW="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$FLOW"

BLOCKED=0
for a in "$@"; do case "$a" in
  --blocked-bit) BLOCKED=1 ;;
  *) echo "usage: $0 [--blocked-bit]"; exit 2 ;;
esac; done

MC="${MC:-64}"
PROQS="${PROQS:-32 48 64 78}"     # the paper's Table-1 PROQ points
HEADP=32                          # PROQ_ENTRIES param for base/blk (their results don't depend on it)
BIGDIE_OVER=4096                  # MC*P above this won't route on the default die -> bigger one
WORKDIR="${WORKDIR:-/tmp/mordor_table1}"; mkdir -p "$WORKDIR"
CACTI_DIR="${CACTI_DIR:-$HOME/cacti}"
CAM_BITS=32                       # CACTI entry width (24b addr + pad; clears the 64B floor)
FAILN=0

build() { # build <variant> <verilog-params> [extra make VAR=val ...]
  local v="$1" p="$2"; shift 2
  if make DESIGN_CONFIG=./designs/nangate45/mordor_v9/config.mk DESIGN_NAME=mordor_v9 \
          FLOW_VARIANT="$v" VERILOG_TOP_PARAMS="$p" "$@" > "$WORKDIR/$v.log" 2>&1; then
    echo "  [ OK ] $v  ($p)"
  else
    echo "  [FAIL] $v  ($p) -- see $WORKDIR/$v.log"; FAILN=$((FAILN+1))
  fi
}

echo "== OpenROAD analysis: baseline + impl1 CAM-on-path (MC=$MC, P in {$PROQS}) =="
build base_$MC "MC_ENTRIES $MC PROQ_ENTRIES $HEADP MODE 0"
for P in $PROQS; do
  v=$([ "$P" = "$HEADP" ] && echo cam_$MC || echo cam_m${MC}_p$P)
  if [ $(( MC * P )) -gt $BIGDIE_OVER ]; then
    build "$v" "MC_ENTRIES $MC PROQ_ENTRIES $P MODE 1" DIE_AREA="0 0 3500 3500" CORE_AREA="100 100 3400 3400"
  else
    build "$v" "MC_ENTRIES $MC PROQ_ENTRIES $P MODE 1"
  fi
done

if [ "$BLOCKED" = 1 ]; then
  echo "== OpenROAD analysis: impl2 blocked-bit (optional; NOT in the paper) =="
  build blk_$MC "MC_ENTRIES $MC PROQ_ENTRIES $HEADP MODE 2"
  echo "== CACTI: impl2 P-entry 1-port install CAM (the only user of CACTI) =="
  [ -x "$CACTI_DIR/cacti" ] || { echo "  [FAIL] no cacti binary at $CACTI_DIR (set CACTI_DIR)"; exit 1; }
  for P in $PROQS; do
    wb=$(( (CAM_BITS+7)/8 ))
    sed -e 's/^-size (bytes) 131072/-size (bytes) '"$(( P*wb ))"'/' \
        -e 's/^-block size (bytes) 64/-block size (bytes) '"$wb"'/' \
        -e 's/^-associativity 2/-associativity 0/' \
        -e 's/^-technology (u) 0.090/-technology (u) 0.045/' \
        -e 's/^-cache type "cache"/-cache type "cam"/' \
        -e 's#^-output/input bus width 512#-output/input bus width '"$CAM_BITS"'#' \
        "$CACTI_DIR/cache.cfg" > "$WORKDIR/c_proq1_$P.cfg"
    printf -- '-search port 1\n' >> "$WORKDIR/c_proq1_$P.cfg"
    if ( cd "$CACTI_DIR" && ./cacti -infile "$WORKDIR/c_proq1_$P.cfg" ) > "$WORKDIR/c_proq1_$P.out" 2>&1; then
      echo "  [ OK ] install-CAM P=$P"
    else
      echo "  [FAIL] install-CAM P=$P -- see $WORKDIR/c_proq1_$P.out"; FAILN=$((FAILN+1))
    fi
  done
fi

echo "== analysis done ($FAILN failures): artifacts in $FLOW/{reports,logs,results}/nangate45/mordor_v9/ + $WORKDIR =="
[ "$FAILN" -eq 0 ]
