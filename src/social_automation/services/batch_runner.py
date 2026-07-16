"""Avvio batch Story AI via queue DB (compatibile Vercel)."""

from __future__ import annotations

from social_automation.config_loaders import load_category_aliases
from social_automation.db.store import add_batch_item, create_batch
from social_automation.drive.selection import normalize_business_category
from social_automation.models import DriveAsset, MediaFormat, Platform
from social_automation.services.drive_selection import DEFAULT_CATEGORIES_CONFIG
from social_automation.settings import Settings


def start_selected_ai_batch(
    settings: Settings,
    *,
    category: str,
    platform: Platform,
    media_format: MediaFormat,
    assets: list[dict],
    marketing_objectives: list[str] | None = None,
    channels: list[str] | None = None,
) -> int:
    if not assets:
        raise ValueError("Seleziona almeno un asset Drive")

    aliases = (
        load_category_aliases(DEFAULT_CATEGORIES_CONFIG)
        if DEFAULT_CATEGORIES_CONFIG.exists()
        else {}
    )
    business_category = normalize_business_category(category.strip(), aliases)
    db_path = settings.db_path

    batch_id = create_batch(
        db_path,
        category=category.strip(),
        platform=platform,
        requested_count=len(assets),
        media_format=media_format,
        note="selected-drive-ai",
    )

    for idx, asset in enumerate(assets):
        payload = dict(asset)
        payload.setdefault("marketing_objectives", list(marketing_objectives or []))
        payload.setdefault("channels", list(channels or []))
        payload["business_category"] = business_category
        add_batch_item(
            db_path,
            batch_id=batch_id,
            item_index=idx + 1,
            status="queued",
            source_asset_id=str(asset.get("file_id") or ""),
            source_asset_name=str(asset.get("name") or ""),
            business_category=business_category,
            payload=payload,
            media_format=media_format,
        )

    return int(batch_id)


def serialize_drive_asset(asset: DriveAsset) -> dict:
    path_hint = "/".join(asset.path_segments[-3:]) if asset.path_segments else ""
    return {
        "file_id": asset.file_id,
        "name": asset.name,
        "mime_type": asset.mime_type,
        "category": asset.category,
        "path_segments": list(asset.path_segments or []),
        "path_hint": path_hint,
    }
