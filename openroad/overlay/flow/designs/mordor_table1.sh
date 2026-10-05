#!/usr/bin/env bash
#
# Run the paper's OpenROAD analysis, then write its report.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$HERE/mordor_table1_analyze.sh" || {
  echo "analysis had failures -- not rendering a report from incomplete artifacts."; exit 1; }
exec bash "$HERE/mordor_table1_report.sh" "$@"
