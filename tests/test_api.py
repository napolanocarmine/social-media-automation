from __future__ import annotations

from fastapi.testclient import TestClient

from social_automation.api.main import create_app


def test_health_v1() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "social-media-automation-api",
    }


def test_health_legacy_alias() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_stats_empty_db(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    from social_automation.api.deps import get_db_path, get_settings
    from social_automation.settings import Settings

    app = create_app()
    settings = Settings(db_path=db_path)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path

    client = TestClient(app)
    response = client.get("/api/v1/dashboard/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["processed_visual"] == 0
    assert body["pending_approval"] == 0
    assert body["ready_to_plan"] == 0
    assert body["due_dispatch"] == 0
    assert body["running_batches"] == 0


def test_suggested_next_step_select_when_empty(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    from social_automation.api.deps import get_db_path, get_settings
    from social_automation.settings import Settings

    app = create_app()
    settings = Settings(db_path=db_path)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path

    client = TestClient(app)
    response = client.get("/api/v1/dashboard/suggested-next-step")
    assert response.status_code == 200
    assert response.json()["page"] == "① Seleziona"
