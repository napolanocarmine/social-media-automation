"""Storage astratto per media (local | Vercel Blob)."""

from __future__ import annotations

from social_automation.storage.factory import get_storage
from social_automation.storage.interface import StorageBackend

__all__ = ["StorageBackend", "get_storage"]
