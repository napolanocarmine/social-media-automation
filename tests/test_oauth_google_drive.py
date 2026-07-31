from __future__ import annotations

from social_automation.db.store import (
    ensure_db_schema,
    get_oauth_refresh_token,
    upsert_oauth_token,
)
from social_automation.drive.oauth_state import (
    create_signed_oauth_state,
    parse_signed_oauth_state,
    verify_signed_oauth_state,
)
from social_automation.drive.token_store import (
    GOOGLE_DRIVE_PROVIDER,
    resolve_google_refresh_token,
)
from social_automation.settings import Settings


def test_signed_oauth_state_roundtrip() -> None:
    settings = Settings(
        cron_secret="test-secret",
        google_credentials_json='{"web":{"client_id":"x"}}',
    )
    state = create_signed_oauth_state(settings, code_verifier="pkce-verifier-abc")

    assert verify_signed_oauth_state(settings, state)
    payload = parse_signed_oauth_state(settings, state)
    assert payload is not None
    assert payload.get("cv") == "pkce-verifier-abc"


def test_oauth_token_upsert_and_resolve(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    ensure_db_schema(db_path)
    upsert_oauth_token(
        db_path,
        provider=GOOGLE_DRIVE_PROVIDER,
        refresh_token="refresh-abc",
    )
    assert get_oauth_refresh_token(db_path, provider=GOOGLE_DRIVE_PROVIDER) == "refresh-abc"

    settings = Settings(
        db_path=db_path,
        google_credentials_json='{"web":{"client_id":"x"}}',
        google_refresh_token="env-token",
    )
    assert resolve_google_refresh_token(settings, db_path=db_path) == "refresh-abc"
