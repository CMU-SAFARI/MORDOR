#!/usr/bin/env bash
# Compatibility entry point matching the camera-ready artifact appendix.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/openroad/reproduce_table1.sh" "$@"
