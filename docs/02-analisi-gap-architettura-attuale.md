# 02 — Analisi gap: architettura attuale vs Vercel

Analisi dettagliata di compatibilità tra il progetto `social-media-automation` (stato luglio 2026) e i requisiti per un deploy su Vercel.

---

## Verdetto sintetico

| Area | Compatibile oggi? | Blocco principale |
|------|-------------------|-------------------|
| Frontend React | ✅ Sì | Nessuno |
| API FastAPI (CRUD leggeri) | ⚠️ Parziale | SQLite + file locali |
| Pianificazione | ⚠️ Parziale | SQLite |
| Dispatch Meta | ✅ Sì (logica) | Serve DB persistente + endpoint cron |
| Batch Story AI | ❌ No | Subprocess + timeout + filesystem |
| Preview immagini | ❌ No | `FileResponse` da disco locale |
| OAuth Google/Meta | ❌ No | Flussi desktop/localhost |
| Scheduler | ⚠️ Parziale | API pronta, loop Docker da sostituire |
| Secrets | ⚠️ Parziale | File su disco, non env |

---

## 1. Frontend React — ✅ Pronto

### Stato attuale

- Workflow completo: Home, Select, Output AI, Approve, Plan, Publish, Automation
- API client con path relativi `/api/v1/*`
- Proxy dev Vite → `localhost:8000`
- Build statica con `npm run build`

### Gap

| Gap | Severità | Azione |
|-----|----------|--------|
| Nessun `vercel.json` | Bassa | Creare rewrites SPA + proxy API |
| URL media assoluti da API | Media | API deve restituire URL Blob, non path locali |
| Nessuna auth UI | Media | Aggiungere Vercel Protection o login |

### File rilevanti

```
frontend/src/App.tsx
frontend/src/lib/api/client.ts
frontend/vite.config.ts
```

---

## 2. API FastAPI — ⚠️ Parziale

### Stato attuale

Router completi in `src/social_automation/api/`:

| Router | Prefix | Funzione |
|--------|--------|----------|
| `health` | `/health` | Health check |
| `dashboard` | `/dashboard` | Metriche |
| `config` | `/config` | Categorie, dispatch config |
| `drive` | `/drive` | Listing asset, thumbnail |
| `images` | `/images` | Output AI, approvazione, copy |
| `media` | `/media/images` | Serve file da disco |
| `batches` | `/batches` | Avvio batch, SSE progress |
| `plans` | `/plans` | Pianificazione slot |
| `calendar` | `/calendar` | Calendario editoriale |
| `dispatch` | `/dispatch` | Due events, run, dry-run |
| `automation` | `/automation` | prepare-week |

Entry point: `src/social_automation/api/main.py`

### Gap

| Gap | Severità | Azione |
|-----|----------|--------|
| `DbPathDep` usa SQLite path | **Alta** | Sostituire con connessione Postgres |
| `media.py` usa `FileResponse` | **Alta** | Redirect a Blob URL |
| `batch_runner.py` usa `subprocess.Popen` | **Alta** | Queue job |
| Nessun adapter ASGI per Vercel | Media | Configurare `vercel.json` + entrypoint |
| SSE batch con timeout function | Media | Polling fallback o `maxDuration` alto |
| CORS hardcoded localhost | Bassa | `API_CORS_ORIGINS` con dominio Vercel |

### Dipendenze Python problematiche su Vercel

| Pacchetto | Problema | Mitigazione |
|-----------|----------|-------------|
| `onnxruntime` | Bundle ~100MB+, binari nativi | Disabilitare gate ONNX o lazy import |
| `google-api-python-client` | Pesante ma gestibile | OK con bundle 500MB |
| `Pillow` | OK | Nessuna |
| `fastapi` + `uvicorn` | OK come ASGI su Vercel | Configurare entrypoint |

---

## 3. Database SQLite — ❌ Blocco critico

### Stato attuale

- `src/social_automation/db/store.py` — ~2000 righe, 100% SQLite
- Path: `output/social_automation.db` (default in `settings.py`)
- Tutti i `services/` e `api/routers/` dipendono da `db_path: Path`

### Tabelle

| Tabella | Righe stimate | Uso |
|---------|---------------|-----|
| `images` | Variabile | Asset processati, approvazione, copy |
| `planning_events` | Variabile | Storico pianificazione |
| `story_schedule_rules` | Poche | Regole story ricorrenti |
| `story_schedule_occurrences` | Variabile | Occorrenze story pubblicate |
| `batches` | Variabile | Job batch AI |
| `batch_items` | Variabile | Item singoli nel batch |
| `metadata` | Variabile | Snapshot metadati render |

### Query SQLite-specifiche da migrare

| Pattern SQLite | Occorrenze | Equivalente Postgres |
|----------------|------------|----------------------|
| `julianday()` per confronto date | `list_due_events` | `scheduled_for <= $1::timestamptz` |
| `INSERT OR IGNORE` | `story_schedule_occurrences` | `INSERT ... ON CONFLICT DO NOTHING` |
| `INSERT OR REPLACE` | `batch_items` | `INSERT ... ON CONFLICT DO UPDATE` |
| `datetime('now')` | Default colonne | `NOW()` / `CURRENT_TIMESTAMP` |
| `PRAGMA table_info` | Migrazioni runtime | `information_schema.columns` |
| `AUTOINCREMENT` | PK | `SERIAL` / `GENERATED ALWAYS AS IDENTITY` |
| `INTEGER` per boolean | `render_ig`, flags | `BOOLEAN` o `SMALLINT` |

### Gap

| Gap | Severità | Azione |
|-----|----------|--------|
| Zero codice Postgres | **Alta** | Nuovo layer `db/postgres.py` o SQLAlchemy |
| `db_path: Path` ovunque | **Alta** | Refactor deps → connection pool |
| Migrazioni runtime in Python | Media | Alembic o SQL versionato |
| Nessuno script export SQLite→PG | Media | Script one-shot migrazione dati |

Vedi [03-postgres-schema-e-migrazione.md](./03-postgres-schema-e-migrazione.md).

---

## 4. Storage filesystem — ❌ Blocco critico

### Stato attuale

Tutto in `output/` (gitignored):

```
output/
├── social_automation.db
├── drive_{file_id}.jpg          # Download Drive
├── processed/{ig,fb,stories}/   # Immagini ritoccate
├── batch_queues/{id}.json       # Coda batch
├── logs/batch-{id}.log          # Log worker
├── meta_page_token.txt          # Token Meta (opzionale)
└── canva-rendered/              # Legacy Canva
```

### Punti di accesso filesystem nel codice

| File | Operazione |
|------|------------|
| `workflow/process_photo.py` | Write download + processed |
| `api/routers/media.py` | Read processed/original |
| `services/batch_runner.py` | Write queue JSON + logs |
| `scheduling/dispatch_runner.py` | Read image per publish |
| `meta/client.py` | Read image file per upload Graph |
| `settings.py` | Read token file |

### Gap

| Gap | Severità | Azione |
|-----|----------|--------|
| Path locali nel DB (`images.path`) | **Alta** | Salvare Blob URL |
| `FileResponse` per media | **Alta** | Redirect 302 a Blob |
| Dispatch legge file locale | **Alta** | Download Blob → `/tmp` → publish |
| Queue file JSON su disco | Media | Stato batch solo in Postgres |
| Log batch su file | Bassa | Log strutturato (Vercel logs) o DB |

Vedi [04-storage-media-blob.md](./04-storage-media-blob.md).

---

## 5. Batch AI — ❌ Blocco critico

### Stato attuale

```
POST /api/v1/batches/ai
  → create_batch() in SQLite
  → write output/batch_queues/{id}.json
  → subprocess.Popen(selected_ai_batch_runner)
  → worker processa sequenzialmente (1 foto alla volta)
  → SSE GET /api/v1/batches/{id}/events (poll ogni 2s)
```

### Perché non funziona su Vercel

1. **`subprocess.Popen` con `start_new_session=True`** — processi detached non supportati
2. **Durata** — ogni foto: download Drive + 2–3 chiamate AI + Pillow = 1–5 minuti
3. **Batch multi-foto** — 10 foto = 10–50 minuti, oltre qualsiasi timeout function
4. **SSE long-lived** — la function resta aperta finché il batch è `running`

### Gap

| Gap | Severità | Azione |
|-----|----------|--------|
| Subprocess batch runner | **Alta** | Queue esterna o 1 foto per invocazione |
| Queue file su disco | Media | Payload batch in Postgres (`batch_items`) |
| SSE dipende da processo locale | Media | Polling su stato DB |
| `runner_pid` in batches | Bassa | Rimuovere, usare job ID queue |

Vedi [08-batch-ai-e-job-queue.md](./08-batch-ai-e-job-queue.md).

---

## 6. OAuth e token — ❌ Blocco

### Google Drive

| Attuale | Problema Vercel |
|---------|-----------------|
| OAuth Desktop app | Richiede browser locale |
| `credentials.json` su disco | Non persistente |
| `token.json` con refresh | Non persistente |
| `run_local_server(port=0)` | Non possibile su serverless |

### Meta

| Attuale | Problema Vercel |
|---------|-----------------|
| `meta-oauth-page-token` su `127.0.0.1:8765` | Server HTTP locale |
| `output/meta_page_token.txt` | File su disco |
| `META_PAGE_ACCESS_TOKEN` in `.env` | ✅ Già supportato via env |

### Gap

| Gap | Severità | Azione |
|-----|----------|--------|
| Google OAuth desktop | **Alta** | OAuth Web + callback Vercel |
| Meta OAuth localhost | Media | Setup one-shot locale → token in Vercel env |
| Token refresh Google | Media | Refresh token in env/DB |
| Nessuna auth dashboard | Media | Vercel Protection |

Vedi [09-oauth-e-autenticazione.md](./09-oauth-e-autenticazione.md).

---

## 7. Scheduler dispatch — ⚠️ Quasi pronto

### Stato attuale

- Docker `scheduler` → `dispatch-loop.sh` → `dispatch-scheduled` ogni 600s
- API equivalente: `POST /api/v1/dispatch/run`
- Logica in `services/dispatch.py` → `scheduling/dispatch_runner.py`

### Gap

| Gap | Severità | Azione |
|-----|----------|--------|
| Loop Docker | **Alta** (da sostituire) | Vercel Cron |
| Nessun `CRON_SECRET` | Media | Endpoint dedicato protetto |
| DB SQLite per `list_due_events` | **Alta** | Postgres |
| Immagini locali per publish | **Alta** | Download da Blob |

### Nota timing

- Docker default: ogni **10 minuti**
- Proposta Vercel: ogni **15–60 minuti**
- Con cron orario, un post alle 14:30 potrebbe uscire alle 15:00 (ritardo max 60 min)
- Raccomandazione: `*/15 * * * *` (ogni 15 min) su piano Pro

Vedi [07-cron-dispatch-meta.md](./07-cron-dispatch-meta.md).

---

## 8. Configurazione — ⚠️ Parziale

### Cosa resta nel repo (non segreti)

```
config/
├── brand/          # Prompt Story AI (YAML, MD)
├── categories.yaml # Categorie Drive
├── schedule.yaml   # Slot editoriali
└── vision_brand.yaml
```

Questi file **possono restare nel repo** e essere letti a runtime dal codice deployato.

### Cosa va in Vercel env (segreti)

Tutto ciò che oggi è in `.env` o file token — vedi [05-secrets-e-variabili-ambiente.md](./05-secrets-e-variabili-ambiente.md).

---

## Matrice riepilogativa

| Componente | Pronto | Refactor | Riscrittura |
|------------|--------|----------|-------------|
| Frontend React | ✅ | — | — |
| API routers | — | ✅ | — |
| services/* | — | ✅ (deps) | — |
| scheduling/* | — | ✅ (DB + file) | — |
| meta/* | — | ✅ (file read) | — |
| brand/visual/* | ✅ | — | — |
| db/store.py | — | — | ✅ (Postgres) |
| batch_runner | — | — | ✅ (queue) |
| drive/auth.py | — | — | ✅ (OAuth web) |
| settings.py | — | ✅ | — |
| Docker/scheduler | — | — | ✅ (eliminare) |

**Legenda:** Pronto = deploy as-is | Refactor = adattare deps | Riscrittura = nuovo modulo

---

## Priorità interventi

```
P0 (bloccanti)
├── Postgres al posto di SQLite
├── Blob storage al posto di output/
├── Eliminare subprocess batch
└── Endpoint cron dispatch protetto

P1 (necessari per workflow completo)
├── OAuth Google web
├── Media URL in API responses
├── Auth dashboard
└── Refactor settings.py (env-only secrets)

P2 (miglioramenti)
├── Rimuovere onnxruntime (se non usato)
├── Alembic per migrazioni DB
├── Monitoring/alerting dispatch
└── PWA / mobile-friendly
```
