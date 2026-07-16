"""Smoke test API — equivalente a scripts/smoke-e2e.sh in pytest."""

from __future__ import annotations

from fastapi.testclient import TestClient

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.settings import Settings


def test_smoke_endpoints(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite3"
    settings = Settings(db_path=db_path, output_dir=tmp_path / "output")
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    client = TestClient(app)

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/dashboard/stats").status_code == 200
    assert client.get("/api/v1/config/categories").status_code == 200
    assert client.get("/api/v1/dispatch/due?limit=5").status_code == 200
    assert client.get("/api/v1/batches?limit=5").status_code == 200


def test_runtime_error_returns_detail_json() -> None:
    app = create_app()

    @app.get("/test-runtime-error")
    def _boom() -> None:
        raise RuntimeError("OpenAI API 429: insufficient_quota")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test-runtime-error")
    assert response.status_code == 502
    assert response.json() == {"detail": "OpenAI API 429: insufficient_quota"}
