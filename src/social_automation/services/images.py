"""Servizio immagini: output AI, approvazione, media path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from social_automation.db.store import (
    count_ai_output_images,
    count_images_for_manual_publication_review,
    get_image_record,
    latest_metadata_for_image,
    list_ai_output_images,
    list_images_for_manual_publication_review,
    set_image_manual_publication_valid,
)
from social_automation.models import MediaFormat, Platform
from social_automation.services.drive_selection import business_category_options
from social_automation.services.media import (
    media_urls_for_image,
    resolve_original_path,
    resolve_processed_path,
)
from social_automation.settings import Settings, load_settings
from social_automation.workflow.process_photo import revert_image_to_original

ApprovalFilter = Literal["pending", "approved", "rejected", "all"]
ApprovalAction = Literal["approve", "reject", "use_original"]

APPROVAL_PAGE_SIZE_DEFAULT = 20
AI_OUTPUT_LIMIT_DEFAULT = 24


def _approval_status_label(value: Any) -> str:
    if value is None:
        return "pending"
    return "approved" if int(value) == 1 else "rejected"


def _serialize_image_row(
    row: dict[str, Any],
    *,
    db_path: Path,
    settings: Settings | None = None,
    include_metadata: bool = False,
) -> dict[str, Any]:
    image_id = int(row["id"])
    processed = resolve_processed_path(db_path, image_id=image_id, settings=settings)
    original = resolve_original_path(db_path, image_id=image_id, row=row, settings=settings)
    meta = latest_metadata_for_image(db_path, image_id=image_id) if include_metadata else None
    visual_method: str | None = None
    if meta and meta.get("metadata_json"):
        try:
            mj_raw = meta.get("metadata_json")
            mj = json.loads(mj_raw) if isinstance(mj_raw, str) else mj_raw
            if isinstance(mj, dict):
                visual_method = str(mj.get("visual_method") or "").strip() or None
        except (ValueError, TypeError):
            pass

    return {
        "id": image_id,
        "name": str(row.get("name") or ""),
        "path": str(row.get("path") or ""),
        "business_category": str(row.get("business_category") or "").strip() or None,
        "approval_status": _approval_status_label(row.get("is_valid_for_publication")),
        "visual_score": float(row["visual_score"]) if row.get("visual_score") is not None else None,
        "visual_status": str(row.get("visual_status") or "").strip() or None,
        "editing_required": bool(int(row["editing_required"]))
        if row.get("editing_required") is not None
        else None,
        "visual_method": visual_method,
        "has_processed_file": processed is not None,
        "has_original_file": original is not None,
        "media": media_urls_for_image(image_id),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def list_ai_output(
    db_path: Path,
    *,
    approval_filter: ApprovalFilter = "all",
    limit: int = AI_OUTPUT_LIMIT_DEFAULT,
    offset: int = 0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    rows = list_ai_output_images(
        db_path,
        approval_filter=approval_filter,
        limit=limit,
        offset=offset,
    )
    total = count_ai_output_images(db_path, approval_filter=approval_filter)
    return {
        "items": [
            _serialize_image_row(r, db_path=db_path, settings=settings) for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_image_detail(
    db_path: Path,
    *,
    image_id: int,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    row = get_image_record(db_path, image_id=image_id)
    if row is None:
        return None
    meta = latest_metadata_for_image(db_path, image_id=image_id)
    if meta:
        row = {**row, "business_category": meta.get("business_category")}
    return _serialize_image_row(row, db_path=db_path, settings=settings, include_metadata=True)


def list_pending_approval(
    db_path: Path,
    *,
    platform: Platform,
    media_format: MediaFormat,
    business_category: str | None,
    page: int = 0,
    page_size: int = APPROVAL_PAGE_SIZE_DEFAULT,
    settings: Settings | None = None,
) -> dict[str, Any]:
    page = max(0, int(page))
    page_size = max(1, min(100, int(page_size)))
    offset = page * page_size
    total = count_images_for_manual_publication_review(
        db_path,
        platform=platform,
        business_category=business_category,
        media_format=media_format,
        require_quality_pass=False,
        pending_manual_only=True,
        require_ai_output=False,
    )
    rows = list_images_for_manual_publication_review(
        db_path,
        platform=platform,
        business_category=business_category,
        media_format=media_format,
        require_quality_pass=False,
        pending_manual_only=True,
        require_ai_output=False,
        limit=page_size,
        offset=offset,
    )
    return {
        "items": [
            _serialize_image_row(r, db_path=db_path, settings=settings, include_metadata=True)
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size) if total else 0,
    }


def apply_approval_action(
    db_path: Path,
    *,
    image_id: int,
    action: ApprovalAction,
    settings: Settings | None = None,
) -> None:
    s = settings or load_settings()
    row = get_image_record(db_path, image_id=image_id)
    if row is None:
        raise ValueError(f"Immagine #{image_id} non trovata")

    if action == "use_original":
        revert_image_to_original(image_id, settings=s, approve=True)
        return
    if action == "approve":
        set_image_manual_publication_valid(db_path, image_id=image_id, value=1)
        return
    if action == "reject":
        set_image_manual_publication_valid(db_path, image_id=image_id, value=0)
        return
    raise ValueError(f"Azione non supportata: {action}")


def list_business_categories() -> list[str]:
    return business_category_options(Path("config/categories.yaml"))
