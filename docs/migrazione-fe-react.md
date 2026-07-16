# Migrazione frontend: Streamlit → TypeScript + React

Piano di migrazione della UI da **Streamlit** a **React + TypeScript**, con backend **FastAPI** che riusa la logica Python esistente.

> **Contesto:** tool operativo interno (2 utenti), workflow Drive → Story AI → approvazione → pianificazione → Meta.  
> **Motivazione:** maggiore controllo su design, UX fluida (wizard, calendario, gallerie, batch live), deploy con accesso remoto (Tailscale / Cloudflare).

### Stato avanzamento

| Fase | Stato | Note |
|------|-------|------|
| **0 — Preparazione** | ✅ Completata | 2025-06-23 |
| **1 — Foundation + Home** | ✅ Completata | 2025-06-23 |
| **2 — Output + Approva** | ✅ Completata | 2025-06-23 |
| **3 — Drive + Batch** | ✅ Completata | 2025-06-23 |
| **4 — Pianifica + Calendario** | ✅ Completata | API plans/calendar + wizard React |
| **5 — Pubblica + Automazione** | ✅ Completata | Dispatch, prepare-week, batch dashboard |
| **6 — Cutover** | ✅ Completata | Docker web+api, docs, smoke test |

**Avvio dev (stack React + API):**

```bash
# Terminale 1 — API
.venv/bin/uvicorn social_automation.api.main:app --reload --port 8000

# Terminale 2 — Frontend
cd frontend && npm run dev   # http://localhost:5173
```

---

## Indice

1. [Obiettivi e vincoli](#1-obiettivi-e-vincoli)
2. [Stato attuale](#2-stato-attuale)
3. [Architettura target](#3-architettura-target)
4. [Stack tecnologico](#4-stack-tecnologico)
5. [Fasi di migrazione](#5-fasi-di-migrazione)
6. [Refactor backend (pre-requisito)](#6-refactor-backend-pre-requisito)
7. [Specifica API REST](#7-specifica-api-rest)
8. [Mappatura pagine Streamlit → React](#8-mappatura-pagine-streamlit--react)
9. [Struttura repository](#9-struttura-repository)
10. [Docker e deploy](#10-docker-e-deploy)
11. [Autenticazione e accesso remoto](#11-autenticazione-e-accesso-remoto)
12. [Testing](#12-testing)
13. [Rischi e mitigazioni](#13-rischi-e-mitigazioni)
14. [Stima effort e milestone](#14-stima-effort-e-milestone)
15. [Definition of done](#15-definition-of-done)
16. [Fuori scope (fase 1)](#16-fuori-scope-fase-1)

---

## 1. Obiettivi e vincoli

### Obiettivi

- UI moderna, responsive, coerente con il brand Story Food & Drink.
- Workflow a step invariato (Seleziona → Output AI → Approva → Pianifica → Pubblica).
- Parità funzionale con `src/social_automation/web/app.py` (~2200 righe) e moduli collegati.
- Coesistenza temporanea Streamlit + React durante la migrazione incrementale.
- Deploy Docker: API + frontend statico + scheduler (invariato).

### Vincoli

- **Backend Python** resta la fonte di verità (Drive, Meta, Story AI, scheduling).
- **SQLite** resta il DB in fase 1 (`DB_PATH`); migrazione Postgres opzionale e parallela.
- **Un solo scheduler** attivo per evitare doppie pubblicazioni Meta.
- Segreti (`.env`, token OAuth) non committati.
- CLI (`python -m social_automation`) resta disponibile per operazioni manuali e debug.

### Non obiettivi (fase 1)

- Rewrite del backend in Node/Go.
- Migrazione a Postgres (documentata come fase opzionale post-API).
- App mobile nativa.

---

## 2. Stato attuale

### Componenti UI Streamlit

| File | Righe (circa) | Ruolo |
|------|---------------|-------|
| `web/app.py` | ~2190 | Shell, dashboard, selezione Drive, output AI, approvazione, dispatch, automazione |
| `web/plan_image_ui.py` | ~570 | Wizard pianificazione (step 1–2, copy, slot) |
| `web/calendar_edit_ui.py` | ~310 | Modifica / annullamento eventi a calendario |
| `web/batch_job_runner.py` | ~180 | Worker batch render (legacy Canva path) |
| `web/selected_ai_batch_runner.py` | ~160 | Worker batch Story AI su asset selezionati |

### Pagine (`_UI_PAGES`)

1. **Home** — dashboard metriche + next step
2. **① Seleziona** — browse Drive, coda batch AI
3. **② Output AI** — preview before/after, stato batch
4. **③ Approva** — approvazione manuale foto
5. **④ Pianifica** — wizard + calendario editoriale
6. **⑤ Pubblica** — eventi scaduti, dispatch manuale
7. **Automazione** — prepare-week + monitor batch

### Accoppiamenti problematici

- `batch_job_runner.py` importa `_run_process_photo` da `app.py` → logica di business nella UI.
- Nessun layer HTTP: Streamlit chiama direttamente `db/store`, client Drive/Meta, subprocess CLI.
- Stato UI in `st.session_state` (~30 chiavi) → va spostato lato client (React) o server (query params / API stateless).
- Immagini servite da path locali `output/` → l'API deve esporre endpoint `/media/...`.

### Cosa resta invariato

- `db/store.py` — persistenza
- `scheduling/*` — slot, dispatch, prepare-week
- `workflow/process_photo.py` — Story AI pipeline
- `drive/*`, `meta/*`, `brand/*`
- `cli.py` — comandi operativi
- Servizio `scheduler` in Docker

---

## 3. Architettura target

```mermaid
flowchart TB
    subgraph client [Client browser]
        FE[React SPA]
    end

    subgraph server [Server Docker]
        NGINX[nginx / Caddy]
        API[FastAPI :8000]
        SCHED[scheduler]
        WORKER[batch worker subprocess]
        OUT[(output/ + SQLite)]
    end

    FE -->|HTTPS / REST / SSE| NGINX
    NGINX -->|/api/*| API
    NGINX -->|/| FE static
    API --> OUT
    API -->|spawn| WORKER
    SCHED --> OUT
    WORKER --> OUT

    API --> Drive[Google Drive API]
    API --> Meta[Meta Graph API]
    API --> Vision[Vision / Story AI API]
```

### Principi

1. **Thin controllers**: route FastAPI delegano a `services/` (non duplicare logica CLI).
2. **Stateless API**: nessuna sessione server-side obbligatoria in fase 1; JWT opzionale in fase 2.
3. **Long-running jobs**: batch e dispatch via subprocess/worker + polling SSE o WebSocket.
4. **Media**: file system `output/` servito dall'API con path controllati (no directory traversal).

---

## 4. Stack tecnologico

### Frontend (`frontend/`)

| Area | Scelta | Motivazione |
|------|--------|-------------|
| Framework | **React 19** + **TypeScript** | Ecosistema, hiring, librerie UI |
| Build | **Vite** | Dev veloce, HMR, build statica |
| Routing | **React Router v7** | Multi-page SPA, deep link per step workflow |
| Styling | **Tailwind CSS v4** | Utility-first, design system flessibile |
| Componenti | **shadcn/ui** + **Radix UI** | Accessibilità, look professionale |
| Data fetching | **TanStack Query v5** | Cache, polling batch, retry |
| Form | **React Hook Form** + **Zod** | Validazione allineata a Pydantic |
| Calendario | **FullCalendar** o `@schedule-x/react` | Vista mese/settimana, eventi multi-piattaforma |
| Date/time | **date-fns** + **date-fns-tz** | Allineamento `APP_TIMEZONE=Europe/Rome` |
| HTTP | **fetch** o **ky** | Wrapper tipizzato su OpenAPI |
| Icons | **lucide-react** | Coerente con shadcn |

### Backend API (`src/social_automation/api/`)

| Area | Scelta |
|------|--------|
| Framework | **FastAPI** |
| Server ASGI | **uvicorn** (dev), **gunicorn+uvicorn workers** (prod) |
| Schema | **Pydantic v2** (già in progetto) |
| OpenAPI | Auto-generata → client TS opzionale (`openapi-typescript`) |
| CORS | Configurabile per dev (`localhost:5173`) |
| SSE | `sse-starlette` per progress batch |

### DevOps

- Docker multi-stage: build frontend → copia in immagine nginx o servita da FastAPI `StaticFiles`.
- Streamlit resta in profile `legacy` fino a cutover.

---

## 5. Fasi di migrazione

Strategia **strangler fig**: API e React crescono pagina per pagina; Streamlit resta fallback.

### Fase 0 — Preparazione (1 settimana)

- [x] Creare `docs/migrazione-fe-react.md` (questo documento)
- [x] Estrarre servizi da `app.py` → `services/` (dashboard, drive_selection, process_photo, project_paths)
- [x] Aggiungere dipendenza `fastapi`, `uvicorn`, `sse-starlette` in `pyproject.toml` (extra `api`)
- [x] Scaffold `frontend/` (Vite + React + TS + Tailwind)
- [x] Endpoint health: `GET /api/health` e `GET /api/v1/health`
- [x] CI: lint frontend (`oxlint`, `tsc`) + pytest backend (`.github/workflows/ci.yml`)

### Fase 1 — API foundation + layout React (1–2 settimane)

- [x] Moduli API: `main.py`, `deps.py`, `routers/`, `schemas/`
- [x] `GET /api/v1/dashboard/stats` (equivalente `_workflow_stats`)
- [x] `GET /api/v1/dashboard/suggested-next-step`
- [x] Layout React: sidebar workflow, header, theme Story brand
- [x] Pagina **Home** con metriche e CTA "prossimo passo"
- [x] Proxy dev Vite → FastAPI (`/api` → `:8000`)
- [x] Comando Docker `api` in `docker/entrypoint.sh`

**Deliverable:** Home funzionante; Streamlit ancora per il resto.

### Fase 2 — Output AI + Approvazione (2 settimane)

- [x] `GET /api/v1/images/ai-output` (filtri pending/approved/rejected/all)
- [x] `GET /api/v1/images/{id}` + `GET /api/v1/media/images/{id}/processed|original`
- [x] `GET /api/v1/images/pending-approval` + paginazione
- [x] `POST /api/v1/images/{id}/approval` (approve/reject/use_original)
- [x] Componenti: `ImageCompare`, `ApprovalCard`, `Pagination`
- [x] Pagine **② Output AI** e **③ Approva**

**Deliverable:** Flusso review foto senza Streamlit.

### Fase 3 — Selezione Drive + Batch AI (2 settimane)

- [x] `GET /api/v1/drive/assets` (categoria, anno, mese, paginazione)
- [x] `GET /api/v1/drive/thumbnails/{file_id}` (cache thumb esistente)
- [x] `GET /api/v1/config/categories`
- [x] `POST /api/v1/batches/ai` (crea batch + avvia worker)
- [x] `GET /api/v1/batches/{id}` + `GET /api/v1/batches/active`
- [x] `POST /api/v1/batches/{id}/stop`
- [x] SSE: `GET /api/v1/batches/{id}/events` (progress live)
- [x] Pagina **① Seleziona** con griglia multi-select
- [x] Banner batch attivo in Output AI

**Deliverable:** Coda Story AI end-to-end da React.

### Fase 4 — Pianificazione + Calendario (2–3 settimane)

- [x] `GET /api/images/plannable` + count
- [x] `POST /api/plans/suggest-slot` (wrap `suggest_next_free_slot`)
- [x] `POST /api/plans` (post + story rules)
- [x] `POST /api/images/{id}/copy/generate` (wrap `generate_copy_for_image`)
- [x] `GET /api/calendar` (wrap `list_calendar_items`)
- [x] `PATCH /api/plans/{image_id}/{platform}` (reschedule)
- [x] `DELETE /api/plans/{image_id}/{platform}` (cancel + Meta FB se necessario)
- [x] Wizard **④ Pianifica** (step 1–2)
- [x] Vista calendario mese con filtri social/categoria
- [x] Dialog modifica evento (da `calendar_edit_ui.py`)

**Deliverable:** Pianificazione completa inclusa modifica calendario.

### Fase 5 — Pubblica + Automazione (1–2 settimane)

- [x] `GET /api/dispatch/due` (post + story rules)
- [x] `POST /api/dispatch/run` e `POST /api/dispatch/dry-run`
- [x] `POST /api/automation/prepare-week` (sync, come Streamlit)
- [x] `GET /api/batches` (dashboard filtri)
- [x] Pagine **⑤ Pubblica** e **Automazione**

**Deliverable:** Parità funzionale con Streamlit.

### Fase 6 — Cutover e cleanup (1 settimana)

- [x] Docker: servizio `web` (nginx + api), deprecare `ui` Streamlit
- [x] Aggiornare `README.md`, `docs/docker.md`, `docs/progetto-completo.md`
- [x] Rimuovere o spostare Streamlit in optional dependency (`[ui]`)
- [x] Refactor `batch_job_runner` (niente import da `app.py`) — già su `services/process_photo`
- [x] Smoke test end-to-end (`scripts/smoke-e2e.sh` + `tests/test_smoke_api.py`)

---

## 6. Refactor backend (pre-requisito)

Prima di esporre le API, estrarre la logica da `web/app.py` in moduli riusabili.

### Nuova struttura proposta

```
src/social_automation/
├── api/
│   ├── main.py              # FastAPI app, CORS, mount static
│   ├── deps.py              # load_settings, db_path, auth (futuro)
│   ├── routers/
│   │   ├── dashboard.py
│   │   ├── images.py
│   │   ├── drive.py
│   │   ├── batches.py
│   │   ├── plans.py
│   │   ├── calendar.py
│   │   ├── dispatch.py
│   │   └── media.py
│   └── schemas/             # Pydantic request/response
├── services/
│   ├── dashboard.py         # workflow stats, suggest next page
│   ├── images.py            # approval, ai output listing
│   ├── drive_selection.py   # list assets, thumbs, cache
│   ├── batch_runner.py      # launch/stop batch (AI + legacy)
│   ├── planning.py          # plan image, copy generation
│   ├── calendar.py          # list/edit/cancel events
│   ├── dispatch.py          # due events, run dispatch
│   └── media.py             # safe path resolution, streaming
├── web/                     # Streamlit (deprecated dopo cutover)
│   └── app.py               # delega a services/ dove possibile
```

### Funzioni da estrarre da `app.py`

| Funzione attuale | Destinazione servizio |
|------------------|----------------------|
| `_workflow_stats`, `_suggest_next_page` | `services/dashboard.py` |
| `_run_process_photo` | `services/images.py` o `workflow/` |
| `_launch_selected_ai_batch_job` | `services/batch_runner.py` |
| `_get_drive_thumb`, `_load_drive_assets_for_selection` | `services/drive_selection.py` |
| `_render_planning_calendar` logic | `services/calendar.py` |
| `_render_dispatch_page` subprocess | `services/dispatch.py` |
| `_render_prepare_week_page` | wrap `scheduling/prepare_week.py` |

### Regola

Ogni endpoint FastAPI deve essere **≤ 20 righe**: validazione input → chiamata service → response schema.

---

## 7. Specifica API REST

Convenzioni:

- Base path: `/api/v1`
- JSON camelCase in risposta (frontend TS) o snake_case consistente — **scegliere uno** e documentare in OpenAPI
- Errori: `{ "detail": "...", "code": "..." }` con status HTTP appropriati
- Paginazione: `?page=0&pageSize=10`
- Timezone: tutte le datetime in ISO 8601 con offset o UTC + campo `timezone: "Europe/Rome"`

### Endpoint per dominio

#### Dashboard

```
GET /api/v1/dashboard/stats
GET /api/v1/dashboard/suggested-next-step
```

#### Immagini

```
GET    /api/v1/images/ai-output?filter=pending|approved|rejected|all&limit=24
GET    /api/v1/images/pending-approval?platform=&format=&category=&page=&pageSize=
POST   /api/v1/images/{id}/approval          { "approved": true|false }
GET    /api/v1/images/plannable?...
GET    /api/v1/images/{id}
GET    /api/v1/images/{id}/copy-pack
POST   /api/v1/images/{id}/copy/generate     { "objective", "channels", ... }
```

#### Media

```
GET /api/v1/media/{image_id}/processed
GET /api/v1/media/{image_id}/original
GET /api/v1/media/drive-thumb/{file_id}
```

Path resolution via `resolve_media_file_path` — mai accettare path arbitrari dal client.

#### Drive

```
GET /api/v1/drive/assets?category=&year=&month=&page=&pageSize=
GET /api/v1/config/categories
GET /api/v1/config/schedule
```

#### Batch

```
GET    /api/v1/batches?status=&platform=&format=&limit=
GET    /api/v1/batches/{id}
GET    /api/v1/batches/{id}/items
POST   /api/v1/batches/ai                 { assets[], platform, format, category }
POST   /api/v1/batches/{id}/stop
GET    /api/v1/batches/{id}/events        SSE stream
```

#### Pianificazione

```
POST /api/v1/plans/suggest-slot           { platform, format, ... }
POST /api/v1/plans                        { imageId, platform, scheduledFor, caption, ... }
POST /api/v1/plans/story-rule             { imageId, platform, mode, ... }
```

#### Calendario

```
GET    /api/v1/calendar?from=&to=&social=&category=
PATCH  /api/v1/calendar/events/{imageId}/{platform}   { scheduledFor, caption? }
DELETE /api/v1/calendar/events/{imageId}/{platform}
```

#### Dispatch

```
GET  /api/v1/dispatch/due?platform=&limit=
POST /api/v1/dispatch/run                 { platform?, limit }
POST /api/v1/dispatch/dry-run             { platform?, limit }
```

#### Automazione

```
POST /api/v1/automation/prepare-week      { days, dryRun }
GET  /api/v1/automation/jobs/{id}         # se async
```

#### Health

```
GET /api/v1/health
GET /api/v1/health/ready                  # DB + token files presenti
```

---

## 8. Mappatura pagine Streamlit → React

| Streamlit | Route React | Componenti chiave |
|-----------|-------------|-------------------|
| Home | `/` | `DashboardStats`, `WorkflowQuickLinks` |
| ① Seleziona | `/workflow/select` | `DriveAssetGrid`, `BatchLaunchPanel` |
| ② Output AI | `/workflow/output` | `AiOutputGallery`, `BatchProgressBanner` |
| ③ Approva | `/workflow/approve` | `ApprovalViewer`, `BeforeAfterCompare` |
| ④ Pianifica | `/workflow/plan` | `PlanWizard`, `PlanningCalendar` |
| ⑤ Pubblica | `/workflow/publish` | `DueEventsTable`, `DispatchActions` |
| Automazione | `/automation` | `PrepareWeekForm`, `BatchDashboard` |

### Layout condiviso

```
┌──────────────────────────────────────────────────────────┐
│  Story Social          [stats badge]    [user/settings]  │
├────────────┬─────────────────────────────────────────────┤
│ Workflow   │  Content area                               │
│ ● Home     │                                             │
│ 1 Seleziona│                                             │
│ 2 Output   │                                             │
│ 3 Approva  │                                             │
│ 4 Pianifica│                                             │
│ 5 Pubblica │                                             │
│ ─────────  │                                             │
│ Automazione│                                             │
└────────────┴─────────────────────────────────────────────┘
```

### Stato client (React)

Sostituisce `st.session_state`:

| Stato Streamlit | Equivalente React |
|-----------------|-------------------|
| `ui-page` | React Router path |
| `plan-step`, `plan-selected-image-id` | URL search params o Zustand store locale |
| `drive-selected-ids` | stato componente Seleziona |
| `render-active-batch-id` | TanStack Query + polling/SSE |
| Filtri approva/pianifica | URL query (`?platform=instagram&page=2`) |

Preferire **URL query** per filtri condivisibili tra i due utenti ("guarda questo link").

---

## 9. Struttura repository

```
social-media-automation/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/           # file-based o react-router
│       ├── pages/
│       ├── components/
│       │   ├── ui/           # shadcn
│       │   ├── workflow/
│       │   ├── calendar/
│       │   └── images/
│       ├── hooks/
│       ├── lib/
│       │   └── api/          # client tipizzato
│       └── types/
├── src/social_automation/
│   ├── api/                  # NEW
│   ├── services/             # NEW
│   └── web/                  # Streamlit (legacy)
├── docker/
│   ├── entrypoint.sh         # + comando `api`
│   └── nginx.conf            # NEW: proxy /api, serve /
├── docs/
│   └── migrazione-fe-react.md
└── docker-compose.yml        # web + api + scheduler
```

---

## 10. Docker e deploy

### Servizi target (`docker-compose.yml`)

```yaml
services:
  web:
    # nginx: frontend static + reverse proxy /api → api:8000
    ports:
      - "${WEB_PORT:-8080}:80"
    depends_on:
      - api

  api:
    command: ["api"]
    # uvicorn social_automation.api.main:app --host 0.0.0.0 --port 8000
    expose:
      - "8000"
    volumes: *app_volumes

  scheduler:
    # invariato
    depends_on:
      - api

  ui-legacy:
    profiles: ["streamlit"]
    command: ["ui"]
    ports:
      - "${STREAMLIT_PORT:-8501}:8501"
```

### Sviluppo locale

```bash
# Terminale 1 — API
uvicorn social_automation.api.main:app --reload --port 8000

# Terminale 2 — Frontend
cd frontend && npm run dev   # :5173, proxy /api → :8000

# Terminale 3 — Scheduler (opzionale)
python -m social_automation dispatch-scheduled --dry-run
```

### Accesso remoto (2 utenti)

- **Tailscale** sulla macchina host → `http://100.x.x.x:8080`
- Esporre solo `web` (nginx), non SQLite né porte interne
- Auth: vedi §11

---

## 11. Autenticazione e accesso remoto

Streamlit oggi **non ha login**. Con UI esposta via Tailscale il tailnet fa da boundary; con Cloudflare serve protezione esplicita.

### Opzioni (in ordine di semplicità)

| Fase | Meccanismo | Note |
|------|------------|------|
| 1 | Solo Tailscale | Nessun login app; tailnet = auth |
| 2 | Cloudflare Access | Email OTP / Google prima del frontend |
| 3 | API key header | `X-API-Key` per chiamate programmatiche |
| 4 | JWT in FastAPI | Login form React, utenti in config/env |

**Raccomandazione fase 1:** Tailscale + nessun auth app.  
**Raccomandazione se Cloudflare:** Access + API senza JWT interno.

---

## 12. Testing

### Backend

- **pytest** su `services/` con DB temporaneo (pattern esistente in `tests/test_db_store.py`)
- **httpx.AsyncClient** + FastAPI TestClient per route API
- Contract test: response JSON match schema OpenAPI

### Frontend

- **Vitest** + **Testing Library** per componenti
- **Playwright** (opzionale) per E2E workflow critico: approva → pianifica → vedi calendario
- Mock API con **MSW** in dev/test

### Checklist regressione pre-cutover

- [ ] Dashboard stats coerenti con Streamlit
- [ ] Batch AI su N asset selezionati completa con stesso esito
- [ ] Approvazione sblocca immagine in Pianifica
- [ ] Slot suggerito rispetta `schedule.yaml`
- [ ] Modifica calendario aggiorna Meta FB dove applicabile
- [ ] Dispatch dry-run e run producono stesso output CLI
- [ ] Scheduler automatico continua a funzionare indipendentemente dalla UI

---

## 13. Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| Logica duplicata API vs Streamlit | Bug divergenti | Servizi condivisi; Streamlit delega a `services/` durante transizione |
| Batch job orphan | Batch stuck | PID tracking esistente + endpoint stop + timeout |
| Path media non validi | 404 preview | Centralizzare `resolve_media_file_path` in `services/media.py` |
| Due scheduler + nuova UI | Doppia publish | Documentare: un solo `scheduler` container |
| Scope creep design | Ritardi | MVP per pagina, polish in iterazione 2 |
| SSE/WebSocket dietro proxy | Batch non live | nginx config per buffering disabilitato su `/api/v1/batches/*/events` |

---

## 14. Stima effort e milestone

Stime per **1 sviluppatore** familiarità con codebase; **2 sviluppatori** (FE + BE) riducono ~30%.

| Fase | Durata | Cumulative |
|------|--------|------------|
| 0 — Preparazione | 1 sett. | 1 sett. |
| 1 — Foundation + Home | 1–2 sett. | 2–3 sett. |
| 2 — Output + Approva | 2 sett. | 4–5 sett. |
| 3 — Drive + Batch | 2 sett. | 6–7 sett. |
| 4 — Pianifica + Calendario | 2–3 sett. | 8–10 sett. |
| 5 — Pubblica + Automazione | 1–2 sett. | 9–12 sett. |
| 6 — Cutover | 1 sett. | 10–13 sett. |

**Totale indicativo: 2,5–3 mesi** a parità funzionale con polish UI base.

### Milestone verificabili

1. **M1** — API health + Home React in Docker
2. **M2** — Approvazione foto senza Streamlit
3. **M3** — Batch AI da griglia Drive
4. **M4** — Calendario pianificazione editabile
5. **M5** — Cutover produzione, Streamlit disabilitato

---

## 15. Definition of done

La migrazione è **completa** quando:

- [ ] Tutte le route in §8 implementate e usabili
- [ ] `docker compose up` avvia `web` + `api` + `scheduler` senza Streamlit
- [ ] Documentazione aggiornata (`README`, `docker.md`)
- [ ] Test backend API ≥ coverage critici (images, plans, dispatch)
- [ ] Due utenti operano in parallelo via Tailscale senza regressioni
- [ ] Nessun import da `web/app.py` in worker (`batch_job_runner` refactorato)
- [ ] Streamlit rimosso da dipendenza default o relegato a `[ui-legacy]`

---

## 16. Fuori scope (fase 1)

Da pianificare **dopo** il cutover React, come epic separati:

### Postgres / Supabase

- Migrare `store.py` da SQLite a Postgres
- Utile se: UI locale su due Mac + DB cloud condiviso
- Non bloccante se: server Docker unico + accesso browser condiviso

### Miglioramenti UX post-MVP

- Drag-and-drop slot calendario
- Notifiche toast push (dispatch fallito)
- Dark mode brand
- Keyboard shortcuts in approvazione (A/R per approve/reject)
- PWA / installabile su mobile

### Auth applicativa

- Ruoli (editor vs admin dispatch)
- Audit log azioni utente

---

## Riferimenti interni

- Architettura attuale: [progetto-completo.md](./progetto-completo.md) §8 (UI Streamlit)
- Docker: [docker.md](./docker.md)
- CLI equivalenti: [cli-comandi.md](./cli-comandi.md)
- File sorgente UI: `src/social_automation/web/app.py`, `plan_image_ui.py`, `calendar_edit_ui.py`

---

*Documento creato: 2025-06 — aggiornato 2025-06-23 (Fase 0–1 completate).*
