# 05 — Secrets e variabili d'ambiente

Elenco completo delle variabili d'ambiente per il deploy su Vercel, con indicazione di quali vanno marcate come **Sensitive**.

---

## Come funzionano i secrets su Vercel

Vercel non ha un "Vault" separato. I secrets sono:

- **Environment Variables** — criptate a riposo
- **Sensitive Environment Variables** — valore **non leggibile** dalla dashboard dopo la creazione

### Best practice

```bash
# Via CLI — marca come sensitive
vercel env add META_PAGE_ACCESS_TOKEN production --sensitive
vercel env add VISION_API_KEY production --sensitive
vercel env add CRON_SECRET production --sensitive
```

### Policy team (opzionale)

Abilitare **Enforce Sensitive Environment Variables** nelle impostazioni team per forzare il flag Sensitive su tutte le nuove variabili Production/Preview.

---

## Variabili per ambiente

| Legenda | Significato |
|---------|-------------|
| 🔒 | Sensitive (obbligatorio per segreti) |
| 🔄 | Auto-iniettata da integrazione Vercel |
| 📁 | Resta nel repo (non env) |
| ⚙️ | Configurazione non sensibile |

---

## Database (Neon)

| Variabile | Tipo | Ambiente | Note |
|-----------|------|----------|------|
| `DATABASE_URL` | 🔄🔒 | Production, Preview | Pooled — usare a runtime |
| `DATABASE_URL_UNPOOLED` | 🔄🔒 | Production | Solo per migrazioni schema |
| `DB_BACKEND` | ⚙️ | All | `postgres` (prod), `sqlite` (dev locale) |

---

## Storage (Vercel Blob)

| Variabile | Tipo | Ambiente | Note |
|-----------|------|----------|------|
| `BLOB_READ_WRITE_TOKEN` | 🔄🔒 | Production, Preview | Auto da integrazione Blob |
| `STORAGE_BACKEND` | ⚙️ | All | `vercel_blob` (prod), `local` (dev) |

---

## Meta Graph API

| Variabile | Tipo | Sensitive | Note |
|-----------|------|-----------|------|
| `META_APP_ID` | 🔒 | Sì | ID app Meta |
| `META_APP_SECRET` | 🔒 | Sì | Secret app Meta |
| `META_PAGE_ACCESS_TOKEN` | 🔒 | Sì | **Token principale per dispatch** |
| `META_IG_USER_ID` | ⚙️ | No | ID utente IG collegato alla Page |
| `META_PAGE_ID` | ⚙️ | No | ID numerico Facebook Page |
| `META_GRAPH_VERSION` | ⚙️ | No | Default: `v22.0` |
| `META_GRAPH_HTTP_TRUST_ENV` | ⚙️ | No | Default: `true` |
| `META_GRAPH_HTTP_CA_BUNDLE` | ⚙️ | No | Solo se proxy aziendale |

### Token Meta — flusso setup

1. **One-shot in locale:** `python -m social_automation meta-oauth-page-token`
2. Copiare il Page token generato
3. Aggiungere come `META_PAGE_ACCESS_TOKEN` su Vercel (Sensitive)
4. Refresh periodico: schedulare `meta-refresh-page-token` via cron separato (se necessario)

> Non usare `META_PAGE_TOKEN_FILE` su Vercel — il file non persiste.

---

## Google Drive

| Variabile | Tipo | Sensitive | Note |
|-----------|------|-----------|------|
| `GOOGLE_CREDENTIALS_JSON` | 🔒 | Sì | **Intero JSON** OAuth client (sostituisce `credentials.json`) |
| `GOOGLE_REFRESH_TOKEN` | 🔒 | Sì | Refresh token dopo primo OAuth web |
| `GOOGLE_DRIVE_FOLDER_ID` | ⚙️ | No | Opzionale se si usa `categories.yaml` |
| `GOOGLE_OAUTH_BROWSER` | — | — | **Non usare su Vercel** (solo dev locale) |

### Migrazione da file a env

**Prima (locale):**
```
credentials.json  → file su disco
token.json        → file su disco
```

**Dopo (Vercel):**
```bash
# Convertire credentials.json in env var
vercel env add GOOGLE_CREDENTIALS_JSON production --sensitive
# Incollare il contenuto JSON intero (una riga o multiline)

# Dopo OAuth web, salvare refresh token
vercel env add GOOGLE_REFRESH_TOKEN production --sensitive
```

---

## Story AI / Vision API

| Variabile | Tipo | Sensitive | Default | Note |
|-----------|------|-----------|---------|------|
| `VISION_API_KEY` | 🔒 | Sì | — | API key OpenAI-compatible |
| `VISION_MODEL` | ⚙️ | No | `gpt-4o-mini` | Modello vision |
| `VISION_API_BASE_URL` | ⚙️ | No | `https://api.openai.com/v1` | Provider alternativo |
| `VISION_HTTP_TRUST_ENV` | ⚙️ | No | eredita Meta | TLS/proxy |
| `VISUAL_PRODUCE_MODE` | ⚙️ | No | `generative` | `generative` \| `pixel` |
| `VISUAL_IMAGE_BACKEND` | ⚙️ | No | `responses` | Backend edit AI |
| `VISUAL_RESPONSES_MODEL` | ⚙️ | No | `gpt-5.5` | Modello mainline |
| `VISUAL_RESPONSES_IMAGE_MODEL` | ⚙️ | No | `gpt-image-1.5` | Modello immagine |
| `VISUAL_REVIEW_ENABLED` | ⚙️ | No | `false` | Gate visual review |
| `VISUAL_USE_AI_IMAGE_EDIT` | ⚙️ | No | `false` | Edit AI vs Pillow |

Vedi `.env.example` nel repo sorgente per l'elenco completo delle variabili `VISUAL_*`.

---

## Dispatch e Cron

| Variabile | Tipo | Sensitive | Default | Note |
|-----------|------|-----------|---------|------|
| `CRON_SECRET` | 🔒 | Sì | — | **Generare:** `openssl rand -hex 32` |
| `DISPATCH_REQUIRE_APPROVAL` | ⚙️ | No | `true` | Gate approvazione |
| `DISPATCH_REQUIRE_QUALITY_PASS` | ⚙️ | No | `false` | Gate ONNX |
| `DISPATCH_REQUIRE_VISION_PASS` | ⚙️ | No | `true` | Gate vision brand |
| `DISPATCH_LIMIT` | ⚙️ | No | `100` | Max eventi per run cron |
| `DISPATCH_PLATFORM` | ⚙️ | No | *(vuoto)* | `instagram` \| `facebook` \| tutti |

---

## Applicazione

| Variabile | Tipo | Sensitive | Default | Note |
|-----------|------|-----------|---------|------|
| `APP_TIMEZONE` | ⚙️ | No | `Europe/Rome` | Fuso pianificazione |
| `API_CORS_ORIGINS` | ⚙️ | No | dominio Vercel | Es: `https://social.vercel.app` |
| `SOCIAL_AUTOMATION_ROOT` | — | — | — | **Non necessario su Vercel** |
| `SCHEDULE_CONFIG_PATH` | 📁 | — | `config/schedule.yaml` | Nel repo |
| `STORY_SYSTEM_PATH` | 📁 | — | `config/brand/story_system.md` | Nel repo |
| `STORY_BUSINESS_RULES_PATH` | 📁 | — | `config/brand/story_business_rules.md` | Nel repo |
| `STORY_AGENT_CONFIG_PATH` | 📁 | — | `config/brand/story_agent.md` | Nel repo |

---

## Auth dashboard (da implementare)

| Variabile | Tipo | Sensitive | Note |
|-----------|------|-----------|------|
| `AUTH_MODE` | ⚙️ | No | `vercel_protection` \| `api_key` \| `jwt` |
| `API_KEY` | 🔒 | Sì | Se `AUTH_MODE=api_key` |
| `JWT_SECRET` | 🔒 | Sì | Se `AUTH_MODE=jwt` |

### Opzione semplice (M1)

Usare **Vercel Password Protection** (Settings → Deployment Protection) senza variabili aggiuntive.

---

## Variabili da NON usare su Vercel

| Variabile | Motivo |
|-----------|--------|
| `DB_PATH` | Sostituito da `DATABASE_URL` |
| `GOOGLE_CREDENTIALS_PATH` | Sostituito da `GOOGLE_CREDENTIALS_JSON` |
| `GOOGLE_TOKEN_PATH` | Sostituito da `GOOGLE_REFRESH_TOKEN` |
| `META_PAGE_TOKEN_FILE` | Sostituito da `META_PAGE_ACCESS_TOKEN` |
| `META_OAUTH_LISTEN_PORT` | OAuth localhost non applicabile |
| `META_REDIRECT_URI` (localhost) | Solo per setup one-shot locale |
| `GOOGLE_OAUTH_BROWSER` | Solo dev macOS |
| `DISPATCH_INTERVAL_SECONDS` | Sostituito da Vercel Cron schedule |
| `STREAMLIT_PORT` | Streamlit deprecato |

---

## Template `.env.example` per Vercel

```env
# === Database (auto da Neon integration) ===
# DATABASE_URL=
# DATABASE_URL_UNPOOLED=
DB_BACKEND=postgres

# === Storage (auto da Blob integration) ===
# BLOB_READ_WRITE_TOKEN=
STORAGE_BACKEND=vercel_blob

# === Meta ===
META_APP_ID=
META_APP_SECRET=
META_PAGE_ACCESS_TOKEN=
META_IG_USER_ID=
META_GRAPH_VERSION=v22.0

# === Google Drive ===
GOOGLE_CREDENTIALS_JSON=
GOOGLE_REFRESH_TOKEN=

# === Story AI ===
VISION_API_KEY=
VISION_MODEL=gpt-4o-mini

# === Dispatch / Cron ===
CRON_SECRET=
DISPATCH_REQUIRE_APPROVAL=true
DISPATCH_LIMIT=100

# === App ===
APP_TIMEZONE=Europe/Rome
API_CORS_ORIGINS=https://your-app.vercel.app
```

---

## Checklist secrets

- [ ] Generare `CRON_SECRET` con `openssl rand -hex 32`
- [ ] Aggiungere tutti i token Meta come Sensitive
- [ ] Convertire `credentials.json` → `GOOGLE_CREDENTIALS_JSON`
- [ ] Ottenere `GOOGLE_REFRESH_TOKEN` via OAuth web
- [ ] Aggiungere `VISION_API_KEY` come Sensitive
- [ ] Verificare che Neon e Blob iniettino le variabili automaticamente
- [ ] Configurare `API_CORS_ORIGINS` con dominio produzione
- [ ] Abilitare Vercel Password Protection (o auth alternativa)
- [ ] **Non committare** nessun secret nel repo
- [ ] Verificare redaction nei build log (Sensitive vars ≥ 32 char)
