from pathlib import Path

from social_automation.config_loaders import load_category_aliases


def test_load_category_aliases_from_example() -> None:
    root = Path(__file__).resolve().parents[1]
    aliases = load_category_aliases(root / "config" / "categories.example.yaml")
    assert aliases["peppe"] == "boss"
    assert aliases["beer"] == "birra"
