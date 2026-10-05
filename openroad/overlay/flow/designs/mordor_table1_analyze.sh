#!/usr/bin/env bash
#
# Run the OpenROAD synthesis and place-and-route design points:
#   base_64                        baseline MC request-queue array          (MODE 0)
#   cam_64 / cam_m64_p{48,64,78}   CAM-on-path at PROQ=32/48/64/78         (MODE 1)
# Existing variants are reused. MC, PROQS, and WORKDIR may be set in the environment.
set -uo pipefail
FLOW="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$FLOW"

if [ "$#" -ne 0 ]; then
  echo "usage: $0" >&2
  exit 2
fi

MC="${MC:-64}"
PROQS="${PROQS:-32 48 64 78}"     # the paper's Table-1 PROQ points
HEADP=32
BIGDIE_OVER=4096                  # MC*P above this won't route on the default die -> bigger one
WORKDIR="${WORKDIR:-/tmp/mordor_table1}"; mkdir -p "$WORKDIR"
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

echo "== OpenROAD analysis: baseline + CAM-on-path (MC=$MC, P in {$PROQS}) =="
build base_$MC "MC_ENTRIES $MC PROQ_ENTRIES $HEADP MODE 0"
for P in $PROQS; do
  v=$([ "$P" = "$HEADP" ] && echo cam_$MC || echo cam_m${MC}_p$P)
  if [ $(( MC * P )) -gt $BIGDIE_OVER ]; then
    build "$v" "MC_ENTRIES $MC PROQ_ENTRIES $P MODE 1" DIE_AREA="0 0 3500 3500" CORE_AREA="100 100 3400 3400"
  else
    build "$v" "MC_ENTRIES $MC PROQ_ENTRIES $P MODE 1"
  fi
done

echo "== analysis done ($FAILN failures): artifacts in $FLOW/{reports,logs,results}/nangate45/mordor_v9/ + $WORKDIR =="
[ "$FAILN" -eq 0 ]
