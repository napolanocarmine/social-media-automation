# Social media automation

Pipeline principale **Story Food & Drink**: **Google Drive** → **Story AI** (ritocco fotografico leggero + copy) → **export foto** (IG/FB/story) → **pianificazione** su **Instagram** e **Facebook** tramite Meta Graph API.

Il modulo `canva/` resta nel repo come legacy opzionale; il flusso default non lo usa più.

## Struttura

- `config/` — esempi di calendario (`schedule.example.yaml`) e categorie Drive (`categories.example.yaml`).
- `src/social_automation/` — pacchetto Python:
  - `drive/` — OAuth2 desktop + elenco/download immagini per cartella.
  - `brand/` — Story AI Assistant (knowledge base, ritocco JSON, copy pack).
  - `processing/` — crop e ritocchi Pillow da parametri AI.
  - `canva/` — client Canva Connect (legacy, opzionale).
  - `meta/` — client IG/FB (publish e scheduling FB).
  - `validation/` — gate vision brand (OpenAI-compatible).
  - `scheduling/` — slot editoriali, dispatch con gate, workflow `prepare-week`.
  - `workflow/` — `process_photo` (Drive→Story AI) e `render` Canva legacy.
  - `pipeline/` — orchestrazione e contesto a stati.
  - `cli.py` — comandi Drive/Story AI/Meta + dispatch schedulazione.

## Setup rapido

```bash
cd /path/to/social-media-automation
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
# oppure, con frontend Streamlit:
# pip install -e ".[ui]"
cp .env.example .env
# Opzionale: copia gli example in config operativi
cp config/schedule.example.yaml config/schedule.yaml
cp config/categories.example.yaml config/categories.yaml
```

### Docker (web React + API + scheduler)

```bash
./scripts/docker-init.sh
# OAuth e .env come sopra (consigliato sul host prima del primo avvio)
docker compose build
docker compose up -d
# Web UI: http://localhost:8080
./scripts/smoke-e2e.sh
```

Dettagli, volumi, Tailscale e Streamlit legacy: [docs/docker.md](docs/docker.md).

### Frontend React + API (sviluppo)

```bash
pip install -e ".[api,dev]"
uvicorn social_automation.api.main:app --reload --port 8000

cd frontend && npm install && npm run dev
# http://localhost:5173 — proxy /api → :8000
```

Migrazione e stato avanzamento: [docs/migrazione-fe-react.md](docs/migrazione-fe-react.md).

Verifica caricamento schedule:

```bash
python -m social_automation --show-schedule config/schedule.example.yaml
```

Dispatch manuale eventi pianificati (senza attendere lo scheduler automatico):

```bash
PYTHONPATH=src python3 -m social_automation dispatch-scheduled --dry-run
PYTHONPATH=src python3 -m social_automation dispatch-scheduled --limit 50
```

Oppure dalla UI React: **⑤ Pubblica** → *Esegui dispatch ora* / *Anteprima (dry-run)*.

Il dispatch rispetta i gate configurati nel `.env` (`DISPATCH_REQUIRE_APPROVAL`, `DISPATCH_REQUIRE_QUALITY_PASS`, `DISPATCH_REQUIRE_VISION_PASS`): eventi non idonei vengono registrati come `skipped` senza pubblicare.

Workflow settimanale automatico (processa foto → approvazione Story AI → pianificazione slot con caption):

```bash
cp config/schedule.example.yaml config/schedule.yaml
# VISION_API_KEY + VISION_MODEL nel .env
PYTHONPATH=src python3 -m social_automation prepare-week --dry-run
PYTHONPATH=src python3 -m social_automation prepare-week --days 7
```

Processa una singola foto (Drive o file locale):

```bash
PYTHONPATH=src python3 -m social_automation story-process --category food --platform instagram
PYTHONPATH=src python3 -m social_automation story-process --category food --source output/drive_abc.jpg
```

### Meta: Page token senza copiarlo ogni volta nel `.env`

1. Metti nel `.env` `META_APP_ID`, `META_APP_SECRET` e (solo se usi Explorer) `META_USER_ACCESS_TOKEN`.
2. **OAuth nel browser** (`meta-oauth-page-token`): in Meta → Facebook Login → **URI di reindirizzamento OAuth validi** aggiungi lo stesso `META_REDIRECT_URI` del `.env`.  
   Se compare *«non usa una connessione sicura»*, Meta richiede **HTTPS** sul redirect: usa **ngrok** (`ngrok http 8765`, poi `META_REDIRECT_URI=https://….ngrok-free.app/oauth/facebook/callback` e `META_OAUTH_LISTEN_PORT=8765`) oppure **mkcert** + `META_OAUTH_TLS_CERTFILE` / `META_OAUTH_TLS_KEYFILE` (dettagli in `docs/meta-setup.md`).

```bash
PYTHONPATH=src python3 -m social_automation meta-oauth-page-token --write-token-file output/meta_page_token.txt
```

3. **Con token utente già copiato da Explorer**: `meta-refresh-page-token`.

```bash
PYTHONPATH=src python3 -m social_automation meta-refresh-page-token --write-token-file output/meta_page_token.txt
```

4. Imposta `META_PAGE_TOKEN_FILE=output/meta_page_token.txt` nel `.env`.

Documentazione ufficiale sui token: [Access Tokens for Meta Technologies](https://developers.facebook.com/documentation/facebook-login/guides/access-tokens).

### Google Drive

1. In [Google Cloud Console](https://console.cloud.google.com/): **API e servizi** → abilita **Google Drive API**.
2. **Credenziali** → **Crea credenziali** → **ID client OAuth** → tipo **Desktop** → scarica il JSON e salvalo come `credentials.json` nella root del progetto (o imposta `GOOGLE_CREDENTIALS_PATH` nel `.env`).
3. **Schermata di consenso OAuth**: se l’app è in test, aggiungi il tuo utente Google come **tester**.
4. Primo login (salva `token.json`). Di default si apre il **browser predefinito** di sistema. Su macOS per usare **Safari**: `GOOGLE_OAUTH_BROWSER=safari` nel `.env`, oppure `--browser safari` da riga di comando.

```bash
python -m social_automation drive-auth --browser safari
# oppure, senza flag, se GOOGLE_OAUTH_BROWSER=safari nel .env:
python -m social_automation drive-auth
```

5. Elenco immagini in una cartella (ID dall’URL Drive `.../folders/QUESTO_ID`):

```bash
python -m social_automation drive-list-images --folder-id CARTELLA_ID
```

6. Elenco ricorsivo da cartella root (es. `anno/mese/categoria/...`), con inferenza categoria dal path:

```bash
python -m social_automation drive-list-images-recursive --folder-id ROOT_ID --categories food,peppe,beer
```

7. Elenco immagini ordinate per recency da struttura `anno/mese/categoria`:

```bash
python -m social_automation drive-list-recent --folder-id ROOT_ID --categories food,beer,peppe,locale --categories-config config/categories.yaml --limit 100
```

### Canva OAuth

1. Nel `.env` imposta:
   - `CANVA_CLIENT_ID`
   - `CANVA_CLIENT_SECRET`
   - `CANVA_REDIRECT_URI` (consigliato: `http://127.0.0.1:8080/callback`)
2. Nella tua integrazione Canva aggiungi lo stesso redirect URL tra gli **Authorized redirects**.
3. Esegui OAuth e salva token locale:

```bash
python -m social_automation canva-auth
```

Se vuoi evitare l'apertura automatica del browser:

```bash
python -m social_automation canva-auth --no-browser
```

Verifica token Canva (richiede scope `profile:read`):

```bash
python -m social_automation canva-profile
```

Render test (seleziona asset recente da Drive per categoria business + template Canva):

```bash
python -m social_automation canva-render-test --folder-id ROOT_ID --platform instagram --category boss
```

Render di una **storia** (stesso template per IG e FB, formato verticale 9:16):

```bash
python -m social_automation canva-render-test --folder-id ROOT_ID --platform instagram --format story --category boss
python -m social_automation canva-render-test --folder-id ROOT_ID --platform facebook --format story --category boss
```

Prima del render test:

1. configura `config/categories.yaml` con alias corretti;
2. configura `config/canva.yaml` con i template ID reali Canva:
   - `templates.instagram.default_template_id` per i post IG;
   - `templates.facebook.default_template_id` per i post FB;
   - `templates.story.default_template_id` per le storie (condiviso IG/FB);
   - eventuali `category_template_overrides.<categoria>.{instagram,facebook,story}`.
3. assicurati che `canva_token.json` sia presente.

Nota: i render vengono salvati in sottocartelle dedicate:

- `output/canva-rendered/ig` per Instagram (post)
- `output/canva-rendered/fb` per Facebook (post)
- `output/canva-rendered/stories` per le storie (cartella unica IG + FB; il
  suffisso `_instagram_story` / `_facebook_story` distingue la piattaforma di
  destinazione e mantiene il tracking separato in DB).

La modalità **placeholder** salva una copia dell'immagine nelle stesse cartelle.
I metadati non vengono più esportati in file JSON: sono salvati nel database SQLite.

### Frontend Streamlit (legacy, opzionale)

> **Deprecato:** l’UI operativa è **React** (`frontend/` + FastAPI). Streamlit resta per rollback temporaneo.

```bash
pip install -e ".[ui]"
streamlit run src/social_automation/web/app.py
# Docker legacy: docker compose --profile streamlit up -d ui-legacy  → :8501
```

La pagina Streamlit consente di:

- navigare con menu `☰` a destra tra:
  - `Rendering`
  - `Approvazione pubblicazione`
  - `Pianifica immagine`
  - `Prepara settimana`
  - `Calendario pianificazione`
  - `Dispatch schedulazione`
- selezionare categoria, piattaforma e **formato** (`Post` feed o `Story` 9:16);
- eseguire il render Drive -> Canva (saltando automaticamente asset già renderizzati
  per la stessa piattaforma e formato);
- vedere preview dell'ultimo render;
- sfogliare tre gallerie: `Instagram (post)`, `Facebook (post)` e
  `Stories (IG + FB)` (cartella unica condivisa);
- vedere gli eventi scaduti pronti alla pubblicazione e avviare dispatch reale o dry-run;
- in **Pianifica immagine** (post) suggerire il prossimo slot libero da `config/schedule.yaml`;
- eseguire **Prepara settimana** per automatizzare render, gate qualità/vision e pianificazione.

Le **story** si pubblicano tramite regole ricorrenti/one-shot e `dispatch-scheduled` (Graph API `media_type=STORIES`).

## Scheduler automatico su macOS (launchd)

Per pubblicare in automatico senza intervento manuale, esegui `dispatch-scheduled` ogni **10 minuti** (configurabile con `DISPATCH_INTERVAL_SECONDS=600`).

1. Copia il template:

```bash
cp config/launchd/com.socialautomation.dispatch-scheduled.plist.example ~/Library/LaunchAgents/com.socialautomation.dispatch-scheduled.plist
```

2. Sostituisci i placeholder nel file copiato:
   - `__PROJECT_ROOT__` con path assoluto del progetto
   - `__PYTHON_BIN__` con il python del tuo ambiente (es. `.venv/bin/python`)

3. Carica il job:

```bash
launchctl unload ~/Library/LaunchAgents/com.socialautomation.dispatch-scheduled.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.socialautomation.dispatch-scheduled.plist
launchctl start com.socialautomation.dispatch-scheduled
```

4. Controlla log:

```bash
tail -f output/logs/dispatch-scheduled.log
tail -f output/logs/launchd-dispatch.err.log
```

Lo script usato dal job e' `scripts/dispatch_scheduled.sh`.

### Database locale (SQLite)

L'app salva automaticamente lo stato render in `DB_PATH` (default: `output/social_automation.db`):

- `images`: … `is_valid_for_publication`, `vision_eval_pass`, `vision_eval_reason`;
- `metadata`: una riga per ogni render con le colonne principali dei metadati Canva
  (`platform`, `media_format`, `template_id`, `canvas_width`, `asset_id`, `design_id`,
  `mode`, ecc.). Il campo `media_format` distingue `post` da `story`.
- `planning_events`: storico append-only per pianificazione/pubblicazione
  (`platform`, `event_type`, `scheduled_for`, `external_id`, `detail`).
- `batches` / `batch_items`: anche le run di rendering hanno `media_format`
  per filtrare il monitor batch tra post e storie.

Il database viene aggiornato da:

- `canva-render-test`
- `publish-test` (anche `--dry-run`)
- `prepare-week`
- `dispatch-scheduled`
- frontend Streamlit

## Configurazione Meta

Checklist completa di app, permessi e chiavi in:

- `docs/meta-setup.md`

## Prossimi step di implementazione

1. ~~Drive: OAuth desktop, `credentials.json`, token; `files.list` per cartelle categoria.~~
2. ~~Canva: OAuth + chiamate API per template/export.~~
3. ~~Meta: Page token, `instagram_content_publish`, scheduling.~~
4. ~~Validazione: provider vision + prompt brand.~~
5. Caption/hashtag da template per categoria.
6. Notifiche su fallimenti dispatch (Telegram/Slack).

Non committare `.env`, token o `credentials.json`.
