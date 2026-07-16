"""Factory storage backend."""

from __future__ import annotations

from social_automation.settings import Settings, load_settings
from social_automation.storage.blob_store import BlobStorage
from social_automation.storage.local_store import LocalStorage


def get_storage(settings: Settings | None = None):
    s = settings or load_settings()
    backend = (s.storage_backend or "local").strip().lower()
    if backend in {"vercel_blob", "blob"}:
        return BlobStorage(s)
    return LocalStorage(s)
