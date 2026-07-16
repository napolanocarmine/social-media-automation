"""Vercel Blob storage (API v12 + OIDC o read-write token)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode, urlparse

import httpx

from social_automation.env import (
    blob_storage_configured_from_env,
    normalize_blob_store_id,
    parse_blob_store_id_from_read_write_token,
    resolve_blob_read_write_token_from_env,
    resolve_blob_store_id_from_env,
    resolve_vercel_oidc_token_from_env,
)
from social_automation.settings import Settings, load_settings


@dataclass(frozen=True)
class BlobAuth:
    kind: Literal["oidc", "read_write"]
    token: str
    store_id: str


def resolve_blob_auth(settings: Settings | None = None) -> BlobAuth:
    s = settings or load_settings()

    rw = (s.blob_read_write_token or "").strip() or resolve_blob_read_write_token_from_env()
    if rw:
        store_id = parse_blob_store_id_from_read_write_token(rw)
        if not store_id:
            store_id = resolve_blob_store_id_from_env()
        if store_id:
            return BlobAuth("read_write", rw, normalize_blob_store_id(store_id))

    oidc = resolve_vercel_oidc_token_from_env()
    store_id = resolve_blob_store_id_from_env()
    if oidc and store_id:
        return BlobAuth("oidc", oidc, normalize_blob_store_id(store_id))

    if rw:
        raise RuntimeError(
            "BLOB_READ_WRITE_TOKEN presente ma store id non risolvibile "
            "(manca BLOB_STORE_ID o token malformato)."
        )
    raise RuntimeError(
        "Blob non configurato: servono BLOB_READ_WRITE_TOKEN oppure "
        "VERCEL_OIDC_TOKEN + BLOB_STORE_ID (integrazione Vercel Blob)."
    )


class BlobStorage:
    BLOB_API = "https://vercel.com/api/blob"
    BLOB_API_VERSION = "12"
    DEFAULT_ACCESS = "public"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.auth = resolve_blob_auth(self.settings)
        self.access = (self.settings.blob_access or self.DEFAULT_ACCESS).strip().lower()
        if self.access not in {"public", "private"}:
            self.access = self.DEFAULT_ACCESS

    @staticmethod
    def is_configured(settings: Settings | None = None) -> bool:
        s = settings or load_settings()
        if (s.blob_read_write_token or "").strip():
            return True
        return blob_storage_configured_from_env()

    def _auth_headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.auth.token}",
            "x-vercel-blob-store-id": self.auth.store_id,
            "x-api-version": self.BLOB_API_VERSION,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _put_headers(self, *, content_type: str, allow_overwrite: bool = True) -> dict[str, str]:
        headers = self._auth_headers(content_type=content_type)
        headers.update(
            {
                "x-vercel-blob-access": self.access,
                "x-content-type": content_type,
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1" if allow_overwrite else "0",
            }
        )
        return headers

    def _blob_url(self, key: str) -> str:
        clean_key = key.lstrip("/")
        return f"https://{self.auth.store_id}.{self.access}.blob.vercel-storage.com/{clean_key}"

    def upload(self, key: str, data: bytes, *, content_type: str = "image/jpeg") -> str:
        clean_key = key.lstrip("/")
        query = urlencode({"pathname": clean_key})
        url = f"{self.BLOB_API}/?{query}"
        with httpx.Client(timeout=120.0) as client:
            resp = client.put(
                url,
                content=data,
                headers=self._put_headers(content_type=content_type),
            )
            resp.raise_for_status()
            payload = resp.json()
            return str(payload.get("url") or self._blob_url(clean_key))

    def download(self, url_or_key: str) -> bytes:
        target = self._to_url(url_or_key)
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(target, headers={"Authorization": f"Bearer {self.auth.token}"})
            resp.raise_for_status()
            return resp.content

    def download_to_tmp(self, url_or_key: str, *, suffix: str = ".jpg") -> Path:
        data = self.download(url_or_key)
        fd, name = tempfile.mkstemp(suffix=suffix)
        tmp = Path(name)
        tmp.write_bytes(data)
        return tmp

    def exists(self, key: str) -> str | None:
        clean_key = key.lstrip("/")
        candidates = [clean_key, self._blob_url(clean_key)]
        with httpx.Client(timeout=30.0) as client:
            for candidate in candidates:
                query = urlencode({"url": candidate})
                resp = client.get(
                    f"{self.BLOB_API}?{query}",
                    headers=self._auth_headers(),
                )
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                payload = resp.json()
                found = str(payload.get("url") or candidate).strip()
                if found:
                    return found
        return None

    def is_remote_url(self, value: str) -> bool:
        parsed = urlparse((value or "").strip())
        return parsed.scheme in {"http", "https"}

    def _to_url(self, url_or_key: str) -> str:
        raw = (url_or_key or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        clean_key = raw.lstrip("/")
        return self._blob_url(clean_key)
