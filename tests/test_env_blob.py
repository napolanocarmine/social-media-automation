from __future__ import annotations

import os

import pytest

from social_automation.env import (
    blob_storage_configured_from_env,
    parse_blob_store_id_from_read_write_token,
    resolve_blob_read_write_token_from_env,
    resolve_blob_store_id_from_env,
)


@pytest.fixture(autouse=True)
def _clear_blob_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        upper = key.upper()
        if "BLOB" in upper or upper == "VERCEL_OIDC_TOKEN":
            monkeypatch.delenv(key, raising=False)


def test_resolve_prefixed_blob_read_write_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "SOCIAL_MEDIA_AUTOMATION_BLOB_READ_WRITE_TOKEN",
        "vercel_blob_rw_store123_secret",
    )
    assert resolve_blob_read_write_token_from_env() == "vercel_blob_rw_store123_secret"


def test_parse_store_id_from_read_write_token() -> None:
    token = "vercel_blob_rw_mystore_abc123"
    assert parse_blob_store_id_from_read_write_token(token) == "mystore"


def test_oidc_plus_store_id_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "oidc-token")
    monkeypatch.setenv("BLOB_STORE_ID", "store_myblob")
    assert resolve_blob_store_id_from_env() == "myblob"
    assert blob_storage_configured_from_env() is True
