from __future__ import annotations

import json

from fastapi.testclient import TestClient

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.drive.errors import is_google_token_error
from social_automation.settings import Settings
from google.auth.exceptions import RefreshError


def test_is_google_token_error() -> None:
    assert is_google_token_error(RefreshError("invalid_grant: revoked"))
    assert is_google_token_error(Exception("invalid_grant: Token has been expired or revoked."))
    assert not is_google_token_error(Exception("folder not found"))


def test_google_oauth_status_endpoint(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    settings = Settings(
        db_path=db_path,
        cron_secret="secret",
        google_credentials_json=json.dumps({"web": {"client_id": "id", "client_secret": "sec"}}),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    client = TestClient(app)

    response = client.get("/api/v1/oauth/google/status")
    assert response.status_code == 200
    body = response.json()
    assert body["credentials_configured"] is True
    assert body["refresh_token_configured"] is False
    assert body["reconnect_url"] == "/api/v1/oauth/google/start"
    assert body["redirect_uri"].endswith("/api/v1/oauth/google/callback")
