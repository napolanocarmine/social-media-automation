from __future__ import annotations

from pathlib import Path

from social_automation.http.vision_httpx import vision_httpx_tls_params
from social_automation.meta.graph_httpx import graph_httpx_tls_params
from social_automation.settings import Settings


def test_vision_httpx_inherits_meta_tls(monkeypatch, tmp_path: Path) -> None:
    ca = tmp_path / "corp.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n")
    monkeypatch.setenv("META_GRAPH_HTTP_TRUST_ENV", "false")
    monkeypatch.setenv("META_GRAPH_HTTP_CA_BUNDLE", str(ca))
    monkeypatch.delenv("VISION_HTTP_TRUST_ENV", raising=False)
    monkeypatch.delenv("VISION_HTTP_CA_BUNDLE", raising=False)

    tls = vision_httpx_tls_params(Settings())
    assert tls["trust_env"] is False
    assert tls["verify"] == str(ca.resolve())


def test_vision_httpx_override_meta(monkeypatch, tmp_path: Path) -> None:
    ca_meta = tmp_path / "meta.pem"
    ca_vision = tmp_path / "vision.pem"
    ca_meta.write_text("meta\n")
    ca_vision.write_text("vision\n")
    monkeypatch.setenv("META_GRAPH_HTTP_TRUST_ENV", "false")
    monkeypatch.setenv("META_GRAPH_HTTP_CA_BUNDLE", str(ca_meta))
    monkeypatch.setenv("VISION_HTTP_TRUST_ENV", "true")
    monkeypatch.setenv("VISION_HTTP_CA_BUNDLE", str(ca_vision))

    tls = vision_httpx_tls_params(Settings())
    assert tls["trust_env"] is True
    assert tls["verify"] == str(ca_vision.resolve())


def test_graph_httpx_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("META_GRAPH_HTTP_TRUST_ENV", "false")
    tls = graph_httpx_tls_params(Settings())
    assert tls == {"verify": True, "trust_env": False}
