"""Meta Graph API: pubblicazione foto su Facebook Page e Instagram (account collegato)."""

from __future__ import annotations

import json
import mimetypes
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from social_automation.meta.graph_httpx import graph_httpx_tls_params
from social_automation.models import MediaFormat, Platform, infer_media_format_from_render_path
from social_automation.settings import Settings, load_settings
from social_automation.util.retry import retry_http

_DEFAULT_GRAPH_VERSION = "v22.0"
_CONTAINER_POLL_INTERVAL_S = 2.0
_CONTAINER_POLL_MAX_S = 120.0


def _graph_base(version: str) -> str:
    v = version.strip().lstrip("/") or _DEFAULT_GRAPH_VERSION
    return f"https://graph.facebook.com/{v}"


def _raise_for_graph_body(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        data = resp.json()
        err = data.get("error") or {}
        msg = err.get("message", resp.text[:500])
        code = err.get("code", "")
        sub = err.get("error_subcode", "")
        raise RuntimeError(f"Meta Graph API ({resp.status_code}) [{code}/{sub}]: {msg}")
    except (ValueError, KeyError, TypeError):
        raise RuntimeError(f"Meta Graph API ({resp.status_code}): {resp.text[:800]}") from None


class MetaClient:
    """Pubblicazione tramite Page Access Token (e IG User ID per Instagram)."""

    def __init__(
        self,
        page_access_token: str,
        ig_user_id: str = "",
        *,
        graph_version: str = _DEFAULT_GRAPH_VERSION,
        settings: Settings | None = None,
    ) -> None:
        s = settings if settings is not None else load_settings()
        self._token = page_access_token.strip()
        self._ig_user_id = ig_user_id.strip()
        self._version = graph_version.strip() or _DEFAULT_GRAPH_VERSION
        self._base = _graph_base(self._version)
        self._page_id: str | None = None
        self._page_id_hint = (s.meta_page_id or "").strip()
        self._tls = graph_httpx_tls_params(s)

    def _http(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            timeout=timeout,
            verify=self._tls["verify"],
            trust_env=self._tls["trust_env"],
        )

    def get_page_profile(self) -> dict[str, Any]:
        """Metadati Page: GET /{page-id} se ``META_PAGE_ID`` è impostato, altrimenti GET /me."""

        def do() -> dict[str, Any]:
            with self._http(30.0) as client:
                if self._page_id_hint:
                    r = client.get(
                        f"{self._base}/{self._page_id_hint}",
                        params={"fields": "id,name", "access_token": self._token},
                    )
                else:
                    r = client.get(
                        f"{self._base}/me",
                        params={"fields": "id,name", "access_token": self._token},
                    )
            _raise_for_graph_body(r)
            return r.json()

        return retry_http(do)

    def get_page_id(self) -> str:
        """ID della Page associata al Page Access Token.

        Se ``META_PAGE_ID`` è impostato nei settings, viene usato senza chiamare Graph:
        alcune app/token non possono fare GET su ``/me`` o ``/{page-id}`` (errore 100
        finché manca es. ``pages_read_engagement``), ma ``pages_manage_posts`` può
        bastare per pubblicare sulla stessa Page.
        """
        if self._page_id:
            return self._page_id
        if self._page_id_hint:
            self._page_id = self._page_id_hint
            return self._page_id
        data = self.get_page_profile()
        pid = str(data.get("id", "")).strip()
        if not pid:
            raise RuntimeError("Meta: risposta profilo Page senza id")
        self._page_id = pid
        return self._page_id

    def publish_facebook_photo(
        self,
        image_path: Path,
        caption: str,
        *,
        published: bool = True,
    ) -> str:
        """Carica una foto sulla Page. Restituisce l'id del post o della foto (Graph)."""
        if not image_path.is_file():
            raise FileNotFoundError(str(image_path))
        page_id = self.get_page_id()
        mime, _ = mimetypes.guess_type(str(image_path))
        mime = mime or "application/octet-stream"

        def do() -> str:
            with self._http(180.0) as client:
                with image_path.open("rb") as fh:
                    files = {"source": (image_path.name, fh, mime)}
                    data: dict[str, Any] = {
                        "access_token": self._token,
                        "published": "true" if published else "false",
                    }
                    if caption.strip():
                        data["message"] = caption.strip()
                    r = client.post(
                        f"{self._base}/{page_id}/photos",
                        files=files,
                        data=data,
                    )
            _raise_for_graph_body(r)
            out = r.json()
            post_id = str(out.get("post_id") or out.get("id") or "").strip()
            if not post_id:
                raise RuntimeError(f"Meta FB: risposta inattesa: {out}")
            return post_id

        return retry_http(do)

    def schedule_facebook_photo(
        self,
        image_path: Path,
        caption: str,
        *,
        publish_at: datetime,
    ) -> str:
        """Programma un post foto sulla Page via ``/feed`` + ``attached_media``.

        Flusso Meta per Planner / Business Suite. Non usa ``/photos`` con
        ``scheduled_publish_time`` da solo: quel percorso spesso non compare
        nel Planner di Business Suite. Sequenza: upload foto ``published=false`` + ``temporary=true``,
        poi ``POST /{page-id}/feed`` con ``unpublished_content_type=SCHEDULED`` e ``attached_media``.
        Restituisce l'id del **post** (``{page-id}_{post-id}``).
        """
        if not image_path.is_file():
            raise FileNotFoundError(str(image_path))
        ts = int(publish_at.timestamp())
        page_id = self.get_page_id()
        mime, _ = mimetypes.guess_type(str(image_path))
        mime = mime or "application/octet-stream"
        msg = (caption or "").strip() or image_path.stem.strip() or "."

        def do() -> str:
            photo_id = self._upload_unpublished_page_photo(image_path, temporary=True)
            try:
                with self._http(180.0) as client:
                    r = client.post(
                        f"{self._base}/{page_id}/feed",
                        data={
                            "access_token": self._token,
                            "message": msg,
                            "published": "false",
                            "scheduled_publish_time": str(ts),
                            "unpublished_content_type": "SCHEDULED",
                            "attached_media": json.dumps([{"media_fbid": photo_id}]),
                        },
                    )
                _raise_for_graph_body(r)
                out = r.json()
                post_id = str(out.get("id", "")).strip()
                if not post_id:
                    raise RuntimeError(f"Meta FB schedule (feed): risposta inattesa: {out}")
                return post_id
            except Exception:
                try:
                    self.delete_graph_object(photo_id)
                except Exception:
                    pass
                raise

        return retry_http(do)

    def list_page_scheduled_posts(self, *, limit: int = 25) -> dict[str, Any]:
        """Post programmati sulla Page: ``GET /{page-id}/scheduled_posts`` (vedi doc Meta)."""
        page_id = self.get_page_id()
        lim = max(1, min(int(limit), 100))

        def do() -> dict[str, Any]:
            with self._http(60.0) as client:
                r = client.get(
                    f"{self._base}/{page_id}/scheduled_posts",
                    params={
                        "access_token": self._token,
                        "limit": str(lim),
                        "fields": "id,created_time,scheduled_publish_time,message",
                    },
                )
            _raise_for_graph_body(r)
            return r.json()

        return retry_http(do)

    def delete_graph_object(self, object_id: str) -> None:
        """Elimina un oggetto Graph (es. foto/post programmato) con DELETE ``/{object_id}``."""
        oid = object_id.strip()
        if not oid:
            raise ValueError("object_id non può essere vuoto")

        def do() -> None:
            with self._http(60.0) as client:
                r = client.delete(f"{self._base}/{oid}", params={"access_token": self._token})
            _raise_for_graph_body(r)

        retry_http(do)

    def _upload_unpublished_page_photo(self, image_path: Path, *, temporary: bool = False) -> str:
        """Carica foto non pubblicata sulla Page; serve per IG o per ``attached_media`` su ``/feed``."""
        if not image_path.is_file():
            raise FileNotFoundError(str(image_path))
        page_id = self.get_page_id()
        mime, _ = mimetypes.guess_type(str(image_path))
        mime = mime or "application/octet-stream"

        def do() -> str:
            with self._http(180.0) as client:
                with image_path.open("rb") as fh:
                    files = {"source": (image_path.name, fh, mime)}
                    data: dict[str, Any] = {
                        "access_token": self._token,
                        "published": "false",
                    }
                    if temporary:
                        data["temporary"] = "true"
                    r = client.post(
                        f"{self._base}/{page_id}/photos",
                        files=files,
                        data=data,
                    )
            _raise_for_graph_body(r)
            photo_id = str(r.json().get("id", "")).strip()
            if not photo_id:
                raise RuntimeError(f"Meta: upload foto senza id: {r.text[:300]}")
            return photo_id

        return retry_http(do)

    def _photo_best_source_url(self, photo_id: str) -> str:
        def do() -> str:
            with self._http(30.0) as client:
                r = client.get(
                    f"{self._base}/{photo_id}",
                    params={
                        "fields": "images",
                        "access_token": self._token,
                    },
                )
            _raise_for_graph_body(r)
            images = r.json().get("images") or []
            if not images:
                raise RuntimeError("Meta: foto senza campo images (URL non disponibile per IG)")
            best = max(
                images,
                key=lambda im: int(im.get("width", 0) or 0) * int(im.get("height", 0) or 0),
            )
            url = str(best.get("source", "")).strip()
            if not url:
                raise RuntimeError("Meta: impossibile ottenere URL sorgente dalla foto Page")
            return url

        return retry_http(do)

    def _instagram_wait_container_ready(self, container_id: str) -> None:
        deadline = time.monotonic() + _CONTAINER_POLL_MAX_S
        while time.monotonic() < deadline:
            with self._http(30.0) as client:
                r = client.get(
                    f"{self._base}/{container_id}",
                    params={
                        "fields": "status_code",
                        "access_token": self._token,
                    },
                )
            _raise_for_graph_body(r)
            status = str(r.json().get("status_code", "")).upper()
            if status in {"FINISHED", "PUBLISHED"}:
                return
            if status in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Meta IG: container in stato {status}")
            time.sleep(_CONTAINER_POLL_INTERVAL_S)
        raise TimeoutError(f"Meta IG: timeout in attesa container {container_id}")

    def publish_instagram_photo(self, image_path: Path, caption: str) -> str:
        """Post immagine su IG (Page): upload non pubblicato, URL, container, publish.

        Per **pianificazione futura** non usare ``publish_time`` + ``media_publish`` immediato (Meta
        spesso pubblica subito). Pattern consigliato: salvare nel DB e chiamare questo metodo
        all’orario con ``dispatch-scheduled``; vedi ``docs/instagram_graph_api_scheduler_notes.md``.
        """
        if not self._ig_user_id:
            raise RuntimeError("META_IG_USER_ID mancante per la pubblicazione Instagram")
        photo_id = self._upload_unpublished_page_photo(image_path)
        image_url = self._photo_best_source_url(photo_id)

        def create_container() -> str:
            with self._http(60.0) as client:
                r = client.post(
                    f"{self._base}/{self._ig_user_id}/media",
                    data={
                        "image_url": image_url,
                        "caption": caption.strip(),
                        "access_token": self._token,
                    },
                )
            _raise_for_graph_body(r)
            cid = str(r.json().get("id", "")).strip()
            if not cid:
                raise RuntimeError(f"Meta IG: creazione container fallita: {r.text[:500]}")
            return cid

        container_id = retry_http(create_container)
        self._instagram_wait_container_ready(container_id)

        def publish() -> str:
            with self._http(60.0) as client:
                r = client.post(
                    f"{self._base}/{self._ig_user_id}/media_publish",
                    data={
                        "creation_id": container_id,
                        "access_token": self._token,
                    },
                )
            _raise_for_graph_body(r)
            mid = str(r.json().get("id", "")).strip()
            if not mid:
                raise RuntimeError(f"Meta IG: media_publish senza id: {r.text[:500]}")
            return mid

        return retry_http(publish)

    def publish_instagram_story(self, image_path: Path, caption: str = "") -> str:
        """Pubblica una story immagine su IG (Graph: ``media_type=STORIES``)."""
        if not self._ig_user_id:
            raise RuntimeError("META_IG_USER_ID mancante per la pubblicazione Instagram")
        photo_id = self._upload_unpublished_page_photo(image_path)
        image_url = self._photo_best_source_url(photo_id)
        cap = caption.strip()

        def create_container() -> str:
            data: dict[str, Any] = {
                "image_url": image_url,
                "media_type": "STORIES",
                "access_token": self._token,
            }
            if cap:
                data["caption"] = cap
            with self._http(60.0) as client:
                r = client.post(
                    f"{self._base}/{self._ig_user_id}/media",
                    data=data,
                )
            _raise_for_graph_body(r)
            cid = str(r.json().get("id", "")).strip()
            if not cid:
                raise RuntimeError(f"Meta IG: creazione container story fallita: {r.text[:500]}")
            return cid

        container_id = retry_http(create_container)
        self._instagram_wait_container_ready(container_id)

        def publish() -> str:
            with self._http(60.0) as client:
                r = client.post(
                    f"{self._base}/{self._ig_user_id}/media_publish",
                    data={
                        "creation_id": container_id,
                        "access_token": self._token,
                    },
                )
            _raise_for_graph_body(r)
            mid = str(r.json().get("id", "")).strip()
            if not mid:
                raise RuntimeError(f"Meta IG: media_publish story senza id: {r.text[:500]}")
            return mid

        return retry_http(publish)

    def publish_facebook_story_photo(self, image_path: Path) -> str:
        """Story foto su Facebook Page: upload non pubblicato + ``/{page-id}/photo_stories``."""
        page_id = self.get_page_id()
        photo_id = self._upload_unpublished_page_photo(image_path)

        def do() -> str:
            with self._http(60.0) as client:
                r = client.post(
                    f"{self._base}/{page_id}/photo_stories",
                    data={
                        "photo_id": photo_id,
                        "access_token": self._token,
                    },
                )
            _raise_for_graph_body(r)
            body = r.json()
            story_id = str(body.get("id", "")).strip()
            if story_id:
                return story_id
            post_id = str(body.get("post_id", "")).strip()
            if post_id:
                return post_id
            success = body.get("success")
            if success is True and photo_id:
                return photo_id
            raise RuntimeError(f"Meta FB: photo_stories senza id riconoscibile: {r.text[:500]}")

        return retry_http(do)

    def publish_image(
        self,
        platform: Platform,
        image_path: Path,
        caption: str,
        *,
        media_format: str | None = None,
    ) -> str:
        """Dispatcher: post feed o story (formato esplicito o dedotto dal path di render)."""
        fmt = media_format if media_format is not None else infer_media_format_from_render_path(
            image_path
        ).value
        if fmt == MediaFormat.STORY.value:
            if platform == Platform.FACEBOOK:
                return self.publish_facebook_story_photo(image_path)
            if platform == Platform.INSTAGRAM:
                return self.publish_instagram_story(image_path, caption)
            raise ValueError(f"Piattaforma non supportata: {platform}")
        if platform == Platform.FACEBOOK:
            return self.publish_facebook_photo(image_path, caption, published=True)
        if platform == Platform.INSTAGRAM:
            return self.publish_instagram_photo(image_path, caption)
        raise ValueError(f"Piattaforma non supportata: {platform}")
