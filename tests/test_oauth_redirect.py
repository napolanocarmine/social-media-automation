from __future__ import annotations

from social_automation.drive.oauth_redirect import resolve_google_oauth_redirect_uri
from social_automation.settings import Settings


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def test_redirect_uri_from_explicit_env() -> None:
    settings = Settings(
        google_redirect_uri="https://app.example.com/api/v1/oauth/google/callback",
    )
    assert (
        resolve_google_oauth_redirect_uri(settings)
        == "https://app.example.com/api/v1/oauth/google/callback"
    )


def test_redirect_uri_from_request_host() -> None:
    settings = Settings()
    request = _FakeRequest(
        {
            "host": "story-social.vercel.app",
            "x-forwarded-proto": "https",
        }
    )
    assert (
        resolve_google_oauth_redirect_uri(settings, request=request)
        == "https://story-social.vercel.app/api/v1/oauth/google/callback"
    )
