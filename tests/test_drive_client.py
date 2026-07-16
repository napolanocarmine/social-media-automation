from social_automation.drive.client import DriveClient


def test_infer_category_from_path_segments() -> None:
    category = DriveClient._infer_category(
        ["2025", "05_maggio", "Beer"],
        {"food", "peppe", "beer"},
    )
    assert category == "beer"


def test_infer_category_returns_none_without_match() -> None:
    category = DriveClient._infer_category(
        ["2025", "05_maggio", "eventi"],
        {"food", "peppe", "beer"},
    )
    assert category is None


def test_infer_category_from_partial_segment_match() -> None:
    category = DriveClient._infer_category(
        ["2025", "Dicembre", "food and drink"],
        {"food", "peppe", "beer"},
    )
    assert category == "food"
