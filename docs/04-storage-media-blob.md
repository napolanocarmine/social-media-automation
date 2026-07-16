# 04 — Storage media (Blob)

Piano per sostituire il filesystem locale `output/` con **object storage** compatibile Vercel.

---

## Problema

Oggi tutte le immagini vivono su disco:

```
output/
├── drive_{file_id}.jpg       # Download grezzo da Drive
├── processed/ig/             # Ritoccate per Instagram post
├── processed/fb/             # Ritoccate per Facebook post
├── processed/stories/        # Ritoccate per story
└── (altri path in images.path, original_path, generated_image_path)
```

Su Vercel:
- Nessun disco persistente
- `/tmp` disponibile solo per la durata della function
- Le immagini devono essere su storage esterno con URL pubblici o signed

---

## Opzioni storage

| Provider | Integrazione Vercel | Pro | Contro |
|----------|---------------------|-----|--------|
| **Vercel Blob** | Nativa (Marketplace) | Semplice, stesso billing | Solo su Vercel, costo per GB |
| **Supabase Storage** | Marketplace | DB + storage insieme | Secondo provider da gestire |
| **AWS S3 / R2** | Manuale (env vars) | Standard, economico | Setup più complesso |
| **Neon** (solo DB) | Già scelto per Postgres | — | Non fa storage file |

### Raccomandazione

**Vercel Blob** per semplicità, oppure **Supabase Storage** se si sceglie Supabase come alternativa a Neon (vedi [11-decisioni-architetturali.md](./11-decisioni-architetturali.md)).

---

## Struttura Blob target

```
{blob-store}/
├── originals/
│   └── drive/{file_id}.jpg
├── processed/
│   ├── ig/{image_id}.jpg
│   ├── fb/{image_id}.jpg
│   └── stories/{image_id}.jpg
└── thumbnails/
    └── drive/{file_id}.jpg
```

### Convenzione URL nel DB

| Colonna `images` | Contenuto target | Esempio |
|------------------|------------------|---------|
| `path` | URL processed principale | `https://xxx.blob.vercel-storage.com/processed/ig/42.jpg` |
| `original_path` | URL originale Drive | `https://xxx.blob.vercel-storage.com/originals/drive/abc123.jpg` |
| `generated_image_path` | URL output AI edit | `https://xxx.blob.vercel-storage.com/processed/ig/42-ai.jpg` |

---

## Flussi di upload

### 1. Download Drive → Blob (batch AI)

```python
# workflow/process_photo.py (target)
async def process_drive_asset(...):
    # 1. Download bytes da Drive API
    image_bytes = drive_client.download(asset.file_id)

    # 2. Upload originale su Blob
    original_url = await blob_store.upload(
        key=f"originals/drive/{asset.file_id}.jpg",
        data=image_bytes,
        content_type="image/jpeg",
    )

    # 3. Processa (AI + Pillow) in memoria o /tmp
    processed_bytes = apply_processing(image_bytes)

    # 4. Upload processed su Blob
    processed_url = await blob_store.upload(
        key=f"processed/{platform}/{image_id}.jpg",
        data=processed_bytes,
        content_type="image/jpeg",
    )

    # 5. Salva URL in Postgres (non path locale)
    db.update_image(image_id, path=processed_url, original_path=original_url)
```

### 2. Thumbnail Drive (preview in Seleziona)

```python
# services/drive_thumbnails.py (target)
async def get_thumbnail(file_id: str) -> str:
    cached = await blob_store.exists(f"thumbnails/drive/{file_id}.jpg")
    if cached:
        return cached.url
    thumb_bytes = drive_client.get_thumbnail(file_id)
    return await blob_store.upload(f"thumbnails/drive/{file_id}.jpg", thumb_bytes)
```

### 3. Dispatch Meta (publish)

```python
# scheduling/dispatch_runner.py (target)
async def publish_event(row, meta_client):
    blob_url = row["path"]  # URL da Postgres

    # Download temporaneo in /tmp per upload Graph API
    tmp_path = await blob_store.download_to_tmp(blob_url)
    try:
        meta_client.publish_photo(tmp_path, caption=...)
    finally:
        tmp_path.unlink()
```

---

## Serving media alla UI

### Attuale

```python
# api/routers/media.py
@router.get("/{image_id}/processed")
def serve_processed(...) -> FileResponse:
    path = resolve_processed_path(...)  # Path locale
    return FileResponse(path)
```

### Target — Opzione A: redirect diretto

```python
@router.get("/{image_id}/processed")
def serve_processed(image_id: int, db: DbDep) -> RedirectResponse:
    url = db.get_image_blob_url(image_id, kind="processed")
    if not url:
        raise HTTPException(404)
    return RedirectResponse(url, status_code=302)
```

### Target — Opzione B: URL in API response (preferita)

Il frontend riceve già `media.processed` e `media.original` nelle risposte API. Basta che l'API restituisca URL Blob direttamente:

```json
{
  "id": 42,
  "media": {
    "processed": "https://xxx.blob.vercel-storage.com/processed/ig/42.jpg",
    "original": "https://xxx.blob.vercel-storage.com/originals/drive/abc.jpg"
  }
}
```

Il router `media.py` diventa opzionale (backward compat o proxy signed URL).

---

## Vercel Blob — setup

### Installazione

```bash
npm install @vercel/blob   # se serve da frontend
pip install vercel-blob    # oppure httpx diretto all'API
```

### Env vars (auto-iniettate da Vercel)

```
BLOB_READ_WRITE_TOKEN=vercel_blob_rw_...
```

### Upload da Python

```python
import httpx

async def upload_blob(key: str, data: bytes, content_type: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"https://blob.vercel-storage.com/{key}",
            content=data,
            headers={
                "Authorization": f"Bearer {BLOB_READ_WRITE_TOKEN}",
                "Content-Type": content_type,
                "x-api-version": "7",
            },
        )
        response.raise_for_status()
        return response.json()["url"]
```

### Accesso pubblico vs privato

| Modalità | Uso | Note |
|----------|-----|------|
| **Public** | Preview immagini in dashboard | URL diretto in `<img src>` |
| **Private + signed URL** | Maggiore sicurezza | API genera signed URL con TTL |

Per un tool interno (2 utenti), **public** con auth sulla dashboard è sufficiente.

---

## Modulo storage astratto

```
src/social_automation/storage/
├── __init__.py
├── interface.py       # Protocol: upload, download, exists, delete
├── blob_store.py      # Vercel Blob implementation
├── local_store.py     # Filesystem (dev locale)
└── factory.py         # get_storage(settings) → Blob | Local
```

### Settings

```python
# settings.py (aggiunte)
storage_backend: str = "local"          # local | vercel_blob
blob_read_write_token: str = ""
blob_store_id: str = ""                 # opzionale
```

---

## Migrazione file esistenti

### Script upload bulk

```bash
python scripts/upload_output_to_blob.py \
  --source output/ \
  --sqlite output/social_automation.db \
  --update-db  # aggiorna path → URL in SQLite prima della migrazione PG
```

### Ordine operazioni

1. Creare Blob store su Vercel
2. Upload tutti i file in `output/processed/` e `output/drive_*`
3. Aggiornare path nel DB (SQLite o direttamente Postgres)
4. Verificare che le preview funzionino con i nuovi URL
5. Eliminare `output/` locale

---

## Limiti e considerazioni

| Aspetto | Limite | Mitigazione |
|---------|--------|-------------|
| Dimensione singolo file | 500 MB (Vercel Blob) | OK per foto JPEG |
| Costo storage | ~$0.15/GB/mese | Stimare ~1–5 GB per brand |
| Latency upload | ~100–500ms | Accettabile per batch |
| /tmp per dispatch | Limitato a RAM function | Download solo file necessario |
| CORS immagini | Blob public = nessun problema | — |

---

## Checklist storage

- [ ] Creare Vercel Blob store
- [ ] Implementare `storage/blob_store.py`
- [ ] Refactor `process_photo.py` per upload Blob
- [ ] Refactor `drive_thumbnails.py` per cache Blob
- [ ] Refactor `dispatch_runner.py` per download /tmp
- [ ] Aggiornare API responses con URL Blob
- [ ] Rimuovere o deprecare `api/routers/media.py` FileResponse
- [ ] Script migrazione file esistenti
- [ ] Test preview immagini in UI Approva/Pianifica
- [ ] Test dispatch con immagine da Blob
