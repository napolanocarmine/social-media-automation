# 12 — Checklist go-live

Verifiche da completare prima e dopo il passaggio a produzione su Vercel.

---

## Pre-requisiti infrastruttura

### Vercel

- [ ] Progetto Vercel creato e collegato a repo Git
- [ ] Piano Pro attivo (per cron flessibile e maxDuration)
- [ ] `vercel.json` configurato (rewrites, crons, functions)
- [ ] Deploy Production riuscito senza errori build
- [ ] Password Protection abilitata

### Neon Postgres

- [ ] Integrazione Neon installata da Marketplace
- [ ] `DATABASE_URL` e `DATABASE_URL_UNPOOLED` iniettati
- [ ] Schema eseguito (`sql/001_initial_schema.sql`)
- [ ] Connessione verificata da function (`GET /api/v1/health`)

### Vercel Blob

- [ ] Blob store creato
- [ ] `BLOB_READ_WRITE_TOKEN` iniettato
- [ ] Upload test riuscito
- [ ] URL pubblico accessibile

### Secrets

- [ ] `META_PAGE_ACCESS_TOKEN` configurato (Sensitive)
- [ ] `META_IG_USER_ID` configurato
- [ ] `VISION_API_KEY` configurato (Sensitive)
- [ ] `CRON_SECRET` generato e configurato (Sensitive)
- [ ] `GOOGLE_CREDENTIALS_JSON` o `GOOGLE_SERVICE_ACCOUNT_JSON` configurato
- [ ] `GOOGLE_REFRESH_TOKEN` configurato (se OAuth Web)
- [ ] `API_CORS_ORIGINS` con dominio produzione
- [ ] `DB_BACKEND=postgres`
- [ ] `STORAGE_BACKEND=vercel_blob`
- [ ] Nessun secret nel repo git

---

## Test funzionali — API

### Health e dashboard

- [ ] `GET /api/v1/health` → `{"status": "ok"}`
- [ ] `GET /api/v1/dashboard/stats` → metriche coerenti
- [ ] `GET /api/v1/dashboard/suggested-next-step` → suggerimento valido
- [ ] `GET /api/v1/config/categories` → lista categorie
- [ ] `GET /api/v1/config/dispatch` → config dispatch

### Google Drive

- [ ] `GET /api/v1/drive/assets?category=...&year=...&month=...` → lista foto
- [ ] Thumbnail visibili nella UI Seleziona
- [ ] OAuth: stato "connesso" visibile in dashboard

### Batch AI

- [ ] `POST /api/v1/batches/ai` con 1 asset → batch creato
- [ ] Batch item processato entro 5 minuti
- [ ] `GET /api/v1/batches/{id}` → status `completed`
- [ ] Immagine appare in Output AI con preview
- [ ] Copy generato (`copy_json` presente)
- [ ] Batch 3 foto: tutti e 3 completati
- [ ] Stop batch: `POST /api/v1/batches/{id}/stop` funziona

### Approvazione

- [ ] `GET /api/v1/images/pending-approval` → foto in attesa
- [ ] Preview before/after visibili (Blob URL)
- [ ] `POST /api/v1/images/{id}/approval` → approve funziona
- [ ] `POST /api/v1/images/{id}/approval` → reject funziona
- [ ] Foto approvata appare in Pianifica

### Pianificazione

- [ ] `GET /api/v1/images/plannable` → foto approvate
- [ ] `POST /api/v1/plans/suggest-slot` → slot suggerito rispetta `schedule.yaml`
- [ ] `POST /api/v1/plans` → evento pianificato in DB
- [ ] `GET /api/v1/calendar` → evento visibile nel calendario
- [ ] Reschedule: modifica data/ora funziona
- [ ] Cancel: annullamento funziona
- [ ] Story ricorrente: regola weekly creata

### Dispatch

- [ ] `GET /api/v1/dispatch/due` → eventi scaduti elencati
- [ ] `POST /api/v1/dispatch/dry-run` → anteprima corretta
- [ ] `POST /api/v1/dispatch/run` → pubblicazione manuale funziona
- [ ] Post Instagram pubblicato (verificare su IG)
- [ ] Post Facebook pubblicato (verificare su FB Page)
- [ ] Story pubblicata
- [ ] Gate approvazione: foto non approvata NON pubblicata
- [ ] Evento già pubblicato NON ripubblicato (idempotenza)

### Cron

- [ ] `GET /api/cron/dispatch?secret=...` → 200 con risultato
- [ ] Cron senza secret → 401
- [ ] Cron su preview → 403
- [ ] Vercel Cron esegue automaticamente (verificare in Dashboard → Cron Jobs)
- [ ] Cron dispatch pubblica eventi scaduti entro 15 min

---

## Test funzionali — UI (E2E manuale)

### Workflow completo

- [ ] **Home** → metriche corrette, link ai step funzionanti
- [ ] **① Seleziona** → Drive listing, selezione foto, avvio batch
- [ ] **② Output AI** → preview foto, stato batch, copy visibile
- [ ] **③ Approva** → approve/reject, filtri social/formato/categoria
- [ ] **④ Pianifica** → wizard 2 step, slot suggerito, calendario
- [ ] **⑤ Pubblica** → eventi scaduti, dispatch manuale
- [ ] **Automazione** → prepare-week (dry-run), monitor batch

### UX

- [ ] Pagine responsive (desktop + tablet)
- [ ] Errori API mostrati con messaggio leggibile
- [ ] Loading states visibili durante operazioni lunghe
- [ ] Paginazione funzionante (Drive, Approva, Output)

---

## Test sicurezza

- [ ] Dashboard non accessibile senza password
- [ ] Cron non accessibile senza secret
- [ ] Job endpoint non accessibile senza firma (se QStash)
- [ ] Secrets non visibili nei build log Vercel
- [ ] Secrets non committati nel repo
- [ ] CORS limitato al dominio produzione
- [ ] Nessun endpoint espone token o chiavi in response

---

## Test performance

- [ ] API health < 500ms
- [ ] Dashboard stats < 2s
- [ ] Listing Drive (20 foto) < 5s
- [ ] Preview immagine carica < 3s
- [ ] Dispatch 10 eventi < 60s
- [ ] Batch 1 foto completa < 3 min

---

## Migrazione dati (se DB produzione esistente)

- [ ] Backup SQLite originale (`output/social_automation.db`)
- [ ] Script migrazione eseguito senza errori
- [ ] Conteggio record verificato (images, planning_events, batches)
- [ ] Immagini uploadate su Blob
- [ ] URL Blob nel DB verificati (preview funzionanti)
- [ ] Eventi pianificati futuri preservati
- [ ] Batch in corso marcati `failed` (non migrati)

---

## Cutover

### Prima del go-live

- [ ] Deploy Production verificato
- [ ] Tutti i test sopra passati
- [ ] Operatori informati del nuovo URL
- [ ] Runbook operativo consegnato (rinnovo token, troubleshooting)
- [ ] Scheduler Docker/launchd **disattivato**
- [ ] Verificato che non ci siano altri scheduler attivi

### Go-live

- [ ] DNS/domino configurato (se custom domain)
- [ ] Ultimo deploy Production
- [ ] Cron attivo e prima esecuzione OK
- [ ] Operatore 1: login e workflow test
- [ ] Operatore 2: login e workflow test (parallelo)

### Dopo go-live (24h)

- [ ] Cron dispatch: almeno 4 esecuzioni senza errori
- [ ] Nessun evento duplicato su Meta
- [ ] Nessun errore 5xx nelle function logs
- [ ] Blob storage usage entro budget
- [ ] Neon connection pool stabile (no timeout)

### Dopo go-live (1 settimana)

- [ ] Almeno 1 batch AI completato in produzione
- [ ] Almeno 1 post pubblicato via cron (non manuale)
- [ ] Almeno 1 pianificazione + dispatch end-to-end
- [ ] Token Meta ancora valido
- [ ] Google Drive access ancora funzionante
- [ ] Feedback operatori raccolto

---

## Rollback plan

Se il go-live fallisce:

1. **Riattivare Docker locale** (`docker compose up -d`)
2. **Disattivare Vercel Cron** (rimuovere da `vercel.json`, redeploy)
3. **I dati su Neon restano** — nessuna perdita (Postgres è il nuovo source of truth)
4. **Investigare** errori nei Vercel function logs
5. **Fix + redeploy** quando pronto

### Criteri per rollback

| Condizione | Azione |
|------------|--------|
| API non risponde per > 30 min | Rollback a Docker |
| Dispatch pubblica duplicati | Disattivare cron immediatamente |
| Token Meta scaduto | Refresh token, non rollback |
| Batch AI fallisce sistematicamente | Rollback batch, API resta su Vercel |

---

## Contatti e runbook

| Ruolo | Azione |
|-------|--------|
| Operatore | Usa dashboard Vercel per workflow quotidiano |
| Dev | Monitora Vercel logs + Neon dashboard |
| Token Meta scaduto | Eseguire `meta-refresh-page-token` in locale, aggiornare env |
| Google Drive disconnesso | Ri-autorizzare via dashboard o aggiornare refresh token |
| Dispatch non funziona | Verificare cron logs → token Meta → gate approvazione |

---

## Firma go-live

| Campo | Valore |
|-------|--------|
| Data go-live | _______________ |
| URL produzione | _______________ |
| Versione deploy | _______________ |
| Test E2E | ☐ Passati |
| Operatori formati | ☐ Sì |
| Scheduler locale disattivato | ☐ Sì |
| Approvato da | _______________ |
