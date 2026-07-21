from __future__ import annotations

from pathlib import Path

from social_automation.settings import load_settings


def test_load_settings_uses_tmp_output_on_vercel(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    s = load_settings()
    assert s.output_dir == Path("/tmp/social-automation")
    assert s.db_backend == "postgres"


def test_load_settings_output_dir_override_on_vercel(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("OUTPUT_DIR", "/tmp/custom")
    s = load_settings()
    assert str(s.output_dir) == "/tmp/custom"
