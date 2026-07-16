"""Filesystem locale (dev)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

from social_automation.settings import Settings, load_settings, resolve_media_file_path


class LocalStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def _resolve_path(self, key: str) -> Path:
        raw = (key or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            raise ValueError("LocalStorage non supporta URL remoti")
        p = Path(raw)
        if p.is_absolute():
            return p
        return (self.settings.output_dir / p).resolve()

    def upload(self, key: str, data: bytes, *, content_type: str = "image/jpeg") -> str:
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def download(self, url_or_key: str) -> bytes:
        path = resolve_media_file_path(url_or_key) or self._resolve_path(url_or_key)
        return path.read_bytes()

    def download_to_tmp(self, url_or_key: str, *, suffix: str = ".jpg") -> Path:
        data = self.download(url_or_key)
        fd, name = tempfile.mkstemp(suffix=suffix)
        tmp = Path(name)
        tmp.write_bytes(data)
        return tmp

    def exists(self, key: str) -> str | None:
        path = resolve_media_file_path(key) or self._resolve_path(key)
        return str(path) if path.is_file() else None

    def is_remote_url(self, value: str) -> bool:
        parsed = urlparse((value or "").strip())
        return parsed.scheme in {"http", "https"}
