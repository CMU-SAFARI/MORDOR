#!/usr/bin/env bash
#
# MORDOR Table 1, end to end: run the analysis, then write the report.
#
#   bash designs/mordor_table1.sh [--blocked-bit] [-o FILE]
#
#   --blocked-bit  also analyze + report the optional impl2 blocked-bit
#                  alternative (NOT in the paper; the only part that uses CACTI)
#   -o FILE        report destination (default ./mordor_table1_report.txt)
#
# Equivalent to: mordor_table1_analyze.sh [--blocked-bit]
#             && mordor_table1_report.sh  [--blocked-bit] [-o FILE]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AFLAGS=()
for a in "$@"; do [ "$a" = "--blocked-bit" ] && AFLAGS+=(--blocked-bit); done

bash "$HERE/mordor_table1_analyze.sh" ${AFLAGS[@]+"${AFLAGS[@]}"} || {
  echo "analysis had failures -- not rendering a report from incomplete artifacts."; exit 1; }
exec bash "$HERE/mordor_table1_report.sh" "$@"
