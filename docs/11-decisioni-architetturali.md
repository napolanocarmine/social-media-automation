# 11 — Decisioni architetturali (ADR)

Architecture Decision Records per le scelte tecniche della migrazione Vercel.

---

## ADR-001: Hosting su Vercel (full vs ibrido)

**Stato:** Accettato  
**Data:** 2026-07-16

### Contesto

Il progetto gira oggi su Docker con SQLite, filesystem locale e scheduler container. L'obiettivo è hostare su Vercel con dashboard, pianificazione e cron dispatch.

### Decisione

**Architettura Vercel-native** con refactor di DB, storage e batch. Non deploy ibrido (Vercel frontend + VPS backend).

### Motivazione

- L'utente è aperto a rivedere l'architettura
- Vercel-native semplifica ops (un solo provider)
- Il refactor è significativo ma fattibile in 4–7 settimane
- L'ibrido aggiungerebbe complessità operativa senza eliminare il refactor

### Conseguenze

- Refactor obbligatorio di `store.py`, `batch_runner.py`, storage
- Vantaggio: scaling automatico, zero manutenzione server
- Rischio: timeout function per job lunghi → mitigato con queue

---

## ADR-002: Database — Neon Postgres

**Stato:** Accettato  
**Data:** 2026-07-16

### Contesto

SQLite non è compatibile con Vercel (filesystem effimero). Serve DB cloud persistente.

### Opzioni valutate

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Neon Postgres** (Vercel Marketplace) | Integrazione nativa, branching preview, serverless driver | Vendor lock-in leggero |
| **Supabase Postgres** | DB + Storage + Auth in uno | Secondo provider, più complesso |
| **Turso** (SQLite edge) | Minimo refactor | Non standard per query complesse |
| **PlanetScale** (MySQL) | Buon DX | MySQL ≠ Postgres, refactor diverso |

### Decisione

**Neon Postgres** via Vercel Marketplace (Vercel-Managed Integration).

### Motivazione

- Integrazione nativa Vercel (billing unificato, env auto-iniettati)
- Preview branch per ogni PR
- Serverless-compatible (connection pooling)
- La doc di migrazione del progetto sorgente menziona già Postgres come epic

### Conseguenze

- Refactor `store.py` (~2000 righe)
- Adapter pattern per transizione graduale
- `psycopg` come driver Python

---

## ADR-003: Storage — Vercel Blob

**Stato:** Accettato  
**Data:** 2026-07-16

### Contesto

Le immagini (originali, processed, thumbnail) vivono su filesystem locale. Serve object storage.

### Opzioni valutate

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Vercel Blob** | Nativo, semplice, stesso billing | Solo Vercel |
| **Supabase Storage** | Integrato con Supabase DB | Secondo provider |
| **AWS S3 / Cloudflare R2** | Standard, economico | Setup manuale |
| **Neon** (solo DB) | — | Non fa storage file |

### Decisione

**Vercel Blob** per storage immagini.

### Motivazione

- Massima semplicità con stack Vercel-only
- `@vercel/blob` SDK + env auto-iniettato
- Per 1–5 GB di foto, costo trascurabile
- Upload diretto possibile (bypass function per file grandi)

### Conseguenze

- Refactor `process_photo.py`, `media.py`, `dispatch_runner.py`
- Path nel DB diventano URL Blob
- Modulo `storage/` con interfaccia astratta (local per dev)

### Reversibilità

Se in futuro si migra a Supabase (ADR-002 revisione), lo storage può migrare con script bulk. L'interfaccia astratta facilita lo switch.

---

## ADR-004: Batch AI — Cron self-queue (fase 1)

**Stato:** Accettato (fase 1), da rivalutare in fase 2  
**Data:** 2026-07-16

### Contesto

Il batch AI usa `subprocess.Popen` per processare N foto in background. Non compatibile con Vercel.

### Opzioni valutate

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Cron self-queue** (1 foto/min) | Zero dipendenze, tutto Vercel | Lento (1 foto/min) |
| **Upstash QStash** | Immediato, HTTP-based | Servizio esterno |
| **Inngest** | Orchestrazione robusta | SDK TypeScript-first |
| **Vercel Workflows** | Nativo, durata illimitata | TypeScript-only |
| **Endpoint sync maxDuration 300** | Semplice | Non scala per batch grandi |

### Decisione

**Fase 1:** Cron self-queue (1 foto per invocazione cron, ogni 1 min).  
**Fase 2:** Upgrade a **Upstash QStash** se la latenza non è accettabile.

### Motivazione

- MVP rapido senza servizi esterni
- Per batch tipici (3–10 foto), 3–10 minuti è accettabile
- QStash come upgrade naturale (Marketplace Vercel, HTTP, Python-friendly)

### Conseguenze

- Batch lento ma funzionale
- `runner_pid` e queue file JSON eliminati
- Stato batch interamente in Postgres

---

## ADR-005: Secrets — Vercel Sensitive Environment Variables

**Stato:** Accettato  
**Data:** 2026-07-16

### Contesto

Token e chiavi API sono oggi in `.env` e file (`token.json`, `credentials.json`). Su Vercel servono secrets gestiti.

### Decisione

**Vercel Sensitive Environment Variables** per tutti i segreti. Nessun file token su disco.

### Motivazione

- Nativo Vercel, zero costo aggiuntivo
- Valore non leggibile dalla dashboard
- Redaction automatica nei build log
- Il progetto già supporta `META_PAGE_ACCESS_TOKEN` da env

### Conseguenze

- `credentials.json` → `GOOGLE_CREDENTIALS_JSON` (env)
- `token.json` → `GOOGLE_REFRESH_TOKEN` (env) o tabella DB
- `meta_page_token.txt` → `META_PAGE_ACCESS_TOKEN` (env)
- Config non-secrets (`config/*.yaml`) restano nel repo

---

## ADR-006: Auth dashboard — Vercel Password Protection

**Stato:** Accettato (fase 1)  
**Data:** 2026-07-16

### Contesto

La dashboard non ha login. In produzione su Vercel serve protezione.

### Opzioni valutate

| Opzione | Complessità | Sicurezza |
|---------|-------------|-----------|
| Vercel Password Protection | Minima | Media |
| Vercel Authentication (SSO) | Bassa | Alta |
| JWT custom in FastAPI | Alta | Alta |
| Cloudflare Access | Media | Alta |

### Decisione

**Fase 1:** Vercel Password Protection.  
**Fase 2 (se necessario):** Vercel Authentication con Google SSO.

### Motivazione

- 2 utenti operativi → password condivisa sufficiente
- Zero codice, attivazione in 1 click
- Il cron Vercel non passa per la protection

---

## ADR-007: Scheduler — Vercel Cron (non loop)

**Stato:** Accettato  
**Data:** 2026-07-16

### Contesto

Il dispatch automatico usa un container Docker con loop infinito (`dispatch-loop.sh`).

### Decisione

**Vercel Cron** con endpoint HTTP protetto da `CRON_SECRET`. Schedule: ogni 15 minuti.

### Motivazione

- L'API dispatch esiste già (`POST /api/v1/dispatch/run`)
- Vercel Cron è il sostituto naturale del loop Docker
- 15 minuti di ritardo max è accettabile per il calendario editoriale

### Conseguenze

- Container `scheduler` eliminato
- Un solo scheduler attivo (regola invariante)
- Endpoint `/api/cron/dispatch` dedicato

---

## ADR-008: Adapter pattern per DB (non SQLAlchemy subito)

**Stato:** Accettato  
**Data:** 2026-07-16

### Contesto

`store.py` ha ~2000 righe con SQL raw SQLite. Serve migrare a Postgres.

### Opzioni

| Opzione | Effort | Rischio |
|---------|--------|---------|
| **Adapter pattern** (Protocol + 2 impl) | 1–2 sett. | Basso |
| **SQLAlchemy ORM** | 3–4 sett. | Medio |
| **Riscrittura completa** | 4+ sett. | Alto |

### Decisione

**Adapter pattern:** interfaccia `Database` con `SqliteDatabase` (dev) e `PostgresDatabase` (prod).

### Motivazione

- Minimo rischio: dev locale continua con SQLite
- Parità funzionale testabile con contract test
- SQLAlchemy valutabile in futuro se lo schema evolve

---

## ADR-009: ONNX quality gate — disabilitato su Vercel

**Stato:** Accettato  
**Data:** 2026-07-16

### Contesto

`onnxruntime` è una dipendenza pesante (~100MB+) usata per il gate qualità immagine opzionale. Non è usata nel flusso Story AI principale (approvazione manuale).

### Decisione

**Disabilitare** `onnxruntime` nel deploy Vercel. `DISPATCH_REQUIRE_QUALITY_PASS=false`.

### Motivazione

- Bundle size: rischio di superare limiti function
- Il flusso Story AI usa approvazione manuale, non ONNX
- Il gate ONNX era già `false` di default nel `.env.example`

### Conseguenze

- Rimuovere `onnxruntime` da `requirements.txt` Vercel
- Mantenere nel repo sorgente per dev locale se necessario

---

## Riepilogo decisioni

| ADR | Decisione | Stato |
|-----|-----------|-------|
| 001 | Vercel-native (non ibrido) | Accettato |
| 002 | Neon Postgres | Accettato |
| 003 | Vercel Blob | Accettato |
| 004 | Cron self-queue → QStash | Accettato (fase 1) |
| 005 | Vercel Sensitive Env Vars | Accettato |
| 006 | Password Protection → SSO | Accettato (fase 1) |
| 007 | Vercel Cron ogni 15 min | Accettato |
| 008 | Adapter pattern DB | Accettato |
| 009 | ONNX disabilitato | Accettato |

### Decisioni aperte (da prendere durante implementazione)

| Tema | Opzioni | Quando decidere |
|------|---------|-----------------|
| Google auth | Service Account vs OAuth Web | M3 (dipende da setup Drive) |
| Meta token | User token vs System User | M3 (dipende da Business Manager) |
| Batch upgrade | Restare su cron vs QStash | M4 (dopo test latenza) |
| SSE vs polling | Polling client vs SSE server | M3 (polling più semplice) |
