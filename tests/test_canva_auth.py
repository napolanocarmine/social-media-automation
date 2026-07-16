from social_automation.canva.auth import (
    extract_code_from_input,
    generate_code_challenge,
    normalize_scopes,
)


def test_normalize_scopes_accepts_spaces_and_commas() -> None:
    scopes = normalize_scopes("asset:read, asset:write design:meta:read")
    assert scopes == ["asset:read", "asset:write", "design:meta:read"]


def test_extract_code_from_callback_url() -> None:
    code = extract_code_from_input("http://127.0.0.1:8080/callback?code=abc123&state=xyz")
    assert code == "abc123"


def test_generate_code_challenge_is_urlsafe() -> None:
    challenge = generate_code_challenge("a" * 64)
    assert "=" not in challenge
    assert "+" not in challenge
    assert "/" not in challenge
