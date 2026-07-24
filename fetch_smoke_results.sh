#!/bin/bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Missing local environment. Run ./setup_ae.sh first." >&2
  exit 2
fi

"${PYTHON}" "${ROOT}/reproduce.py" cluster fetch \
  --classes main blast-radius \
  --allow-incomplete

expected=(
  "results/baseline/no_mitigation/401.bzip2_output.yaml"
  "results/main/priority/PARA/401.bzip2_output.yaml"
  "results/main/mordor/PARA/401.bzip2_output.yaml"
  "results/main/insecure/PARA/401.bzip2_output.yaml"
)
for radius in 1 2 8; do
  expected+=(
    "results/blast_radius/brc_1/radius_${radius}/priority/PARA/401.bzip2_output.yaml"
    "results/blast_radius/brc_1/radius_${radius}/mordor/PARA/401.bzip2_output.yaml"
  )
done

missing=0
for relative in "${expected[@]}"; do
  if [[ ! -s "${ROOT}/${relative}" ]]; then
    echo "Missing smoke output: ${relative}" >&2
    missing=$((missing + 1))
  fi
done
if (( missing )); then
  echo "Fetch validation failed: ${missing}/10 smoke outputs missing." >&2
  exit 1
fi

echo "Fetch validation passed: 10/10 smoke outputs are present under results/."
