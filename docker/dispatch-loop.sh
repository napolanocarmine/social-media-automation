#!/bin/sh
# Alternativa a launchd (macOS): esegue dispatch-scheduled a intervallo regolare (default 10 min).
set -eu

INTERVAL="${DISPATCH_INTERVAL_SECONDS:-600}"
LIMIT="${DISPATCH_LIMIT:-100}"
PLATFORM="${DISPATCH_PLATFORM:-}"

echo "dispatch-loop: interval=${INTERVAL}s limit=${LIMIT} platform=${PLATFORM:-all}"

while true; do
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[$ts] dispatch-scheduled start"
  set +e
  if [ -n "${PLATFORM}" ]; then
    python -m social_automation dispatch-scheduled --limit "${LIMIT}" --platform "${PLATFORM}"
  else
    python -m social_automation dispatch-scheduled --limit "${LIMIT}"
  fi
  code=$?
  set -e
  if [ "${code}" -ne 0 ]; then
    echo "[$ts] dispatch-scheduled exit=${code}" >&2
  fi
  sleep "${INTERVAL}"
done
