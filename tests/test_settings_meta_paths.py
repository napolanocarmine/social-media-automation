
from social_automation.settings import (
    default_meta_page_token_file,
    intended_meta_page_token_file_path,
)


def test_default_meta_page_token_file_name() -> None:
    p = default_meta_page_token_file()
    assert p.name == "meta_page_token.txt"
    assert "output" in p.parts


def test_intended_meta_page_token_relative_resolves_under_output() -> None:
    p = intended_meta_page_token_file_path("output/meta_page_token.txt")
    assert p is not None
    assert p.name == "meta_page_token.txt"
    assert p.parent.name == "output"


def test_intended_meta_page_token_empty_returns_none() -> None:
    assert intended_meta_page_token_file_path("") is None
    assert intended_meta_page_token_file_path("   ") is None
