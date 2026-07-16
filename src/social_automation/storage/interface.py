"""Interfaccia storage media."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StorageBackend(Protocol):
    def upload(self, key: str, data: bytes, *, content_type: str = "image/jpeg") -> str:
        """Upload bytes e restituisce URL pubblico."""
        ...

    def download(self, url_or_key: str) -> bytes:
        """Download bytes da URL o key."""
        ...

    def download_to_tmp(self, url_or_key: str, *, suffix: str = ".jpg") -> Path:
        """Download in file temporaneo /tmp."""
        ...

    def exists(self, key: str) -> str | None:
        """Restituisce URL se la key esiste, altrimenti None."""
        ...

    def is_remote_url(self, value: str) -> bool:
        """True se il valore è un URL remoto (non path locale)."""
        ...
