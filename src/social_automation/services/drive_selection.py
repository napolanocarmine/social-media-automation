"""Selezione asset Google Drive per UI e batch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from social_automation.config_loaders import (
    load_categories_yaml,
    load_category_aliases,
    resolve_drive_folder_id,
)
from social_automation.db.store import has_source_asset_render_for_platform
from social_automation.drive.client import DriveClient
from social_automation.drive.selection import (
    apply_category_alias,
    infer_category_names,
    normalize_business_category,
    sort_assets_newest_first,
    year_month_from_path,
)
from social_automation.models import DriveAsset, MediaFormat, Platform

DEFAULT_CATEGORIES_CONFIG = Path("config/categories.yaml")


def raw_categories(cat_cfg_path: Path) -> set[str]:
    categories_cfg = load_categories_yaml(cat_cfg_path) if cat_cfg_path.exists() else {}
    raw = {
        str(c).strip().lower()
        for c in categories_cfg.get("raw_categories", [])
        if str(c).strip()
    }
    return raw if raw else {"food", "beer", "peppe", "locale"}


def business_category_options(cat_cfg_path: Path) -> list[str]:
    aliases = load_category_aliases(cat_cfg_path) if cat_cfg_path.exists() else {}
    raw = sorted(raw_categories(cat_cfg_path))
    ordered: list[str] = []
    seen: set[str] = set()
    for name in raw:
        business = normalize_business_category(name, aliases)
        if business not in seen:
            ordered.append(business)
            seen.add(business)
    for value in aliases.values():
        business = str(value).strip().lower()
        if business and business not in seen:
            ordered.append(business)
            seen.add(business)
    if not ordered:
        return ["food", "beer", "peppe", "locale"]
    return ordered


def asset_matches_period(
    asset: DriveAsset,
    *,
    target_year: int | None,
    target_month: int | None,
) -> bool:
    if target_year is None and target_month is None:
        return True
    year, month = year_month_from_path(asset.path_segments)
    if target_year is not None and year != int(target_year):
        return False
    if target_month is not None and month != int(target_month):
        return False
    return True


def pick_latest_asset(
    drive_client: DriveClient,
    folder_id: str,
    *,
    category: str,
    categories_config: Path,
    db_path: Path,
    platform: Platform,
    target_year: int | None = None,
    target_month: int | None = None,
    media_format: MediaFormat = MediaFormat.POST,
) -> tuple[DriveAsset, dict[str, str]]:
    aliases = (
        load_category_aliases(categories_config) if categories_config.exists() else {}
    )
    raw_cats = raw_categories(categories_config)
    assets = drive_client.list_images_recursively(
        folder_id,
        category_names=infer_category_names(raw_cats, aliases),
    )
    ranked = sort_assets_newest_first(assets)
    target_business_category = normalize_business_category(category, aliases)
    for asset in ranked:
        if not asset_matches_period(
            asset,
            target_year=target_year,
            target_month=target_month,
        ):
            continue
        if apply_category_alias(asset.category, aliases) != target_business_category:
            continue
        if has_source_asset_render_for_platform(
            db_path,
            source_asset_id=asset.file_id,
            platform=platform,
            media_format=media_format,
        ):
            continue
        return asset, aliases
    raise RuntimeError(
        f"Nessun asset trovato per categoria business '{target_business_category}'."
    )


def load_drive_assets_for_selection(
    settings: Any,
    *,
    category: str,
    target_year: int | None = None,
    target_month: int | None = None,
    open_browser: bool = True,
) -> list[DriveAsset]:
    """Elenco immagini Drive (listing senza filtro già processate)."""
    categories_config = DEFAULT_CATEGORIES_CONFIG
    folder_id = resolve_drive_folder_id(
        folder_id_arg="",
        folder_id_env=settings.google_drive_folder_id,
        categories_yaml=categories_config,
    )
    if not folder_id:
        raise RuntimeError(
            "Manca folder id Drive in `config/categories.yaml` o `.env`."
        )
    oauth_browser = (settings.google_oauth_browser or "").strip() or None
    drive_client = DriveClient.from_paths(
        settings.google_credentials_path,
        settings.google_token_path,
        open_browser=open_browser,
        oauth_browser=oauth_browser,
    )
    aliases = (
        load_category_aliases(categories_config) if categories_config.exists() else {}
    )
    raw_cats = raw_categories(categories_config)
    assets = drive_client.list_images_recursively(
        folder_id,
        category_names=infer_category_names(raw_cats, aliases),
    )
    ranked = sort_assets_newest_first(assets)
    target_business_category = normalize_business_category(category, aliases)
    filtered: list[DriveAsset] = []
    for asset in ranked:
        if not asset_matches_period(
            asset,
            target_year=target_year,
            target_month=target_month,
        ):
            continue
        if apply_category_alias(asset.category, aliases) != target_business_category:
            continue
        filtered.append(asset)
    return filtered
