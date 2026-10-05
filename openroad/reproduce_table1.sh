#!/usr/bin/env bash
#
# One-command host wrapper for the MORDOR Table 1 reproduction.
#
#   ./reproduce_table1.sh                 # build + full paper experiment
#   ./reproduce_table1.sh --quick         # build + PROQ=32 smoke test
#   ./reproduce_table1.sh --skip-build    # reuse an existing Docker image
#   ./reproduce_table1.sh --sudo          # invoke Docker through sudo
#   ./reproduce_table1.sh --blocked-bit   # include non-paper supplementary data
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-mordor-hw}"
QUICK=0
SKIP_BUILD=0
BLOCKED_BIT=0
USE_SUDO=0

usage() {
  cat <<'EOF'
usage: ./reproduce_table1.sh [options]

Options:
  --quick         Run only the PROQ=32 functional check (~20 min).
  --skip-build    Reuse the existing mordor-hw Docker image.
  --blocked-bit   Include the supplementary non-paper blocked-bit experiment.
  --sudo          Run Docker through sudo.
  -h, --help      Show this help.
EOF
}

while (($#)); do
  case "$1" in
    --quick) QUICK=1 ;;
    --skip-build) SKIP_BUILD=1 ;;
    --blocked-bit) BLOCKED_BIT=1 ;;
    --sudo) USE_SUDO=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

DOCKER=(docker)
if ((USE_SUDO)); then
  DOCKER=(sudo docker)
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[MORDOR] ERROR: Docker Engine/CLI is not installed." >&2
  echo "Install Docker Engine and the Docker Buildx plugin, then retry." >&2
  exit 2
fi
if ((USE_SUDO)) && ! command -v sudo >/dev/null 2>&1; then
  echo "[MORDOR] ERROR: --sudo was requested, but sudo is unavailable." >&2
  exit 2
fi
if ! DOCKER_INFO="$("${DOCKER[@]}" info 2>&1)"; then
  echo "[MORDOR] ERROR: cannot connect to the Docker daemon." >&2
  echo "${DOCKER_INFO}" >&2
  cat >&2 <<'EOF'
Ensure that Docker Engine is running (on systemd hosts:
  sudo systemctl enable --now docker
), then use --sudo or grant the current user access to the Docker socket.
EOF
  exit 2
fi
if ! "${DOCKER[@]}" buildx version >/dev/null 2>&1; then
  echo "[MORDOR] WARNING: Docker Buildx is not installed." >&2
  echo "The deprecated legacy builder may work today, but Buildx is recommended." >&2
fi

cd "$ROOT"
mkdir -p out

if ((SKIP_BUILD == 0)); then
  echo "[MORDOR] Verifying the pinned OpenROAD executable"
  (
    cd "$ROOT/.."
    sha256sum -c CHECKSUMS.sha256
  )
  echo "[MORDOR] Building pinned Docker image: $IMAGE_NAME"
  "${DOCKER[@]}" build -t "$IMAGE_NAME" .
fi

RUN_ARGS=(run --rm -v "$ROOT/out:/out")
LOG="$ROOT/out/run.log"
if ((QUICK)); then
  RUN_ARGS+=(-e PROQS=32)
  LOG="$ROOT/out/run-p32.log"
fi
RUN_ARGS+=("$IMAGE_NAME")
if ((BLOCKED_BIT)); then
  RUN_ARGS+=(--blocked-bit)
  LOG="$ROOT/out/run-blocked-bit.log"
fi

echo "[MORDOR] Running experiment; console log: $LOG"
"${DOCKER[@]}" "${RUN_ARGS[@]}" 2>&1 | tee "$LOG"

REPORT="$ROOT/out/mordor_table1_output.txt"
if [[ ! -s "$REPORT" ]]; then
  echo "[MORDOR] ERROR: expected report was not produced: $REPORT" >&2
  exit 1
fi
if grep -q '\[FAIL\]' "$LOG"; then
  echo "[MORDOR] ERROR: at least one analysis variant failed; inspect $LOG" >&2
  exit 1
fi

echo "[MORDOR] Completed successfully."
echo "[MORDOR] Report: $REPORT"
echo "[MORDOR] Raw outputs: $ROOT/out/openroad_raw/"
