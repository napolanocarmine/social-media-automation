#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/output/logs"
mkdir -p "${LOG_DIR}"

cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
LIMIT="${DISPATCH_LIMIT:-100}"
PLATFORM="${DISPATCH_PLATFORM:-}"

CMD=("${PYTHON_BIN}" "-m" "social_automation" "dispatch-scheduled" "--limit" "${LIMIT}")
if [[ -n "${PLATFORM}" ]]; then
  CMD+=("--platform" "${PLATFORM}")
fi

export PYTHONPATH="${PROJECT_ROOT}/src"
"${CMD[@]}" >> "${LOG_DIR}/dispatch-scheduled.log" 2>&1
