"""Test retry HTTP."""

from __future__ import annotations

import httpx
import pytest

from social_automation.util.retry import retry_http


def test_retry_http_succeeds_after_transient_503() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            req = httpx.Request("GET", "https://example.com")
            resp = httpx.Response(503, request=req)
            raise httpx.HTTPStatusError("srv", request=req, response=resp)
        return "ok"

    assert retry_http(fn, max_attempts=4, base_delay_s=0.01) == "ok"
    assert calls["n"] == 2


def test_retry_http_non_retry_status_raises() -> None:
    def fn() -> str:
        req = httpx.Request("GET", "https://example.com")
        resp = httpx.Response(400, request=req)
        raise httpx.HTTPStatusError("bad", request=req, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        retry_http(fn, max_attempts=3, base_delay_s=0.01)


def test_retry_http_transport_retries() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            req = httpx.Request("GET", "https://example.com")
            raise httpx.ConnectError("x", request=req)
        return "ok"

    assert retry_http(fn, max_attempts=4, base_delay_s=0.01) == "ok"
