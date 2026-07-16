# 06 — Deploy e configurazione Vercel

Guida operativa per il deploy del progetto su Vercel.

---

## Struttura progetto target

```
social-media-automation-vercel/
├── frontend/                  # React SPA (root directory Vercel)
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
├── api/                       # FastAPI entrypoint per Vercel
│   ├── index.py               # ASGI app wrapper
│   └── cron/
│       └── dispatch.py        # Endpoint cron
├── src/
│   └── social_automation/     # Backend Python (copiato/adattato)
├── config/                    # YAML/MD brand (non segreti)
├── pyproject.toml
├── vercel.json
└── requirements.txt           # Dipendenze Python per Vercel
```

---

## `vercel.json`

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "npm ci --prefix frontend && npm run build --prefix frontend",
  "outputDirectory": "frontend/dist",
  "framework": null,
  "rewrites": [
    {
      "source": "/api/cron/(.*)",
      "destination": "/api/cron/$1"
    },
    {
      "source": "/api/(.*)",
      "destination": "/api/index.py"
    },
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ],
  "crons": [
    {
      "path": "/api/cron/dispatch",
      "schedule": "*/15 * * * *"
    }
  ],
  "functions": {
    "api/index.py": {
      "maxDuration": 60
    },
    "api/cron/dispatch.py": {
      "maxDuration": 120
    },
    "api/jobs/process-item.py": {
      "maxDuration": 300
    }
  },
  "headers": [
    {
      "source": "/api/v1/batches/(.*)/events",
      "headers": [
        { "key": "Cache-Control", "value": "no-cache" },
        { "key": "X-Accel-Buffering", "value": "no" }
      ]
    }
  ]
}
```

### Note configurazione

| Setting | Valore | Motivo |
|---------|--------|--------|
| `outputDirectory` | `frontend/dist` | SPA statica |
| Rewrite `/api/*` | `api/index.py` | FastAPI come function |
| Rewrite `/*` | `/index.html` | SPA fallback |
| Cron schedule | `*/15 * * * *` | Dispatch ogni 15 min |
| `maxDuration` dispatch | 120s | Tempo per pubblicare N eventi |
| `maxDuration` batch item | 300s | Una foto per invocazione |

---

## Entrypoint FastAPI per Vercel

### `api/index.py`

```python
"""ASGI entrypoint per Vercel Python runtime."""
from social_automation.api.main import app

# Vercel rileva automaticamente l'oggetto `app` ASGI
```

### `api/cron/dispatch.py`

```python
"""Endpoint invocato da Vercel Cron per dispatch Meta."""
import os
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Vercel Cron usa GET
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("Authorization", "")

        if not secret or auth != f"Bearer {secret}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"detail":"Unauthorized"}')
            return

        from social_automation.services.dispatch import run_dispatch
        from social_automation.db import get_database
        from social_automation.settings import load_settings

        settings = load_settings()
        db = get_database(settings)

        try:
            result = run_dispatch(db, limit=int(os.getenv("DISPATCH_LIMIT", "100")), settings=settings)
            body = json.dumps({"ok": True, **result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
```

> **Alternativa:** usare FastAPI router dedicato (`/api/v1/cron/dispatch`) con middleware auth, invece di un handler separato. Entrambi funzionano su Vercel.

---

## `requirements.txt`

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
sse-starlette>=2.1.0
pydantic>=2.0
pydantic-settings>=2.0
httpx>=0.27.0
PyYAML>=6.0
Pillow>=10.0.0
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
psycopg[binary,pool]>=3.2.0
numpy>=1.24.0
```

### Dipendenze escluse su Vercel (inizialmente)

| Pacchetto | Motivo esclusione |
|-----------|-------------------|
| `onnxruntime` | Bundle pesante, gate ONNX disabilitato |
| `streamlit` | UI deprecata |

---

## Setup Vercel — passo per passo

### 1. Creare progetto

```bash
cd social-media-automation-vercel
vercel link
```

### 2. Installare integrazioni Storage

```bash
# Postgres
vercel install neon --name story-db --plan free -e production -e preview

# Blob
vercel install blob --name story-media -e production -e preview
```

Oppure dal Dashboard: **Storage → Browse Marketplace**.

### 3. Configurare env vars

```bash
# Secrets (una per una, --sensitive)
vercel env add META_PAGE_ACCESS_TOKEN production --sensitive
vercel env add VISION_API_KEY production --sensitive
vercel env add CRON_SECRET production --sensitive
vercel env add GOOGLE_CREDENTIALS_JSON production --sensitive
vercel env add GOOGLE_REFRESH_TOKEN production --sensitive

# Config non sensibili
vercel env add APP_TIMEZONE production
# → Europe/Rome

vercel env add API_CORS_ORIGINS production
# → https://social-media-automation-vercel.vercel.app

vercel env add DB_BACKEND production
# → postgres

vercel env add STORAGE_BACKEND production
# → vercel_blob
```

### 4. Eseguire migrazione schema

```bash
# Con DATABASE_URL_UNPOOLED dal dashboard Neon
psql "$DATABASE_URL_UNPOOLED" -f docs/sql/001_initial_schema.sql
```

### 5. Deploy

```bash
vercel --prod
```

### 6. Proteggere dashboard

Dashboard → Settings → **Deployment Protection** → Enable Password Protection.

---

## Frontend — modifiche minime

### `vite.config.ts` (dev locale invariato)

```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
```

In produzione, Vercel `rewrites` in `vercel.json` gestiscono il proxy — nessuna modifica al client API.

### Build

```bash
cd frontend && npm run build
# Output: frontend/dist/
```

---

## CI/CD

### GitHub integration (consigliata)

1. Collegare repo GitHub a Vercel
2. Ogni push su `main` → deploy Production
3. Ogni PR → deploy Preview con Neon branch isolato

### GitHub Actions (opzionale, per test pre-deploy)

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev,api]" psycopg[binary]
      - run: pytest
        env:
          TEST_DATABASE_URL: postgresql://postgres:test@localhost:5432/test
          DB_BACKEND: postgres
```

---

## Ambienti

| Ambiente | Branch | DB | Note |
|----------|--------|-----|------|
| **Production** | `main` | Neon production branch | Cron attivo |
| **Preview** | PR branches | Neon preview branch (auto) | Cron disabilitato o separato |
| **Development** | locale | SQLite + filesystem | `DB_BACKEND=sqlite` |

### Disabilitare cron su Preview

Vercel Cron gira solo su Production per default. Per sicurezza, il endpoint cron deve verificare `VERCEL_ENV === 'production'`.

---

## Monitoring

| Cosa | Come |
|------|------|
| Log API | Vercel Dashboard → Functions → Logs |
| Log cron | Vercel Dashboard → Cron Jobs → History |
| Errori dispatch | Log strutturato + `planning_events.detail` |
| DB query | Neon Dashboard → Monitoring |
| Blob usage | Vercel Dashboard → Storage |

### Alerting (consigliato)

- Vercel Integration con Slack/email per deploy failures
- Cron failure: risponde non-200 → Vercel logga automaticamente
- Opzionale: endpoint `/api/v1/health` monitorato esternamente (UptimeRobot, Better Stack)

---

## Troubleshooting deploy

| Problema | Causa | Soluzione |
|----------|-------|-----------|
| 504 timeout API | Function troppo lenta | Aumentare `maxDuration`, ottimizzare query |
| CORS error | `API_CORS_ORIGINS` errato | Aggiungere dominio Vercel esatto |
| 401 cron | `CRON_SECRET` mancante | Verificare env + header Authorization |
| 502 DB connection | Pool esaurito | Usare `DATABASE_URL` pooled, non unpoled |
| Immagini 404 | Path locali nel DB | Migrare a Blob URL |
| Build Python fail | Dipendenze pesanti | Rimuovere `onnxruntime`, verificare `requirements.txt` |
| SSE non aggiorna | Buffering proxy | Headers `no-cache` in `vercel.json` |

---

## Checklist deploy

- [ ] `vercel.json` configurato con rewrites, crons, maxDuration
- [ ] `api/index.py` entrypoint ASGI
- [ ] `requirements.txt` con dipendenze necessarie
- [ ] Neon installato, schema eseguito
- [ ] Blob installato
- [ ] Tutti i secrets configurati (vedi doc 05)
- [ ] `DB_BACKEND=postgres` su Production
- [ ] `STORAGE_BACKEND=vercel_blob` su Production
- [ ] Deploy Production riuscito
- [ ] `GET /api/v1/health` risponde 200
- [ ] Dashboard React carica correttamente
- [ ] Password Protection abilitata
- [ ] Cron dispatch testato manualmente
- [ ] Preview deployment funziona con Neon branch
