# Meta setup (Facebook + Instagram)

Questa guida serve per configurare l'app in modo da pubblicare da `social_automation`
senza passare dalla Business Suite.

## Prerequisiti account

- Facebook Page attiva.
- Account Instagram `Business` o `Creator`.
- IG collegato alla Facebook Page corretta.
- Ruolo admin (o permessi equivalenti) sulla Page.

## 1) Crea app Meta

1. Vai su [Meta for Developers](https://developers.facebook.com/).
2. Crea una nuova app (tipo Business).
3. Aggiungi il prodotto `Facebook Login` (se richiesto per ottenere token utente).
4. Aggiungi permessi per Graph API.

## 2) Permessi da richiedere

Permessi **per pubblicare** (Graph API, non solo elenco Page):

- `pages_manage_posts`
- `pages_read_engagement`
- `instagram_content_publish`

Spesso servono anche:

- `pages_show_list` (per `me/accounts` e OAuth “minimo”)
- `business_management`

**OAuth (`meta-oauth-page-token`) vs Explorer:** nel dialog Facebook Login, Meta accetta solo permessi **validi e abilitati per la tua app**. Se chiedi permessi non ancora approvati o non disponibili per il tipo di app, vedi **«Invalid Scopes»** (messaggio visibile solo agli sviluppatori). Il progetto usa di default `META_OAUTH_SCOPES=pages_show_list` così il login parte; per pubblicare serve comunque un **Page token** con i permessi sopra (tipicamente **Graph API Explorer** in modalità dev + `meta-refresh-page-token`, oppure App Review e poi estendi `META_OAUTH_SCOPES`).

## 3) Ottieni i valori da mettere nel `.env`

Compila questi campi:

- `META_APP_ID`
- `META_APP_SECRET`
- `META_PAGE_ACCESS_TOKEN` **oppure** solo `META_PAGE_TOKEN_FILE` (vedi sotto)
- `META_REDIRECT_URI` (per `meta-oauth-page-token`; default porta `8765`)
- `META_IG_USER_ID`
- `META_GRAPH_VERSION` (es. `v22.0`)

### Token: scadenza e cosa può fare l’app da sola

Meta **non** dà un refresh token illimitato “stile OAuth2” per tutti i flussi. In pratica:

1. **User access token** da Explorer / login: spesso **breve** (ore).
2. Con `META_APP_ID` + `META_APP_SECRET` puoi **scambiarlo** in **long-lived user token** (circa **60 giorni**) tramite `grant_type=fb_exchange_token`.
3. Da quel token long-lived, `me/accounts` restituisce un **Page access token** che per le Page che gestisci è in genere **lungo** (non va rinnovato ogni giorno come il token breve). Scade o smette di funzionare se revochi l’app, cambi password in certi casi, o ruoti i permessi.
4. **Completamente senza browser per anni**: Meta consiglia **System User** nel **Business Manager** con token generato per asset di proprietà (flusso enterprise). È il modello giusto se il server non deve mai aprire un browser.

Questo progetto include un comando che automatizza i punti 2–3 e scrive il Page token su **file** (così cron e `launchd` non devono riscrivere il `.env`):

```bash
cd /path/to/social-media-automation
source .venv/bin/activate
# Una tantum: incolla in .env META_USER_ACCESS_TOKEN col token *utente* da Explorer (con permessi Page).
# Opzionale: META_PAGE_ID se hai più Page.
python -m social_automation meta-refresh-page-token --write-token-file output/meta_page_token.txt
```

Poi nel `.env` imposta:

```env
META_PAGE_TOKEN_FILE=output/meta_page_token.txt
```

`load_settings()` legge quel file e **sovrascrive** `META_PAGE_ACCESS_TOKEN` in memoria se il file esiste. Puoi lasciare vuoto `META_PAGE_ACCESS_TOKEN` nel `.env` se usi solo il file.

### OAuth automatico (browser → Page token, senza Explorer)

Documentazione ufficiale sui tipi di token e sul flusso user → Page:  
[Access Tokens for Meta Technologies](https://developers.facebook.com/documentation/facebook-login/guides/access-tokens).

1. Nel pannello app Meta: prodotto **Facebook Login** → **Impostazioni** → in **URI di reindirizzamento OAuth validi** aggiungi **esattamente** lo stesso valore di `META_REDIRECT_URI`.  
   Meta spesso **non accetta più `http://` su localhost**: usa **HTTPS** (vedi sotto ngrok o mkcert) oppure verifica le impostazioni di sicurezza dell’app.
2. Nel `.env`: `META_APP_ID`, `META_APP_SECRET`, e `META_REDIRECT_URI` (e se serve `META_OAUTH_LISTEN_PORT` con ngrok).
3. Esegui dalla root del progetto:

```bash
python -m social_automation meta-oauth-page-token --write-token-file output/meta_page_token.txt
```

Imposta anche `META_PAGE_TOKEN_FILE=output/meta_page_token.txt` nel `.env` come per `meta-refresh-page-token`.

Si apre il browser: dopo login e consensi, il terminale riceve il callback locale, scambia il `code`, ottiene il Page token e lo scrive nel file. Con più Page usa `--page-id` o `META_PAGE_ID`.

**Cosa non è magico:** quando il long-lived **user** scade (~60 giorni), serve di nuovo login (es. rilancia `meta-oauth-page-token` oppure Explorer + `meta-refresh-page-token`). Per evitare anche quello, passa a **System User** in Business Manager.

### Come ottenere `META_PAGE_ACCESS_TOKEN` (manuale)

1. Ottieni user token con permessi pagina.
2. Scambia in long-lived token (best practice).
3. Deriva page token della Page target.
4. Verifica con:

```bash
PYTHONPATH=src python3 -m social_automation meta-page
```

Se risponde con `id` e `name` pagina, il token e' valido.

Equivalente automatico: dopo `meta-refresh-page-token`, con `META_PAGE_TOKEN_FILE` impostato, lo stesso `meta-page` userà il token dal file.

### Come ottenere `META_IG_USER_ID`

Dal Graph API Explorer o chiamata API sulla pagina:

- recupera Page ID
- leggi campo `instagram_business_account`
- usa l'id come `META_IG_USER_ID`

## 4) Test publish da applicativo

Test publish diretto:

```bash
PYTHONPATH=src python3 -m social_automation publish-test --platform instagram --category food --caption "Test da app"
```

Test scheduler/dispatcher:

```bash
PYTHONPATH=src python3 -m social_automation dispatch-scheduled --dry-run
PYTHONPATH=src python3 -m social_automation dispatch-scheduled --limit 50
```

### Pianificazione da Streamlit e Meta (Business Suite)

Su **«Pianifica immagine» → Salva pianificazione** con social **Facebook** e formato **Post (feed)**:

- i dati restano nel database locale come prima;
- viene anche chiamata la Graph API per **programmare il post sulla Page** (`scheduled_publish_time`), così compare in **Pianificazione contenuti / Business Suite**;
- l’`id` restituito da Meta viene salvato in `planning_events.external_id`: il comando **`dispatch-scheduled` non ripubblica** quel contenuto (evita doppioni quando Meta pubblica da solo all’orario scelto).

**Storie Facebook**: niente programmazione nativa Meta da quel pulsante.

**Instagram (post feed):** «Salva pianificazione» salva **solo nel database** (nessun container Graph anticipato: scadrebbe in ~24h e lo scheduling nativo con `publish_time` + `media_publish` non è affidabile). All’orario pianificato esegui **`dispatch-scheduled`**: l’app crea allora il container e chiama `media_publish` (pattern descritto in [instagram_graph_api_scheduler_notes.md](./instagram_graph_api_scheduler_notes.md)).

Per la programmazione nativa su Page servono permessi adeguati (es. `pages_manage_posts`); se Meta risponde con errori di permesso, usa Explorer + `meta-refresh-page-token` o estendi gli scope OAuth.

## 5) Errori comuni

- `(#10) Application does not have permission`: scope mancanti o app mode non corretta.
- `Unsupported post request`: ID pagina/IG errato o account non collegato.
- Token expired: rigenera/sostituisci `META_PAGE_ACCESS_TOKEN`.
- Publish IG fallita: account IG non Business/Creator o policy API non soddisfatte.
- **Facebook: «non usa una connessione sicura»** (OAuth bloccato): Meta richiede spesso **HTTPS**
  sul redirect. Soluzioni:
  1. **ngrok** (consigliato per provare subito): `ngrok http 8765`, copia l’URL `https://….ngrok-free.app`,
     imposta `META_REDIRECT_URI=https://….ngrok-free.app/oauth/facebook/callback` (stesso URI nell’app Meta),
     `META_OAUTH_LISTEN_PORT=8765`, poi `meta-oauth-page-token`.
  2. **HTTPS su localhost**: installa [mkcert](https://github.com/FiloSottile/mkcert), esegui una tantum `mkcert -install`, poi dalla root del repo `./scripts/gen_meta_oauth_mkcert.sh` (crea `output/meta-oauth-certs/meta-oauth.pem` e `meta-oauth-key.pem`). Imposta `META_REDIRECT_URI=https://127.0.0.1:8765/oauth/facebook/callback`, `META_OAUTH_TLS_CERTFILE` / `META_OAUTH_TLS_KEYFILE` su quei file, e registra **lo stesso** URI https nell’app Meta.
- **«Invalid Scopes»** nel dialog OAuth: riduci gli scope (`.env`: `META_OAUTH_SCOPES=pages_show_list`) oppure aggiungi in Meta i permessi/casi d’uso richiesti; vedi [Permissions](https://developers.facebook.com/docs/facebook-login/permissions). I certificati **non** risolvono questo errore: riguarda solo i permessi richiesti nella URL di login.
- **`CERTIFICATE_VERIFY_FAILED` su `graph.facebook.com`** (dopo il callback OAuth, su `meta-refresh-page-token`, ecc.): di solito un **proxy/VPN** (`HTTPS_PROXY`) che intercetta TLS con una CA non nel bundle di Python. Nel `.env` prova `META_GRAPH_HTTP_TRUST_ENV=false` (connessione senza proxy da variabili d’ambiente). In azienda, imposta `META_GRAPH_HTTP_CA_BUNDLE` al file PEM della CA interna.
