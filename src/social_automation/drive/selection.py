"""Utility per mappatura categorie e ordinamento per recency anno/mese."""

from __future__ import annotations

import re

from social_automation.models import DriveAsset

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")

_MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "gen": 1,
    "gennaio": 1,
    "feb": 2,
    "february": 2,
    "febbraio": 2,
    "mar": 3,
    "march": 3,
    "marzo": 3,
    "apr": 4,
    "april": 4,
    "aprile": 4,
    "may": 5,
    "maggio": 5,
    "jun": 6,
    "june": 6,
    "giu": 6,
    "giugno": 6,
    "jul": 7,
    "july": 7,
    "lug": 7,
    "luglio": 7,
    "aug": 8,
    "august": 8,
    "ago": 8,
    "agosto": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "set": 9,
    "settembre": 9,
    "oct": 10,
    "october": 10,
    "ott": 10,
    "ottobre": 10,
    "nov": 11,
    "november": 11,
    "novembre": 11,
    "dec": 12,
    "december": 12,
    "dic": 12,
    "dicembre": 12,
}


def apply_category_alias(raw: str | None, aliases: dict[str, str]) -> str | None:
    if not raw:
        return None
    normalized = raw.strip().lower()
    return aliases.get(normalized, normalized)


def infer_category_names(raw_categories: set[str], aliases: dict[str, str]) -> set[str]:
    """Categorie da usare per inferenza path: raw + possibili business names."""
    if not aliases:
        return raw_categories
    names = {c.strip().lower() for c in raw_categories if c.strip()}
    names.update(v.strip().lower() for v in aliases.values() if str(v).strip())
    return names


def normalize_business_category(category: str, aliases: dict[str, str]) -> str:
    """Normalizza input categoria accettando raw o business label."""
    normalized = category.strip().lower()
    if not normalized:
        return ""
    return aliases.get(normalized, normalized)


def parse_aliases(raw_aliases: str) -> dict[str, str]:
    """Parsa 'peppe:boss,beer:birra'."""
    out: dict[str, str] = {}
    for chunk in raw_aliases.split(","):
        if ":" not in chunk:
            continue
        left, right = chunk.split(":", 1)
        key = left.strip().lower()
        value = right.strip().lower()
        if key and value:
            out[key] = value
    return out


def month_from_segment(segment: str) -> int:
    s = segment.strip().lower()
    if s.isdigit():
        n = int(s)
        if 1 <= n <= 12:
            return n
    parts = re.split(r"[^a-z0-9]+", s)
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            n = int(part)
            if 1 <= n <= 12:
                return n
        if part in _MONTH_ALIASES:
            return _MONTH_ALIASES[part]
    return 0


def year_month_from_path(path_segments: list[str]) -> tuple[int, int]:
    year = 0
    month = 0
    for idx, seg in enumerate(path_segments):
        normalized = seg.strip()
        if _YEAR_RE.match(normalized):
            year = int(normalized)
            if idx + 1 < len(path_segments):
                month = month_from_segment(path_segments[idx + 1])
            break
    return year, month


def sort_assets_newest_first(assets: list[DriveAsset]) -> list[DriveAsset]:
    def key(asset: DriveAsset) -> tuple[int, int, str]:
        year, month = year_month_from_path(asset.path_segments)
        return (year, month, asset.name.lower())

    return sorted(assets, key=key, reverse=True)
