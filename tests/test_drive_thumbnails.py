from __future__ import annotations

import os

import pytest

from social_automation.services.drive_thumbnails import (
    _blob_cache_available,
    _use_blob_cache,
)
from social_automation.settings import Settings


@pytest.fixture(autouse=True)
def _clear_blob_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        upper = key.upper()
        if "BLOB" in upper or upper == "VERCEL_OIDC_TOKEN":
            monkeypatch.delenv(key, raising=False)


def test_use_blob_cache_when_backend_vercel_blob() -> None:
    settings = Settings(storage_backend="vercel_blob")
    assert _use_blob_cache(settings) is True


def test_blob_cache_unavailable_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    settings = Settings(storage_backend="vercel_blob")
    assert _blob_cache_available(settings) is False
