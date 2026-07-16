from social_automation.drive.selection import (
    apply_category_alias,
    infer_category_names,
    normalize_business_category,
    parse_aliases,
    sort_assets_newest_first,
    year_month_from_path,
)
from social_automation.models import DriveAsset


def test_year_month_from_path_italian_month() -> None:
    year, month = year_month_from_path(["2026", "Marzo", "food"])
    assert (year, month) == (2026, 3)


def test_apply_category_alias() -> None:
    aliases = {"peppe": "boss", "beer": "birra"}
    assert apply_category_alias("peppe", aliases) == "boss"
    assert apply_category_alias("food", aliases) == "food"


def test_infer_category_names_includes_alias_values() -> None:
    raw = {"food", "beer"}
    aliases = {"beer": "birra", "peppe": "boss"}
    names = infer_category_names(raw, aliases)
    assert names == {"food", "beer", "birra", "boss"}


def test_normalize_business_category_accepts_raw_or_business() -> None:
    aliases = {"beer": "birra", "peppe": "boss"}
    assert normalize_business_category("beer", aliases) == "birra"
    assert normalize_business_category("birra", aliases) == "birra"


def test_parse_aliases() -> None:
    parsed = parse_aliases("peppe:boss,beer:birra")
    assert parsed == {"peppe": "boss", "beer": "birra"}


def test_sort_assets_newest_first() -> None:
    older = DriveAsset(
        file_id="1",
        name="old.jpg",
        mime_type="image/jpeg",
        category="food",
        path_segments=["2024", "Gennaio", "food"],
    )
    newer = DriveAsset(
        file_id="2",
        name="new.jpg",
        mime_type="image/jpeg",
        category="food",
        path_segments=["2026", "Marzo", "food"],
    )
    ordered = sort_assets_newest_first([older, newer])
    assert ordered[0].file_id == "2"
