# Social Media Automation — Documentazione migrazione Vercel

Documentazione di progetto per la migrazione dell'applicazione **Story Food & Drink** da architettura Docker/SQLite/filesystem locale a stack **Vercel-native**.

> **Repository sorgente (attuale):** `social-media-automation`  
> **Repository target (Vercel):** `social-media-automation-vercel`  
> **Data documentazione:** luglio 2026

---

## Obiettivo

Hostare su Vercel:

1. **Dashboard React** — workflow completo (Seleziona → Output AI → Approva → Pianifica → Pubblica)
2. **API FastAPI** — pianificazione, gestione immagini, configurazione
3. **Cron job** — dispatch periodico verso Meta (Instagram + Facebook)

Con infrastruttura gestita:

- **Postgres** via integrazione Neon (Vercel Marketplace)
- **Object storage** per immagini (Vercel Blob o Supabase Storage)
- **Secrets** via Vercel Sensitive Environment Variables

---

## Indice documenti

| # | Documento | Contenuto |
|---|-----------|-----------|
| 01 | [Visione e architettura target](./01-visione-e-architettura-target.md) | Architettura cloud-native, diagrammi, componenti |
| 02 | [Analisi gap — architettura attuale](./02-analisi-gap-architettura-attuale.md) | Cosa funziona oggi, cosa blocca Vercel |
| 03 | [Postgres — schema e migrazione](./03-postgres-schema-e-migrazione.md) | Schema SQL, mapping SQLite→Postgres, piano migrazione |
| 04 | [Storage media (Blob)](./04-storage-media-blob.md) | Sostituzione `output/`, upload, serving immagini |
| 05 | [Secrets e variabili d'ambiente](./05-secrets-e-variabili-ambiente.md) | Elenco completo env vars per Vercel |
| 06 | [Deploy e configurazione Vercel](./06-vercel-deploy-e-configurazione.md) | `vercel.json`, setup progetto, CI |
| 07 | [Cron dispatch Meta](./07-cron-dispatch-meta.md) | Scheduler, endpoint, sicurezza, timing |
| 08 | [Batch AI e job queue](./08-batch-ai-e-job-queue.md) | Refactor subprocess → queue |
| 09 | [OAuth e autenticazione](./09-oauth-e-autenticazione.md) | Google Drive, Meta, auth dashboard |
| 10 | [Roadmap e milestone](./10-roadmap-milestone.md) | Piano implementazione 4–7 settimane |
| 11 | [Decisioni architetturali (ADR)](./11-decisioni-architetturali.md) | Scelte tecniche documentate |
| 12 | [Checklist go-live](./12-checklist-go-live.md) | Verifiche pre-produzione |

### SQL

| File | Contenuto |
|------|-----------|
| [sql/001_initial_schema.sql](./sql/001_initial_schema.sql) | Schema Postgres iniziale |

---

## Principi guida

1. **Conservare la logica business** in `services/` — non riscrivere da zero
2. **Sostituire l'infrastruttura**, non il dominio applicativo
3. **Un solo scheduler** attivo per evitare doppie pubblicazioni Meta
4. **Secrets mai in repo** — solo Vercel env (Sensitive)
5. **Nessun filesystem persistente** — Postgres + Blob per tutto lo stato

---

## Riferimenti al progetto attuale

| Area | Path nel repo sorgente |
|------|------------------------|
| Frontend React | `frontend/` |
| API FastAPI | `src/social_automation/api/` |
| Logica business | `src/social_automation/services/` |
| Database SQLite | `src/social_automation/db/store.py` |
| Scheduling | `src/social_automation/scheduling/` |
| Meta client | `src/social_automation/meta/` |
| Config brand | `config/brand/` |
| Calendario editoriale | `config/schedule.yaml` |
| Doc esistente | `docs/progetto-completo.md` |

---

## Stima effort

| Milestone | Durata | Output |
|-----------|--------|--------|
| M1 — Fondamenta cloud | 1–2 sett. | Postgres + secrets + deploy base + cron |
| M2 — Storage media | 1–2 sett. | Blob + preview immagini end-to-end |
| M3 — Batch AI + OAuth | 2–3 sett. | Queue batch + OAuth cloud + auth UI |
| **Totale** | **4–7 sett.** | Parità funzionale cloud-native |

Vedi [10-roadmap-milestone.md](./10-roadmap-milestone.md) per il dettaglio.
