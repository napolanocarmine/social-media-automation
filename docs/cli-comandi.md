# Riferimento rapido: comandi CLI

Tutti i comandi partono dalla **root del repository** e usano il modulo Python del progetto.

**Prefisso consigliato** (con venv locale):

```bash
cd /Users/cnapolano001/Desktop/social-media-automation
PYTHONPATH=src .venv/bin/python -m social_automation <COMANDO> [opzioni]
```

**Alternativa** (se il pacchetto è installato in modo editabile e `social_automation` è sul `PYTHONPATH`):

```bash
.venv/bin/python -m social_automation <COMANDO> [opzioni]
```

**Aiuto generale** su un comando:

```bash
PYTHONPATH=src .venv/bin/python -m social_automation <COMANDO> --help
```

Variabili d’ambiente: vedi `.env` / `.env.example`. **Non committare** token o segreti.

---

## Meta: rigenerare il Page access token

Hai due strade principali.

### 1) OAuth nel browser (consigliato se vuoi nuovi permessi / token “pulito”)

Apre il dialog Facebook, salva il **Page token** su file (default `output/meta_page_token.txt` se così configurato in `.env`).

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-oauth-page-token --graph-no-proxy
```

Opzioni utili:

| Opzione | Effetto |
|--------|---------|
| `--no-browser` | Stampa solo l’URL OAuth da aprire a mano |
| `--page-id <ID>` | Forza la Page se ne hai più di una |
| `--write-token-file path` | File dove salvare solo il token (default spesso `output/meta_page_token.txt`) |
| `--oauth-rerequest` | `auth_type=rerequest`: Meta mostra di nuovo la schermata permessi (utile dopo aver esteso `META_OAUTH_SCOPES` nel `.env`) |
| `--scopes a,b,c` | Scope separati da virgola (se omesso: `META_OAUTH_SCOPES` dal `.env`) |
| `--graph-no-proxy` | Ignora `HTTP_PROXY`/`HTTPS_PROXY` verso Graph (TLS/proxy) |

**Prima di rifare OAuth** (opzionale ma utile se il file token confonde):

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-clear-page-token
# poi con conferma:
PYTHONPATH=src .venv/bin/python -m social_automation meta-clear-page-token --yes
```

`meta-clear-page-token` **cancella solo i file locali**; non revoca il token lato Meta.

### 2) Refresh da user token (cron / senza browser)

Scambia il **user access token** in long-lived (salvo `--skip-exchange`), chiama `me/accounts`, scrive il **Page token** su file.

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-refresh-page-token --graph-no-proxy
```

Richiede nel `.env` (o equivalente) almeno: `META_APP_ID`, `META_APP_SECRET`, `META_USER_ACCESS_TOKEN` valido con accesso alle Page; oppure passa `--user-token`.

| Opzione | Effetto |
|--------|---------|
| `--user-token <token>` | User token (se omesso: `META_USER_ACCESS_TOKEN`) |
| `--page-id <ID>` | Page target |
| `--skip-exchange` | Non chiamare `fb_exchange_token` |
| `--write-token-file path` | Destinazione del Page token |
| `--print-token` | Stampa il token in chiaro su stdout (attenzione ai log) |
| `--graph-no-proxy` | Come sopra |

---

## Meta: verifiche e debug

### Page token e profilo Page

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-page
```

Verifica che il Page token sia valido e stampa **id/nome** della Facebook Page.

### Scope e scadenza del token (`debug_token`)

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-debug-token --graph-no-proxy
```

Con token esplicito (raro):

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-debug-token --token "EAAG..." --graph-no-proxy
```

Serve `META_APP_ID` + `META_APP_SECRET` nel `.env`.

### Post programmati sulla Page (Facebook)

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-scheduled-posts --limit 25 --graph-no-proxy
```

### Ottenere `META_IG_USER_ID` (Instagram Business collegato alla Page)

Dalla root del repo. Esegue `GET /{page-id}?fields=instagram_business_account{id,username}` con le stesse credenziali del progetto:

```bash
PYTHONPATH=src .venv/bin/python -c "
import json
import sys
import httpx
from social_automation.settings import load_settings
from social_automation.meta.graph_httpx import graph_httpx_tls_params
from social_automation.meta.client import MetaClient

s = load_settings()
tok = s.meta_page_access_token.strip()
if not tok:
    sys.exit('META_PAGE_ACCESS_TOKEN mancante (o META_PAGE_TOKEN_FILE non valido).')
gv = (s.meta_graph_version or 'v22.0').strip().lstrip('/') or 'v22.0'
base = f'https://graph.facebook.com/{gv}'
m = MetaClient(tok, '', graph_version=gv, settings=s)
page_id = m.get_page_id()
with httpx.Client(**graph_httpx_tls_params(s)) as c:
    r = c.get(
        f'{base}/{page_id}',
        params={'fields': 'instagram_business_account{id,username}', 'access_token': tok},
        timeout=30.0,
    )
if r.status_code >= 400:
    print(r.text, file=sys.stderr)
    sys.exit(1)
j = r.json()
ig = j.get('instagram_business_account') or {}
iid = str(ig.get('id') or '').strip()
if not iid:
    print(json.dumps(j, indent=2, ensure_ascii=False))
    sys.exit('Nessun instagram_business_account: collega Instagram professionale alla Page.')
print('META_IG_USER_ID=' + iid)
if ig.get('username'):
    print('username=' + str(ig['username']))
"
```

Se esce “Nessun instagram_business_account”, collega l’account Instagram **professionale** alla Page in Meta Business Suite / impostazioni Pagina, poi ripeti.

### Test parametri scheduling su Instagram (`/media`, senza pubblicare)

Solo creazione **container**; **non** chiama `media_publish`. Serve `--image-url` HTTPS **pubblico**.

**URL immagine:** deve rispondere con un file immagine (`image/jpeg`, `image/png`, …). **Non** usare link di redirect Google (`google.com/url?...`), pagine prodotto/sito (HTML) o URL che richiedono cookie/login: Meta riceve HTML o un redirect e la creazione del media fallisce. Usa un link **diretto** al file (es. CDN o `upload.wikimedia.org/...`).

Richiede anche **`META_IG_USER_ID`** valorizzato nel `.env` (account Instagram professionale collegato alla Page).

Baseline (campi normali):

```bash
PYTHONPATH=src .venv/bin/python -m social_automation meta-test-ig-media-params \
  --image-url 'https://esempio.com/immagine.jpg' \
  --graph-no-proxy
```

Con parametro extra (es. `publish_time` tra 2 ore):

```bash
FUTURO=$(($(date -u +%s) + 7200))
PYTHONPATH=src .venv/bin/python -m social_automation meta-test-ig-media-params \
  --image-url 'https://esempio.com/immagine.jpg' \
  --unix-time "$FUTURO" \
  --extra-param publish_time \
  --graph-no-proxy
```

---

## Meta: pubblicazione e pianificazione da pipeline

### Pubblicazione end-to-end di test (Drive → Canva → Meta)

```bash
PYTHONPATH=src .venv/bin/python -m social_automation publish-test \
  --platform facebook \
  --category food \
  --caption "Test"
```

Per Instagram: `--platform instagram` (serve `META_IG_USER_ID` nel `.env`).

| Opzione | Effetto |
|--------|---------|
| `--dry-run` | Drive + Canva, **nessuna** chiamata Meta |
| `--placeholder` | Salta Canva, copia file locale |
| `--format post` / `story` | Formato (storie: vedi help del comando) |

### Dispatcher: eventi pianificati nel DB → Meta

```bash
PYTHONPATH=src .venv/bin/python -m social_automation dispatch-scheduled --dry-run
PYTHONPATH=src .venv/bin/python -m social_automation dispatch-scheduled --limit 50
```

| Opzione | Effetto |
|--------|---------|
| `--platform instagram` / `facebook` | Filtra piattaforma |
| `--dry-run` | Elenca senza pubblicare |

**Instagram:** per i post feed pianificati da Streamlit, la pubblicazione Graph avviene qui all’orario (non su «Salva pianificazione»). Vedi [instagram_graph_api_scheduler_notes.md](./instagram_graph_api_scheduler_notes.md).

---

## Google Drive

| Comando | Scopo |
|--------|--------|
| `drive-auth` | Primo login OAuth Drive → salva `token.json` |
| `drive-list-images` | Elenco immagini in una cartella (non ricorsivo) |
| `drive-list-images-recursive` | Elenco ricorsivo |
| `drive-list-recent` | Ricorsivo, ordinato per data (più recenti prima) |

Esempio:

```bash
PYTHONPATH=src .venv/bin/python -m social_automation drive-auth
```

---

## Canva

| Comando | Scopo |
|--------|--------|
| `canva-auth` | OAuth Canva |
| `canva-profile` | Verifica token / profilo |
| `canva-render-test` | Un asset Drive recente → render di test in `output/` |

Esempio render:

```bash
PYTHONPATH=src .venv/bin/python -m social_automation canva-render-test \
  --platform instagram \
  --category birra
```

---

## Pianificazione e dispatch

| Comando | Scopo |
|--------|--------|
| `prepare-week` | Workflow settimanale: slot liberi → render/immagini → qualità/vision → pianifica |
| `dispatch-scheduled` | Pubblica eventi scaduti e regole story (con gate approvazione/qualità/vision) |
| `image-quality-evaluate` | Backfill valutazione ONNX su `images` |

Esempi:

```bash
cp config/schedule.example.yaml config/schedule.yaml
PYTHONPATH=src .venv/bin/python -m social_automation prepare-week --dry-run
PYTHONPATH=src .venv/bin/python -m social_automation prepare-week --days 7

PYTHONPATH=src .venv/bin/python -m social_automation dispatch-scheduled --dry-run
PYTHONPATH=src .venv/bin/python -m social_automation dispatch-scheduled --ignore-gates
```

Gate dispatch (`.env`): `DISPATCH_REQUIRE_APPROVAL`, `DISPATCH_REQUIRE_QUALITY_PASS`, `DISPATCH_REQUIRE_VISION_PASS`.

Vision brand: `VISION_API_KEY`, `VISION_MODEL`; prompt in `config/vision_brand.yaml`.

---

## TLS / proxy verso `graph.facebook.com`

Se compaiono errori tipo `CERTIFICATE_VERIFY_FAILED` o proxy MITM:

1. Nel `.env`: `META_GRAPH_HTTP_TRUST_ENV=false` **oppure**
2. Aggiungi `--graph-no-proxy` ai comandi Meta che lo supportano (OAuth, refresh, debug, scheduled-posts, test IG, ecc.).

---

## Documentazione correlata

- Docker (UI + scheduler): [docker.md](./docker.md)
- Setup Meta più ampio: [meta-setup.md](./meta-setup.md)
