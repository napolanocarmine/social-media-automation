#!/bin/sh
set -eu

mkdir -p /app/output/logs /app/output/canva-rendered/ig /app/output/canva-rendered/fb /app/output/canva-rendered/stories

cmd="${1:-api}"
shift || true

case "${cmd}" in
  ui|ui-legacy)
    exec streamlit run src/social_automation/web/app.py \
      --server.address=0.0.0.0 \
      --server.port=8501 \
      --server.headless=true \
      "$@"
    ;;
  scheduler)
    exec /app/docker/dispatch-loop.sh
    ;;
  cli)
    exec python -m social_automation "$@"
    ;;
  api)
    exec uvicorn social_automation.api.main:app \
      --host 0.0.0.0 \
      --port "${API_PORT:-8000}" \
      "$@"
    ;;
  shell)
    exec /bin/sh "$@"
    ;;
  *)
    exec "${cmd}" "$@"
    ;;
esac
