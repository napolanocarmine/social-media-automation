#!/usr/bin/env bash
# Smoke test HTTP dello stack web (nginx + API) o API standalone.
#
# Esempi:
#   ./scripts/smoke-e2e.sh
#   WEB_URL=http://100.x.x.x:8080 ./scripts/smoke-e2e.sh   # Tailscale
#   API_URL=http://127.0.0.1:8000 ./scripts/smoke-e2e.sh    # solo uvicorn dev
set -euo pipefail

WEB_URL="${WEB_URL:-http://127.0.0.1:8080}"
API_URL="${API_URL:-${WEB_URL}}"

check() {
  local name="$1"
  local url="$2"
  local code
  code="$(curl -fsS -o /dev/null -w '%{http_code}' "${url}")" || {
    echo "FAIL ${name}: ${url}" >&2
    return 1
  }
  if [[ "${code}" != "200" && "${code}" != "204" ]]; then
    echo "FAIL ${name}: HTTP ${code} ${url}" >&2
    return 1
  fi
  echo "OK   ${name} (${code})"
}

echo "Smoke E2E — WEB_URL=${WEB_URL} API_URL=${API_URL}"

check "web index" "${WEB_URL}/"
check "health legacy" "${API_URL}/api/health"
check "health v1" "${API_URL}/api/v1/health"
check "dashboard stats" "${API_URL}/api/v1/dashboard/stats"
check "config categories" "${API_URL}/api/v1/config/categories"
check "dispatch due" "${API_URL}/api/v1/dispatch/due?limit=5"
check "batches list" "${API_URL}/api/v1/batches?limit=5"

echo "Smoke E2E completato."
