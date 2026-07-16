#!/usr/bin/env bash
# Crea directory e file placeholder per i bind mount di docker compose.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

mkdir -p output/logs output/canva-rendered config models

for f in credentials.json token.json canva_token.json; do
  if [[ ! -f "${f}" ]]; then
    echo '{}' > "${f}"
    echo "Creato placeholder ${f} — sostituisci dopo OAuth sul host."
  fi
done

for example in schedule categories canva vision_brand; do
  src="config/${example}.example.yaml"
  dst="config/${example}.yaml"
  if [[ -f "${src}" && ! -f "${dst}" ]]; then
    cp "${src}" "${dst}"
    echo "Copiato ${src} → ${dst}"
  fi
done

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Creato .env da .env.example — compila le variabili."
fi

echo "Pronto per: docker compose build && docker compose up -d"
echo "Web UI: http://localhost:\${WEB_PORT:-8080}"
