#!/bin/bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Missing local environment. Run ./setup_ae.sh first." >&2
  exit 2
fi

exec "${PYTHON}" "${ROOT}/reproduce.py" cluster fetch "$@"
