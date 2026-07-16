"""Vercel Blob storage."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from social_automation.settings import Settings, load_settings


class BlobStorage:
    BLOB_API = "https://blob.vercel-storage.com"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.token = (
            (self.settings.blob_read_write_token or "").strip()
            or (os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip()
        )
        if not self.token:
            raise RuntimeError("BLOB_READ_WRITE_TOKEN non configurato")

    def _headers(self, content_type: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": content_type,
            "x-api-version": "7",
        }

    def upload(self, key: str, data: bytes, *, content_type: str = "image/jpeg") -> str:
        clean_key = key.lstrip("/")
        url = f"{self.BLOB_API}/{quote(clean_key, safe='/')}"
        with httpx.Client(timeout=120.0) as client:
            resp = client.put(url, content=data, headers=self._headers(content_type))
            resp.raise_for_status()
            payload = resp.json()
            return str(payload.get("url") or url)

    def download(self, url_or_key: str) -> bytes:
        target = self._to_url(url_or_key)
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(target)
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
        url = f"{self.BLOB_API}/{quote(clean_key, safe='/')}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.head(url, headers={"Authorization": f"Bearer {self.token}"})
            if resp.status_code == 200:
                return url
        return None

    def is_remote_url(self, value: str) -> bool:
        parsed = urlparse((value or "").strip())
        return parsed.scheme in {"http", "https"}

    def _to_url(self, url_or_key: str) -> str:
        raw = (url_or_key or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        clean_key = raw.lstrip("/")
        return f"{self.BLOB_API}/{quote(clean_key, safe='/')}"
