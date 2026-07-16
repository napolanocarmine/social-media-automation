# Instagram Graph API Scheduling Notes

## Domanda
Qual è il giusto parametro per pubblicare un post futuro su Instagram attraverso le API?

---

Il punto subdolo è che per Instagram Graph API il parametro “giusto” non è sempre documentato in modo coerente tra endpoint, versioni e capability dell’account.

Per i post Instagram pubblicati via:

- `POST /{ig-user-id}/media`
- seguito da `POST /{ig-user-id}/media_publish`

il parametro corretto oggi è:

```text
publish_time
```

NON `scheduled_publish_time`.

Quindi:

```bash
POST /{ig-user-id}/media
```

con:

```text
image_url=...
caption=...
publish_time=UNIX_TIMESTAMP
```

E poi successivamente:

```bash
POST /{ig-user-id}/media_publish
creation_id=...
```

---

# Però c’è una trappola importante

Instagram Graph API NON funziona come Facebook Pages scheduling.

Per Instagram:

- il container `/media` può essere creato con metadata
- ma la pubblicazione differita reale è limitata
- e in molte configurazioni `publish_time` viene ignorato o rifiutato

Meta storicamente ha supportato meglio:

- scheduling Facebook Pages
- scheduling tramite Business Suite
- partner ufficiali

mentre Instagram spesso richiede:

## scheduling applicativo

cioè:

```text
TU salvi il job
TU aspetti l’orario
TU chiami media_publish all’orario
```

che è infatti quello che fanno moltissimi SaaS.

---

# Il tuo errore specifico

Questo:

```json
(#3) User must be on whitelist
```

non indica che il parametro è errato.

Indica invece che:

- la capability che stai usando è gated
- oppure il tuo IG account non è tester dell’app
- oppure l’app è in Development mode
- oppure stai usando una feature riservata partner

Quindi il test non è ancora attendibile sul parametro.

---

# Cosa ti consiglio davvero

## Strategia robusta

### 1. NON usare scheduling nativo IG

Fai:

```text
/media           -> crea container
(media_id salvato)

/media_publish   -> solo quando arriva il momento
```

tramite tuo scheduler locale.

È la soluzione più stabile.

---

# Flusso consigliato

## Creazione draft

```bash
POST https://graph.facebook.com/v25.0/{ig-user-id}/media
```

Params:

```text
image_url
caption
```

Response:

```json
{
  "id": "1789...."
}
```

---

## Scheduler locale

Salvi:

```text
creation_id
publish_at
status
```

nel DB.

---

## Pubblicazione reale

All’orario:

```bash
POST /{ig-user-id}/media_publish
creation_id=...
```

---

# Perché quasi tutti fanno così

Perché:

- prevedibile
- supportato
- non dipende da feature Meta ballerine
- funziona anche se Business Suite cambia comportamento
- evita problemi whitelist

---

# IMPORTANTISSIMO

I media container Instagram:

```text
scadono dopo ~24h
```

Quindi:

## NON puoi creare oggi e pubblicare tra 7 giorni

Devi:

### opzione A (migliore)
Salvare asset e creare il container poco prima della pubblicazione.

oppure

### opzione B
Rigenerare il container automaticamente.

---

# Architettura corretta IG Scheduler

```text
DB
 ├── media_asset
 ├── caption
 ├── publish_at
 └── ig_account

Scheduler
 └── 5 min prima:
       create media container

Publish worker
 └── media_publish
```

Questo è praticamente il pattern usato dai tool seri.

---

# Quindi risposta finale

## Parametro corretto teorico

```text
publish_time
```

## Ma soluzione consigliata reale

NON usare scheduling nativo Instagram.

Usa:

```text
/media
```

poi:

```text
/media_publish
```

all’orario deciso dal tuo scheduler.

---

# Extra: dettaglio poco documentato

Su Instagram Graph API:

- `scheduled_publish_time`
  è più legato al mondo Facebook Pages

mentre:

- `publish_time`
  compare in alcuni flow IG/FB unificati

Ma per IG puro il comportamento è incoerente tra versioni API e account capabilities.

Per questo i partner seri evitano di affidarsi al scheduling server-side Meta per Instagram.

---

# Conclusione sintetica

## Facebook Pages
Supporta uno scheduling “vero” server-side tramite API.

Puoi fare:

```text
published=false
scheduled_publish_time=...
```

e il post resta nei sistemi Meta come scheduled post nativo.

---

## Instagram
NON ha lo stesso modello stabile e completo.

Per IG:

- puoi creare media container
- puoi pubblicare via API
- puoi automatizzare tutto
- MA il concetto di “scheduled post nativo IG” via API pubblica è incompleto/incoerente

Quindi nella pratica:

```text
lo scheduler lo fai tu
```

e all’orario giusto invochi:

```text
/media_publish
```

---

# La differenza architetturale vera

## Facebook

Meta conserva il job:

```text
Meta DB
 └── scheduled post
```

## Instagram

Meta si aspetta spesso:

```text
TUA APP
 └── decide quando pubblicare
```

Instagram Publishing API è più simile a:

> “dammi il contenuto quando vuoi pubblicarlo”

non a:

> “custodisci questo post fino a venerdì alle 18:00”

---

# Quello che fanno i SaaS seri

Tool tipo:

- Buffer
- Later
- Hootsuite
- Metricool

molto spesso usano:

## scheduling proprietario

NON scheduling nativo Instagram.

Perché è:

- più prevedibile
- più debuggabile
- più portabile
- meno fragile alle modifiche Meta

---

# Modello corretto per una tua app

```text
utente programma
    ↓
DB salva job
    ↓
worker/cron
    ↓
create media container
    ↓
media_publish
```

e non:

```text
Meta custodisce il post per te
```

perché su IG quello scenario oggi non è realmente affidabile tramite API pubbliche.
