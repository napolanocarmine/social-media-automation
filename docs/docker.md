# Docker

Esecuzione containerizzata di **React web + FastAPI** + **scheduler** (`dispatch-scheduled` ogni minuto).

Streamlit resta disponibile come servizio opzionale (`--profile streamlit`).

## Prerequisiti

- Docker Desktop (o Docker Engine + Compose v2)
- OAuth eseguito **almeno una volta** sul host (consigliato), oppure token copiati nei file montati

## Setup rapido

```bash
cd /path/to/social-media-automation

chmod +x scripts/docker-init.sh scripts/smoke-e2e.sh
./scripts/docker-init.sh

# Compila .env (META_*, VISION_*, GOOGLE_DRIVE_FOLDER_ID, …)
# OAuth sul host (se non l’hai già fatto):
#   python -m social_automation drive-auth
#   python -m social_automation meta-oauth-page-token --write-token-file output/meta_page_token.txt

docker compose build
docker compose up -d
./scripts/smoke-e2e.sh
```

- **Web UI:** http://localhost:8080 (nginx → React, `/api` → FastAPI)
- **Scheduler:** loop `dispatch-scheduled` (intervallo `DISPATCH_INTERVAL_SECONDS`, default **10 minuti**)

## Servizi

| Servizio | Comando / immagine | Ruolo |
|----------|-------------------|--------|
| `web` | nginx (`target: web`) | Frontend React statico + reverse proxy `/api` |
| `api` | `entrypoint api` | Backend FastAPI (uvicorn :8000) |
| `scheduler` | `entrypoint scheduler` | Pubblicazione automatica |
| `cli` (profile) | `docker compose run --rm cli …` | Comandi one-shot |
| `ui-legacy` (profile `streamlit`) | `entrypoint ui` | Streamlit deprecato |

## Accesso remoto (2 collaboratori)

Esporre solo la porta **`WEB_PORT`** (default 8080) sulla macchina host, ad es. via **Tailscale**:

```bash
# Sul client
WEB_URL=http://100.x.x.x:8080 ./scripts/smoke-e2e.sh
```

Non esporre SQLite, la porta API interna (8000) né porte di debug.

## Sviluppo locale (senza Docker)

```bash
# Terminale 1
uvicorn social_automation.api.main:app --reload --port 8000

# Terminale 2
cd frontend && npm run dev   # :5173, proxy /api → :8000
```

## Streamlit legacy

```bash
docker compose --profile streamlit up -d ui-legacy
# http://localhost:8501
```

Preferire lo stack `web` + `api` per il workflow operativo.

## CLI nel container

```bash
docker compose run --rm cli prepare-week --dry-run
docker compose run --rm cli dispatch-scheduled --dry-run
docker compose run --rm cli dispatch-scheduled --limit 50
docker compose run --rm cli image-quality-evaluate --limit 50
```

## Dispatch manuale vs automatico

| Modalità | Come |
|----------|------|
| **Manuale** | UI **⑤ Pubblica** (*Esegui dispatch ora*), API `POST /api/v1/dispatch/run`, CLI `dispatch-scheduled` |
| **Automatica** | Servizio Docker `scheduler` o launchd macOS; default ogni **10 min** (`DISPATCH_INTERVAL_SECONDS=600`) |

Anteprima senza pubblicare: dry-run da UI, `POST /api/v1/dispatch/dry-run` o `dispatch-scheduled --dry-run`.

## Variabili utili (`.env` o shell)

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `WEB_PORT` | `8080` | Porta host UI React (nginx) |
| `STREAMLIT_PORT` | `8501` | Porta host Streamlit legacy |
| `API_PORT` | `8000` | Porta uvicorn nel container `api` |
| `DISPATCH_INTERVAL_SECONDS` | `600` | Intervallo scheduler (10 min) |
| `DISPATCH_LIMIT` | `100` | Max eventi per run |
| `DISPATCH_PLATFORM` | vuoto | `instagram` o `facebook` per filtrare |
| `SOCIAL_AUTOMATION_ROOT` | `/app` | Impostato in compose |
| `API_CORS_ORIGINS` | localhost:5173 | Origini CORS (dev); in prod il browser parla solo a nginx |

In container: lascia `GOOGLE_OAUTH_BROWSER` vuoto (nessun browser).

## Volumi montati

| Host | Container | Contenuto |
|------|-----------|-----------|
| `./output` | `/app/output` | DB SQLite, render, log, `meta_page_token.txt` |
| `./config` | `/app/config` | `schedule.yaml`, categorie, brand |
| `./models` | `/app/models` | Modello ONNX qualità |
| `./credentials.json` | `/app/credentials.json` | OAuth Google (read-only) |
| `./token.json` | `/app/token.json` | Token Google |
| `./canva_token.json` | `/app/canva_token.json` | Token Canva (legacy) |

**Non** includere segreti nell’immagine Docker.

## Log

```bash
docker compose logs -f web
docker compose logs -f api
docker compose logs -f scheduler
```

## Stop

```bash
docker compose down
```

## Sostituisce launchd?

Sì: il servizio `scheduler` equivale al job `com.socialautomation.dispatch-scheduled` su macOS. Non usare entrambi in parallelo sulla stessa installazione (doppia pubblicazione).

## Build multi-architettura (opzionale)

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t social-media-automation:local --target api .
docker buildx build --platform linux/amd64,linux/arm64 -t social-media-automation-web:local --target web .
```

Su Apple Silicon l’immagine `linux/arm64` nativa è la scelta più veloce.
