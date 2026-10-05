#!/usr/bin/env bash
#
# Container entry point for the paper's OpenROAD analysis.
set -uo pipefail

ORFS=/OpenROAD-flow-scripts
source "$ORFS/env.sh"
cd "$ORFS/flow"

export SKIP_REPORT_METRICS="${SKIP_REPORT_METRICS:-1}"

OUT=/out
mkdir -p "$OUT"

bash designs/mordor_table1.sh "$@" -o "$OUT/mordor_table1_output.txt" || true

# Keep the raw OpenROAD artifacts alongside the report.
cp -r /tmp/mordor_table1 "$OUT/raw_workdir" 2>/dev/null || true
mkdir -p "$OUT/openroad_raw"
cp -r reports/nangate45/mordor_v9 "$OUT/openroad_raw/reports" 2>/dev/null || true
cp -r logs/nangate45/mordor_v9    "$OUT/openroad_raw/logs"    2>/dev/null || true

echo
echo "[MORDOR] done. Report -> $OUT/mordor_table1_output.txt (also printed above)."
echo "[MORDOR] Compare the generated values with the hardware-overhead table."
