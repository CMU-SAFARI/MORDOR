#!/bin/bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KEY="${MORDOR_AE_KEY:-${ROOT}/credentials/ae_cluster_key}"

if [[ ! -e "${KEY}" ]]; then
  install -m 600 /dev/null "${KEY}"
  cat <<EOF
Created the private-key slot:
  ${KEY}

Copy the evaluator private key into that file, then run this command again:
  ./setup_ae.sh

The credentials directory is excluded from Git.
EOF
  exit 2
fi

if ! grep -q -- 'BEGIN .*PRIVATE KEY' "${KEY}" 2>/dev/null; then
  echo "The private-key file is empty or does not contain an SSH private key: ${KEY}" >&2
  echo "Copy the evaluator private key into it and rerun ./setup_ae.sh." >&2
  exit 2
fi

chmod 600 "${KEY}"

if [[ ! -x "${ROOT}/.venv/bin/python" ]]; then
  echo "Creating the local plotting environment..."
  python3 -m venv "${ROOT}/.venv"
fi

echo "Installing local orchestration and plotting dependencies..."
"${ROOT}/.venv/bin/python" -m pip install \
  -r "${ROOT}/artifact_evaluation/requirements.txt" \
  -r "${ROOT}/plotting/requirements.txt"

exec "${ROOT}/.venv/bin/python" "${ROOT}/reproduce.py" cluster setup
