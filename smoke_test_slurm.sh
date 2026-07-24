#!/bin/bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KEY="${MORDOR_AE_KEY:-${ROOT}/credentials/ae_cluster_key}"
HOST="aevaluator2@safari-proxy.ethz.ch"
ACTION="${1:-resume}"

if [[ "${ACTION}" == "-h" || "${ACTION}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./smoke_test_slurm.sh [resume|status|queue|plan|submit]

The smoke cohort contains ten real paper jobs:
  - PARA, 401.bzip2
  - four main-study cases
  - six blast-radius cases

The default action, resume, submits only missing jobs and skips completed or
currently active jobs.
EOF
  exit 0
fi

if ! grep -q -- 'BEGIN .*PRIVATE KEY' "${KEY}" 2>/dev/null; then
  echo "Missing SSH private key: ${KEY}" >&2
  exit 2
fi
chmod 600 "${KEY}"

SSH=(
  ssh -i "${KEY}"
  -o IdentitiesOnly=yes
  -o BatchMode=yes
  -o StrictHostKeyChecking=accept-new
  "${HOST}"
)

if [[ "${ACTION}" == "queue" ]]; then
  exec "${SSH[@]}" "squeue -u aevaluator2 -o '%.18i %.50j %.10T %.10M %.20R'"
fi

case "${ACTION}" in
  plan)   EXTRA=() ;;
  submit) EXTRA=(--submit) ;;
  resume) EXTRA=(--resume) ;;
  status) EXTRA=(--status) ;;
  *)
    echo "Unknown action: ${ACTION}" >&2
    echo "Use --help for available actions." >&2
    exit 2
    ;;
esac

REMOTE=(
  python3 MORDOR/artifact_evaluation/run_experiments.py
  --repo-root MORDOR/ramulator
  --trace-dir /mnt/panzer/mmakeenkova/EMPRESS/cputraces
  --workspace-root ../artifact_workspace
  --ramulator build/ramulator2
  --classes main blast-radius
  --mechanisms PARA
  --traces 401.bzip2
  --partition high_latency
  --memory 6GB
  --exclude kratos10
  "${EXTRA[@]}"
)
printf -v REMOTE_COMMAND '%q ' "${REMOTE[@]}"

"${SSH[@]}" "${REMOTE_COMMAND}"

if [[ "${ACTION}" == "resume" || "${ACTION}" == "submit" ]]; then
  echo
  echo "Smoke cohort launched. Check it with:"
  echo "  ./smoke_test_slurm.sh queue"
  echo "  ./smoke_test_slurm.sh status"
fi
