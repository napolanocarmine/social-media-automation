"""Elaborazione foto Drive → Story AI (ritocco + copy)."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from social_automation.config_loaders import resolve_drive_folder_id
from social_automation.drive.client import DriveClient
from social_automation.drive.selection import normalize_business_category
from social_automation.models import MediaFormat, Platform
from social_automation.services.drive_selection import (
    DEFAULT_CATEGORIES_CONFIG,
    pick_latest_asset,
)
from social_automation.settings import load_settings
from social_automation.workflow.process_photo import process_local_photo


def run_process_photo(
    *,
    category: str,
    platform: Platform,
    target_year: int | None = None,
    target_month: int | None = None,
    media_format: MediaFormat = MediaFormat.POST,
    open_browser: bool = True,
) -> dict[str, Any]:
    """Drive → Story AI (ritocco + copy) → export foto."""
    settings = load_settings()
    categories_config = DEFAULT_CATEGORIES_CONFIG
    folder_id = resolve_drive_folder_id(
        folder_id_arg="",
        folder_id_env=settings.google_drive_folder_id,
        categories_yaml=categories_config,
    )
    if not folder_id:
        raise RuntimeError(
            "Manca folder id Drive: compila il campo o usa GOOGLE_DRIVE_FOLDER_ID/"
            "drive_root_folder_id nel file categorie."
        )

    drive_client = DriveClient.from_settings(settings, open_browser=open_browser)
    selected, aliases = pick_latest_asset(
        drive_client,
        folder_id,
        category=category,
        categories_config=categories_config,
        db_path=settings.db_path,
        platform=platform,
        target_year=target_year,
        target_month=target_month,
        media_format=media_format,
    )
    business_category = normalize_business_category(category, aliases)

    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = mimetypes.guess_extension(selected.mime_type) or ".jpg"
    source_path = output_dir / f"drive_{selected.file_id}{suffix}"
    source_path.write_bytes(drive_client.download_file_bytes(selected.file_id))

    out = process_local_photo(
        source_path,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        settings=settings,
        image_name=selected.name,
        source_asset_id=selected.file_id,
        source_asset_name=selected.name,
    )
    return {
        "selected_asset": f"{selected.file_id}\t{selected.name}",
        "source_asset_id": selected.file_id,
        "source_asset_name": selected.name,
        "business_category": business_category,
        "platform": platform.value,
        "media_format": media_format.value,
        "rendered_file": out["processed_file"],
        "processed_file": out["processed_file"],
        "rendered_name": Path(out["processed_file"]).name,
        "db_image_id": str(out["image_id"]),
        "copy": out.get("copy") or {},
    }
