"""Client Canva Connect: template, dimensioni per IG/FB, export immagine.

Riferimento: Canva Connect REST API (OAuth2).
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from social_automation.canva.image_cover import write_cover_jpeg
from social_automation.models import MediaFormat, Platform

logger = logging.getLogger(__name__)

CANVA_REST_V1 = "https://api.canva.com/rest/v1"
CANVA_TOKEN_URL = f"{CANVA_REST_V1}/oauth/token"

# Dimensioni di fallback per i POST se non riusciamo a leggere le pagine del template master.
FORMAT_BY_PLATFORM: dict[Platform, tuple[int, int]] = {
    Platform.INSTAGRAM: (1080, 1080),
    Platform.FACEBOOK: (1200, 630),
}

# Le storie (IG/FB) condividono lo stesso formato verticale 9:16.
STORY_FALLBACK_DIMENSIONS: tuple[int, int] = (1080, 1920)

# Sottocartella unica condivisa per le storie (IG/FB) come richiesto in spec.
_STORY_OUTPUT_SUBDIR = "stories"

_ASSET_POLL_INTERVAL_S = 1.0
_EXPORT_POLL_INTERVAL_S = 1.5
_ASSET_WAIT_MAX_S = 180.0
_EXPORT_WAIT_MAX_S = 300.0


def _platform_output_subdir(
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
) -> str:
    if media_format == MediaFormat.STORY:
        return _STORY_OUTPUT_SUBDIR
    if platform == Platform.INSTAGRAM:
        return "ig"
    if platform == Platform.FACEBOOK:
        return "fb"
    return platform.value


def _fallback_dimensions(
    platform: Platform,
    media_format: MediaFormat,
) -> tuple[int, int]:
    if media_format == MediaFormat.STORY:
        return STORY_FALLBACK_DIMENSIONS
    return FORMAT_BY_PLATFORM[platform]


def _clamp_design_dimension(n: int) -> int:
    return max(40, min(8000, n))


def _encode_asset_name(name: str) -> str:
    trimmed = name[:50]
    return base64.b64encode(trimmed.encode("utf-8")).decode("ascii")


class CanvaClient:
    """Client Canva Connect (token-based): upload, create design, export."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        token: dict[str, Any] | None = None,
        token_path: Path | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token = token or {}
        self._token_path = token_path
        self._last_render_metadata: dict[str, Any] | None = None

    @classmethod
    def from_token_file(
        cls,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        token_path: Path,
    ) -> CanvaClient:
        if not token_path.exists():
            raise FileNotFoundError(
                f"Token Canva non trovato: {token_path}. "
                "Esegui `python -m social_automation canva-auth`."
            )
        token = json.loads(token_path.read_text(encoding="utf-8"))
        return cls(
            client_id,
            client_secret,
            redirect_uri,
            token=token,
            token_path=token_path,
        )

    def _access_token(self) -> str:
        token = str(self._token.get("access_token", "")).strip()
        if not token:
            raise RuntimeError(
                "access_token Canva mancante nel token file. Riesegui `canva-auth`."
            )
        return token

    def _auth_headers_json(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
        }

    def get_last_render_metadata(self) -> dict[str, Any] | None:
        """Ultimi metadati render generati in memoria (copia difensiva)."""
        if self._last_render_metadata is None:
            return None
        return dict(self._last_render_metadata)

    @staticmethod
    def _canva_error_code(resp: httpx.Response) -> str:
        try:
            payload = resp.json()
        except ValueError:
            return ""
        code = payload.get("code")
        if isinstance(code, str):
            return code.strip()
        return ""

    def _save_token_if_possible(self) -> None:
        if self._token_path is None:
            return
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(
            json.dumps(self._token, indent=2),
            encoding="utf-8",
        )

    def _refresh_access_token(self) -> None:
        refresh_token = str(self._token.get("refresh_token", "")).strip()
        if not refresh_token:
            raise RuntimeError(
                "Token Canva scaduto/non valido e refresh_token assente. "
                "Riesegui `python -m social_automation canva-auth`."
            )
        logger.info("Canva: access token non valido, provo refresh token")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                CANVA_TOKEN_URL,
                data=payload,
                auth=(self._client_id, self._client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                "Refresh token Canva fallito. "
                "Riesegui `python -m social_automation canva-auth`. "
                f"Dettaglio ({resp.status_code}): {resp.text[:500]}"
            )
        new_token = resp.json()
        if not str(new_token.get("access_token", "")).strip():
            raise RuntimeError("Refresh Canva riuscito ma access_token mancante in risposta.")
        if not str(new_token.get("refresh_token", "")).strip():
            new_token["refresh_token"] = refresh_token
        self._token.update(new_token)
        self._save_token_if_possible()
        logger.info("Canva: token aggiornato e salvato")

    def get_profile(self) -> dict[str, Any]:
        """Verifica token Canva tramite endpoint profile."""
        logger.debug("Richiesta GET users/me/profile")
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{CANVA_REST_V1}/users/me/profile",
                headers={"Authorization": f"Bearer {self._access_token()}"},
            )
        if resp.status_code == 401 and self._canva_error_code(resp) == "invalid_access_token":
            self._refresh_access_token()
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    f"{CANVA_REST_V1}/users/me/profile",
                    headers={"Authorization": f"Bearer {self._access_token()}"},
                )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Errore profilo Canva ({resp.status_code}): {resp.text[:500]}"
            )
        return resp.json()

    def get_first_page_dimensions(self, design_id: str) -> tuple[int, int] | None:
        """Legge larghezza/altezza della prima pagina (preview API)."""
        logger.info(
            "Canva: lettura dimensioni prima pagina del template (design_id=%s)",
            design_id,
        )
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{CANVA_REST_V1}/designs/{design_id}/pages",
                params={"offset": 1, "limit": 1},
                headers={"Authorization": f"Bearer {self._access_token()}"},
            )
        if resp.status_code == 401 and self._canva_error_code(resp) == "invalid_access_token":
            self._refresh_access_token()
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    f"{CANVA_REST_V1}/designs/{design_id}/pages",
                    params={"offset": 1, "limit": 1},
                    headers={"Authorization": f"Bearer {self._access_token()}"},
                )
        if resp.status_code >= 400:
            logger.warning(
                "Canva: impossibile leggere le pagine del template (%s): HTTP %s",
                design_id,
                resp.status_code,
            )
            return None
        data = resp.json()
        items = data.get("items") or []
        if not items:
            logger.info(
                "Canva: nessuna pagina restituita per il design %s, uso dimensioni di fallback",
                design_id,
            )
            return None
        dim = items[0].get("dimensions") or {}
        w = dim.get("width")
        h = dim.get("height")
        if w is None or h is None:
            logger.info(
                "Canva: pagina senza dimensioni note per %s, uso fallback",
                design_id,
            )
            return None
        out = _clamp_design_dimension(int(round(float(w)))), _clamp_design_dimension(
            int(round(float(h)))
        )
        logger.info(
            "Canva: dimensioni canvas da template %sx%s px (arrotondate/clamp)",
            out[0],
            out[1],
        )
        return out

    def upload_image_asset(self, image_path: Path) -> str:
        """Carica un file immagine; restituisce asset_id."""
        token = self._access_token()
        meta = json.dumps(
            {"name_base64": _encode_asset_name(image_path.stem or "upload")},
            separators=(",", ":"),
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Asset-Upload-Metadata": meta,
        }
        body = image_path.read_bytes()
        logger.info(
            "Canva: upload immagine su asset-uploads (%s, %s byte)",
            image_path.name,
            len(body),
        )
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{CANVA_REST_V1}/asset-uploads",
                headers=headers,
                content=body,
            )
        if resp.status_code == 401 and self._canva_error_code(resp) == "invalid_access_token":
            self._refresh_access_token()
            headers["Authorization"] = f"Bearer {self._access_token()}"
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{CANVA_REST_V1}/asset-uploads",
                    headers=headers,
                    content=body,
                )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Errore upload asset Canva ({resp.status_code}): {resp.text[:800]}"
            )
        payload = resp.json()
        job = payload.get("job") or {}
        job_id = job.get("id")
        logger.debug(
            "Canva: risposta upload job id=%s status=%s",
            job_id,
            job.get("status"),
        )
        if job.get("status") == "success":
            asset = job.get("asset") or {}
            aid = asset.get("id")
            if aid:
                logger.info("Canva: upload completato, asset_id=%s", aid)
                return str(aid)
        if job.get("status") == "failed":
            err = job.get("error") or {}
            raise RuntimeError(
                f"Upload asset fallito: {err.get('code', '')} {err.get('message', '')}"
            )
        if not job_id:
            raise RuntimeError(f"Risposta upload asset inattesa: {payload!r}")
        logger.info(
            "Canva: upload in corso, polling job asset fino a completamento (job_id=%s)",
            job_id,
        )
        return self._wait_asset_job(str(job_id))

    def _wait_asset_job(self, job_id: str) -> str:
        deadline = time.monotonic() + _ASSET_WAIT_MAX_S
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        with httpx.Client(timeout=30.0) as client:
            while time.monotonic() < deadline:
                resp = client.get(
                    f"{CANVA_REST_V1}/asset-uploads/{job_id}",
                    headers=headers,
                )
                if (
                    resp.status_code == 401
                    and self._canva_error_code(resp) == "invalid_access_token"
                ):
                    self._refresh_access_token()
                    headers["Authorization"] = f"Bearer {self._access_token()}"
                    resp = client.get(
                        f"{CANVA_REST_V1}/asset-uploads/{job_id}",
                        headers=headers,
                    )
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Errore polling asset ({resp.status_code}): {resp.text[:500]}"
                    )
                job = (resp.json().get("job") or {})
                status = job.get("status")
                logger.debug("Canva: poll asset job %s → status=%s", job_id, status)
                if status == "success":
                    asset = job.get("asset") or {}
                    aid = asset.get("id")
                    if not aid:
                        break
                    logger.info("Canva: upload completato, asset_id=%s", aid)
                    return str(aid)
                if status == "failed":
                    err = job.get("error") or {}
                    raise RuntimeError(
                        f"Upload asset fallito: {err.get('code', '')} {err.get('message', '')}"
                    )
                time.sleep(_ASSET_POLL_INTERVAL_S)
        raise TimeoutError(f"Timeout in attesa asset upload job {job_id}")

    def create_design_with_asset(
        self,
        width: int,
        height: int,
        asset_id: str,
        title: str,
    ) -> str:
        body: dict[str, Any] = {
            "type": "type_and_asset",
            "design_type": {
                "type": "custom",
                "width": _clamp_design_dimension(width),
                "height": _clamp_design_dimension(height),
            },
            "asset_id": asset_id,
            "title": title[:255] if title else "Render",
        }
        logger.info(
            "Canva: creazione design %sx%s px con asset_id=%s (POST /v1/designs)",
            body["design_type"]["width"],
            body["design_type"]["height"],
            asset_id,
        )
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{CANVA_REST_V1}/designs",
                headers=self._auth_headers_json(),
                json=body,
            )
        if resp.status_code == 401 and self._canva_error_code(resp) == "invalid_access_token":
            self._refresh_access_token()
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{CANVA_REST_V1}/designs",
                    headers=self._auth_headers_json(),
                    json=body,
                )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Errore create design Canva ({resp.status_code}): {resp.text[:800]}"
            )
        design = (resp.json().get("design") or {})
        did = design.get("id")
        if not did:
            raise RuntimeError(f"Create design senza id: {resp.text[:500]}")
        logger.info("Canva: design creato, design_id=%s", did)
        return str(did)

    def export_jpeg_file(
        self,
        design_id: str,
        *,
        width: int | None = None,
        height: int | None = None,
        quality: int = 92,
        pages: list[int] | None = None,
    ) -> bytes:
        fmt: dict[str, Any] = {
            "type": "jpg",
            "quality": max(1, min(100, quality)),
        }
        if width is not None:
            fmt["width"] = width
        if height is not None:
            fmt["height"] = height
        if pages:
            fmt["pages"] = pages
        body = {"design_id": design_id, "format": fmt}
        headers_json = self._auth_headers_json()
        poll_headers = {"Authorization": f"Bearer {self._access_token()}"}
        logger.info(
            "Canva: avvio export JPEG (design_id=%s, quality=%s, width=%s, height=%s)",
            design_id,
            fmt.get("quality"),
            fmt.get("width"),
            fmt.get("height"),
        )
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{CANVA_REST_V1}/exports",
                headers=headers_json,
                json=body,
            )
            if (
                resp.status_code == 401
                and self._canva_error_code(resp) == "invalid_access_token"
            ):
                self._refresh_access_token()
                headers_json = self._auth_headers_json()
                poll_headers["Authorization"] = f"Bearer {self._access_token()}"
                resp = client.post(
                    f"{CANVA_REST_V1}/exports",
                    headers=headers_json,
                    json=body,
                )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Errore create export Canva ({resp.status_code}): {resp.text[:800]}"
                )
            job = (resp.json().get("job") or {})
            job_id = job.get("id")
            if not job_id:
                raise RuntimeError(f"Export job senza id: {resp.text[:500]}")
            logger.debug(
                "Canva: export job id=%s status=%s",
                job_id,
                job.get("status"),
            )
            if job.get("status") == "success" and job.get("urls"):
                logger.info("Canva: export già pronto, download in corso")
                return self._download_first_url(client, list(job["urls"]))
            logger.info(
                "Canva: export in elaborazione, polling (export job_id=%s)",
                job_id,
            )
            return self._wait_export_job(client, str(job_id), poll_headers)

    def _wait_export_job(
        self,
        client: httpx.Client,
        job_id: str,
        headers: dict[str, str],
    ) -> bytes:
        deadline = time.monotonic() + _EXPORT_WAIT_MAX_S
        while time.monotonic() < deadline:
            resp = client.get(
                f"{CANVA_REST_V1}/exports/{job_id}",
                headers=headers,
            )
            if resp.status_code == 401 and self._canva_error_code(resp) == "invalid_access_token":
                self._refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token()}"
                resp = client.get(
                    f"{CANVA_REST_V1}/exports/{job_id}",
                    headers=headers,
                )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Errore polling export ({resp.status_code}): {resp.text[:500]}"
                )
            job = (resp.json().get("job") or {})
            status = job.get("status")
            logger.debug("Canva: poll export job %s → status=%s", job_id, status)
            if status == "success":
                urls = job.get("urls") or []
                if not urls:
                    raise RuntimeError("Export completato senza URL")
                logger.info("Canva: export completato, download da URL Canva")
                return self._download_first_url(client, list(urls))
            if status == "failed":
                err = job.get("error") or {}
                raise RuntimeError(
                    f"Export fallito: {err.get('code', '')} {err.get('message', '')}"
                )
            time.sleep(_EXPORT_POLL_INTERVAL_S)
        raise TimeoutError(f"Timeout export job {job_id}")

    @staticmethod
    def _download_first_url(client: httpx.Client, urls: list[str]) -> bytes:
        if not urls:
            raise RuntimeError("Nessun URL di download export")
        r = client.get(urls[0], timeout=120.0, follow_redirects=True)
        if r.status_code >= 400:
            raise RuntimeError(
                f"Download export fallito ({r.status_code}): {r.text[:300]}"
            )
        logger.info("Canva: scaricati %s byte (JPEG export)", len(r.content))
        return r.content

    def render_for_platform(
        self,
        source_image_path: Path,
        platform: Platform,
        template_id: str | None = None,
        *,
        output_dir: Path | None = None,
        output_stem: str | None = None,
        use_placeholder: bool = False,
        precrop_cover: bool = True,
        media_format: MediaFormat = MediaFormat.POST,
    ) -> Path:
        """Render: upload → nuovo design (canvas) → export JPEG, oppure copia locale.

        Se ``precrop_cover`` è True, l'immagine viene ritagliata in locale con la stessa logica
        del «Riempi» in Canva (copre il canvas, crop centrato), perché la Connect API con
        ``asset_id`` non espone crop/sfondo come nell'editor.

        ``media_format`` distingue tra ``post`` (cartella per piattaforma ig/fb) e ``story``
        (cartella unica condivisa ``stories``, formato verticale 9:16).
        """
        if not source_image_path.is_file():
            raise FileNotFoundError(f"File sorgente non trovato: {source_image_path}")
        target_dir = output_dir or Path("output") / "canva-rendered"
        platform_dir = target_dir / _platform_output_subdir(platform, media_format)
        platform_dir.mkdir(parents=True, exist_ok=True)
        stem = output_stem or source_image_path.stem
        # Per le storie includiamo "story" nel nome file in modo da distinguerle
        # dai post, anche quando IG/FB condividono la stessa cartella "stories".
        if media_format == MediaFormat.STORY:
            file_suffix_label = f"{platform.value}_story"
        else:
            file_suffix_label = platform.value
        out_path = platform_dir / f"{stem}_{file_suffix_label}.jpg"

        if use_placeholder:
            logger.info(
                "Canva: modalità placeholder — copia locale senza API "
                "(platform=%s, format=%s, template_id=%s)",
                platform.value,
                media_format.value,
                template_id,
            )
            ext = source_image_path.suffix or ".jpg"
            out_path = platform_dir / f"{stem}_{file_suffix_label}{ext}"
            shutil.copy2(source_image_path, out_path)
            metadata = {
                "platform": platform.value,
                "media_format": media_format.value,
                "template_id": template_id,
                "source_file": str(source_image_path),
                "output_file": str(out_path),
                "mode": "placeholder_copy",
            }
            self._last_render_metadata = metadata
            logger.info("Canva: file scritto %s (metadati salvati in memoria)", out_path)
            return out_path

        logger.info(
            "Canva: inizio render Connect — sorgente=%s platform=%s format=%s template_id=%s",
            source_image_path,
            platform.value,
            media_format.value,
            template_id,
        )
        fallback_w, fallback_h = _fallback_dimensions(platform, media_format)
        dims: tuple[int, int] | None = None
        if template_id:
            dims = self.get_first_page_dimensions(template_id)
        else:
            logger.info(
                "Canva: nessun template_id, dimensioni canvas da fallback (%s/%s)",
                platform.value,
                media_format.value,
            )
        canvas_w, canvas_h = dims if dims else (fallback_w, fallback_h)
        if not dims:
            logger.info(
                "Canva: uso dimensioni fallback canvas=%sx%s export=%sx%s",
                canvas_w,
                canvas_h,
                fallback_w,
                fallback_h,
            )
        export_w, export_h = (
            (canvas_w, canvas_h) if dims else (fallback_w, fallback_h)
        )
        logger.info(
            "Canva: export finale %sx%s px (preserva_aspect=%s)",
            export_w,
            export_h,
            bool(dims),
        )

        upload_path = source_image_path
        prep_path: Path | None = None
        if precrop_cover:
            prep_path = platform_dir / f".{stem}_{file_suffix_label}_cover_prep.jpg"
            logger.info(
                "Canva: pre-elaborazione immagine (crop «cover» / Riempi) → %sx%s px, file %s",
                canvas_w,
                canvas_h,
                prep_path.name,
            )
            write_cover_jpeg(
                source_image_path,
                prep_path,
                canvas_w,
                canvas_h,
                jpeg_quality=95,
            )
            upload_path = prep_path
        try:
            asset_id = self.upload_image_asset(upload_path)
        finally:
            if prep_path is not None and prep_path.exists():
                prep_path.unlink()

        title = f"{stem} {file_suffix_label}"[:255]
        design_id = self.create_design_with_asset(
            canvas_w, canvas_h, asset_id, title=title
        )
        jpeg_bytes = self.export_jpeg_file(
            design_id,
            width=export_w,
            height=export_h,
            quality=92,
            pages=[1],
        )
        out_path.write_bytes(jpeg_bytes)
        logger.info(
            "Canva: render completato — output=%s (%s byte)",
            out_path,
            len(jpeg_bytes),
        )
        metadata = {
            "platform": platform.value,
            "media_format": media_format.value,
            "template_id": template_id,
            "template_dimensions_source": "first_page" if dims else "fallback_format_map",
            "canvas_width": canvas_w,
            "canvas_height": canvas_h,
            "export_width": export_w,
            "export_height": export_h,
            "image_fit": "cover_precrop_local" if precrop_cover else "api_default",
            "asset_id": asset_id,
            "design_id": design_id,
            "source_file": str(source_image_path),
            "output_file": str(out_path),
            "mode": "connect_upload_create_export",
            "note": (
                "Crop «Riempi» applicato in locale prima dell'upload: la REST Connect con "
                "asset_id non espone setBackground/crop come l'editor o l'Apps SDK. "
                "Template usato per le dimensioni canvas. Per layout master variabile: "
                "Brand template / Autofill."
            ),
        }
        self._last_render_metadata = metadata
        return out_path
