#!/usr/bin/env bash
#
# MICRO-AE entrypoint. Sources the ORFS environment, runs the MORDOR Table-1 analysis +
# report (designs/mordor_table1.sh), and mirrors the report + raw artifacts to /out
# (bind-mount a host dir there).
#
#   docker run --rm -v "$PWD/out:/out" mordor-hw-ae                 # paper Table 1 (impl1), ~2-2.5 h
#   docker run --rm -v "$PWD/out:/out" mordor-hw-ae --blocked-bit   # + optional impl2 blocked-bit table
#
# Quick partial check (~20 min, P=32 only):  docker run ... -e PROQS=32 mordor-hw-ae
#
# NB: no `set -e` -- a single failed variant must not abort the run or skip the /out mirror.
set -uo pipefail

ORFS=/OpenROAD-flow-scripts
source "$ORFS/env.sh"
cd "$ORFS/flow"

# Skip ORFS per-stage report_metrics: its Python metrics-helper child SIGILLs on CPUs
# without AVX-512 (e.g. i9-12900K), killing CTS. The eval doesn't use its output.
export SKIP_REPORT_METRICS="${SKIP_REPORT_METRICS:-1}"

OUT=/out
mkdir -p "$OUT"

bash designs/mordor_table1.sh "$@" -o "$OUT/mordor_ae_output.txt" || true

# Keep the raw OpenROAD/CACTI artifacts alongside the report when /out is mounted.
cp -r /tmp/mordor_table1 "$OUT/raw_workdir" 2>/dev/null || true
mkdir -p "$OUT/openroad_raw"
cp -r reports/nangate45/mordor_v9 "$OUT/openroad_raw/reports" 2>/dev/null || true
cp -r logs/nangate45/mordor_v9    "$OUT/openroad_raw/logs"    2>/dev/null || true

echo
echo "[MORDOR-AE] done. Report -> $OUT/mordor_ae_output.txt (also printed above)."
echo "[MORDOR-AE] Reference to eyeball against: expected_output.txt (shipped with the artifact)."
