"""Render Drive → Canva condiviso tra CLI, UI e workflow settimanale."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from social_automation.canva.client import CanvaClient
from social_automation.canva.templates import resolve_template_id
from social_automation.config_loaders import (
    load_canva_yaml,
    load_categories_yaml,
    load_category_aliases,
    resolve_drive_folder_id,
)
from social_automation.db.store import has_source_asset_render_for_platform, record_render_artifacts
from social_automation.drive.client import DriveClient
from social_automation.drive.selection import (
    apply_category_alias,
    infer_category_names,
    normalize_business_category,
    sort_assets_newest_first,
)
from social_automation.models import DriveAsset, MediaFormat, Platform
from social_automation.settings import Settings, load_settings

_DEFAULT_CATEGORIES = Path("config/categories.yaml")


def _raw_categories_set(cat_cfg_path: Path) -> set[str]:
    categories_cfg = load_categories_yaml(cat_cfg_path) if cat_cfg_path.exists() else {}
    raw = {
        str(c).strip().lower()
        for c in categories_cfg.get("raw_categories", [])
        if str(c).strip()
    }
    return raw if raw else {"food", "beer", "peppe", "locale"}


def pick_latest_unrendered_asset(
    drive: DriveClient,
    folder_id: str,
    *,
    business_category: str,
    categories_config: Path,
    db_path: Path,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
) -> DriveAsset | None:
    """Asset più recente per categoria non ancora renderizzato per piattaforma/formato."""
    raw_categories = _raw_categories_set(categories_config)
    aliases = load_category_aliases(categories_config) if categories_config.exists() else {}
    assets = drive.list_images_recursively(
        folder_id,
        category_names=infer_category_names(raw_categories, aliases),
    )
    ranked = sort_assets_newest_first(assets)
    target = normalize_business_category(business_category, aliases)
    for asset in ranked:
        if apply_category_alias(asset.category, aliases) != target:
            continue
        if has_source_asset_render_for_platform(
            db_path,
            source_asset_id=asset.file_id,
            platform=platform,
            media_format=media_format,
        ):
            continue
        return asset
    return None


def render_drive_canva_asset(
    *,
    category: str,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
    settings: Settings | None = None,
    categories_config: Path | None = None,
    use_placeholder: bool = False,
) -> dict[str, Any]:
    """Scarica asset Drive, render Canva, registra in DB. Solleva RuntimeError se impossibile."""
    s = settings or load_settings()
    cat_cfg = categories_config or _DEFAULT_CATEGORIES
    folder_id = resolve_drive_folder_id(
        folder_id_arg="",
        folder_id_env=s.google_drive_folder_id,
        categories_yaml=cat_cfg,
    )
    if not folder_id:
        raise RuntimeError("Manca folder id Drive (GOOGLE_DRIVE_FOLDER_ID o categories.yaml)")
    if not s.canva_config_path.exists():
        raise RuntimeError(f"Config Canva non trovata: {s.canva_config_path}")

    oauth_browser = (s.google_oauth_browser or "").strip() or None
    drive = DriveClient.from_paths(
        s.google_credentials_path,
        s.google_token_path,
        open_browser=True,
        oauth_browser=oauth_browser,
    )
    selected = pick_latest_unrendered_asset(
        drive,
        folder_id,
        business_category=category,
        categories_config=cat_cfg,
        db_path=s.db_path,
        platform=platform,
        media_format=media_format,
    )
    if selected is None:
        raise RuntimeError(
            f"Nessun asset Drive non ancora renderizzato per categoria={category!r} "
            f"platform={platform.value} format={media_format.value}"
        )

    aliases = load_category_aliases(cat_cfg) if cat_cfg.exists() else {}
    business_category = normalize_business_category(category, aliases)
    canva_cfg = load_canva_yaml(s.canva_config_path)
    template_id = resolve_template_id(
        canva_cfg,
        platform=platform.value,
        category=business_category,
        media_format=media_format,
    )
    if not template_id:
        raise RuntimeError(
            f"Nessun template Canva per platform={platform.value} "
            f"category={business_category} format={media_format.value}"
        )

    output_dir = s.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = mimetypes.guess_extension(selected.mime_type) or ".jpg"
    source_path = output_dir / f"drive_{selected.file_id}{suffix}"
    source_path.write_bytes(drive.download_file_bytes(selected.file_id))

    canva = CanvaClient.from_token_file(
        s.canva_client_id.strip(),
        s.canva_client_secret.strip(),
        s.canva_redirect_uri.strip(),
        s.canva_token_path,
    )
    rendered = canva.render_for_platform(
        source_path,
        platform,
        template_id=template_id,
        output_dir=output_dir / "canva-rendered",
        output_stem=f"{business_category}_{selected.file_id}",
        use_placeholder=use_placeholder,
        precrop_cover=True,
        media_format=media_format,
    )
    meta = canva.get_last_render_metadata() or {}
    image_id = record_render_artifacts(
        s.db_path,
        image_name=selected.name,
        image_path=rendered,
        source_asset_id=selected.file_id,
        source_asset_name=selected.name,
        business_category=business_category,
        metadata_payload=meta,
    )
    return {
        "image_id": image_id,
        "rendered_file": str(rendered),
        "business_category": business_category,
        "platform": platform.value,
        "media_format": media_format.value,
        "template_id": template_id,
        "source_asset_id": selected.file_id,
    }
