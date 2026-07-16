# Social Media Automation — Vercel

Migrazione cloud-native di **Story Food & Drink** per deploy su Vercel.

Documentazione completa in [`docs/`](./docs/README.md).

## Stack

| Componente | Tecnologia |
|------------|------------|
| Frontend | React + Vite (`frontend/`) |
| API | FastAPI serverless (`api/index.py`) |
| Database | Neon Postgres (`DB_BACKEND=postgres`) |
| Media | Vercel Blob (`STORAGE_BACKEND=vercel_blob`) |
| Cron | Dispatch ogni 15 min + batch queue ogni 1 min |
| Dev locale | SQLite + filesystem (`DB_BACKEND=sqlite`) |

## Quick start locale

```bash
pip install -e ".[dev,api]" -r requirements.txt
cd frontend && npm ci && cd ..

# Dev con SQLite
export DB_BACKEND=sqlite
export STORAGE_BACKEND=local
uvicorn social_automation.api.main:app --reload --port 8000
```

Frontend: `cd frontend && npm run dev`

## Deploy Vercel

1. Collega il repo a Vercel
2. Installa integrazioni **Neon** e **Blob** dal Marketplace
3. Applica schema: `psql "$DATABASE_URL_UNPOOLED" -f docs/sql/001_initial_schema.sql`
4. Configura env (vedi [`.env.vercel.example`](./.env.vercel.example) e [docs/05-secrets-e-variabili-ambiente.md](./docs/05-secrets-e-variabili-ambiente.md))
5. `vercel --prod`

## Endpoint cron

| Path | Schedule | Funzione |
|------|----------|----------|
| `GET /api/cron/dispatch` | `*/15 * * * *` | Pubblicazione Meta |
| `GET /api/cron/process-batch` | `* * * * *` | 1 foto batch AI |

Autenticazione: header `Authorization: Bearer $CRON_SECRET` o query `?secret=`.

## OAuth Google Drive

1. Configura `GOOGLE_CREDENTIALS_JSON` (OAuth Web)
2. Visita `/api/v1/oauth/google/start`
3. Salva `refresh_token` come `GOOGLE_REFRESH_TOKEN`

## Struttura aggiunta per Vercel

```
api/index.py                          # Entrypoint ASGI
vercel.json                           # Rewrites, crons, maxDuration
requirements.txt                      # Dipendenze Python Vercel
src/social_automation/db/
  factory.py                          # Switch sqlite/postgres
  sqlite_store.py                     # Dev locale
  postgres_store.py                   # Produzione Neon
  store.py                            # Facade
src/social_automation/storage/        # Local + Blob
src/social_automation/api/routers/
  cron.py                             # Endpoint cron
  oauth_google.py                     # OAuth web Drive
src/social_automation/services/
  batch_queue.py                      # Queue batch (no subprocess)
scripts/
  migrate_sqlite_to_postgres.py
  upload_output_to_blob.py
```

## Test

```bash
pytest -q
```

Con Postgres:

```bash
TEST_DATABASE_URL=postgresql://... DB_BACKEND=postgres pytest tests/test_db_store.py
```

## Roadmap

Vedi [docs/10-roadmap-milestone.md](./docs/10-roadmap-milestone.md).

- **M1** ✅ Fondamenta: Postgres, deploy, cron dispatch
- **M2** ✅ Storage Blob + media URL
- **M3** ✅ Batch queue + OAuth web
- **M4** Test E2E + go-live (operativo)
