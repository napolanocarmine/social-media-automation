"""Workflow foto: Drive → Visual Producer V2 → Copy → DB."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Literal

from social_automation.brand.agent import generate_copy_pack
from social_automation.brand.copy_pack import copy_approved
from social_automation.brand.openai_json import api_configured
from social_automation.config_loaders import (
    load_category_aliases,
    resolve_drive_folder_id,
)
from social_automation.db.store import (
    get_image_record,
    latest_metadata_for_image,
    record_processed_artifacts,
    set_image_manual_publication_valid,
    update_image_copy_json,
    update_image_visual_state,
    update_vision_eval,
)
from social_automation.drive.client import DriveClient
from social_automation.drive.selection import normalize_business_category
from social_automation.models import DriveAsset, MediaFormat, Platform
from social_automation.processing.image_adjust import apply_retouch_to_file, crop_mode_for_platform
from social_automation.settings import Settings, load_settings
from social_automation.services.media import maybe_persist_processed_media_to_blob
from social_automation.visual.models import VisualProductionResult
from social_automation.visual.producer import produce_final_asset
from social_automation.workflow.render import pick_latest_unrendered_asset

_DEFAULT_CATEGORIES = Path("config/categories.yaml")
ProcessMode = Literal["auto", "retouch_copy"]


def _visual_review_dict(result: VisualProductionResult) -> dict[str, Any]:
    review = result.review
    payload: dict[str, Any] = {
        "score": review.score,
        "approved": review.approved,
        "needs_editing": review.needs_editing,
        "reasoning": review.reasoning,
        "suggested_format": review.suggested_format,
        "method": result.method,
        "producer_notes": result.producer_notes,
        "visual_status": result.visual_status,
    }
    if result.edit_plan_json:
        payload["edit_plan"] = result.edit_plan_json
    return payload


def process_local_photo(
    source_path: Path,
    *,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
    business_category: str | None = None,
    settings: Settings | None = None,
    mode: ProcessMode = "auto",
    image_name: str | None = None,
    source_asset_id: str | None = None,
    source_asset_name: str | None = None,
    auto_approve: bool = True,
    generate_copy: bool = True,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> dict[str, Any]:
    """Visual Review → asset finale; copy opzionale (generato in Pianifica)."""
    s = settings or load_settings()
    if not api_configured(api_key=s.vision_api_key, model=s.vision_model):
        raise ValueError("VISION_API_KEY e VISION_MODEL richiesti per Story AI")

    biz = (business_category or "").strip().lower() or None
    fid = (source_asset_id or source_path.stem).strip()

    production = produce_final_asset(
        source_path,
        settings=s,
        platform=platform,
        media_format=media_format,
        business_category=biz,
        file_id=fid,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
    )
    final_path = Path(production.final_path)

    copy_data: dict[str, Any] | None = None
    if generate_copy:
        copy_data = generate_copy_pack(
            final_path,
            settings=s,
            business_category=biz,
            platform=platform,
            media_format=media_format,
            marketing_objectives=marketing_objectives,
            marketing_objective=marketing_objective,
            channels=channels,
        )

    retouch_data: dict[str, Any] = production.retouch_json or _visual_review_dict(production)
    visual_review = _visual_review_dict(production)

    meta = {
        "platform": platform.value,
        "media_format": media_format.value,
        "business_category": biz,
        "source_file": str(source_path),
        "output_file": str(final_path),
        "mode": "story_ai_v2",
        "process_mode": mode,
        "visual_method": production.method,
        "visual_status": production.visual_status,
        "marketing_objectives": marketing_objectives or [],
        "marketing_objective": marketing_objective,
        "channels": [c.value for c in (channels or [])],
    }
    image_id = record_processed_artifacts(
        s.db_path,
        image_name=image_name or source_path.name,
        image_path=final_path,
        source_asset_id=source_asset_id,
        source_asset_name=source_asset_name,
        business_category=biz,
        metadata_payload=meta,
        retouch_json=retouch_data,
        copy_json=copy_data if generate_copy else None,
        original_path=production.original_path,
        generated_image_path=production.generated_image_path,
        visual_score=production.visual_score,
        visual_status=production.visual_status,
        editing_required=production.editing_required,
    )

    blob_urls = maybe_persist_processed_media_to_blob(
        s.db_path,
        image_id=image_id,
        settings=s,
        processed_path=final_path,
        source_path=source_path,
        original_path=production.original_path,
        generated_image_path=production.generated_image_path,
        source_asset_id=source_asset_id,
        platform=platform.value,
    )
    if blob_urls.get("path"):
        final_path = Path(blob_urls["path"])

    visual_ok = production.review.approved and production.visual_score >= s.visual_review_score_manual
    copy_ok = copy_approved(copy_data) if copy_data else False
    if auto_approve and visual_ok and not production.review.needs_editing and (
        not generate_copy or copy_ok
    ):
        set_image_manual_publication_valid(s.db_path, image_id=image_id, value=1)
        reason = "Story AI V2 approved"
        if copy_data:
            reason = str((copy_data.get("final_review") or {}).get("notes") or reason)
        update_vision_eval(
            s.db_path,
            image_id=image_id,
            vision_pass=1,
            reason=reason,
        )
    else:
        set_image_manual_publication_valid(s.db_path, image_id=image_id, value=None)
        if not visual_ok or production.visual_status == "manual_review":
            update_vision_eval(
                s.db_path,
                image_id=image_id,
                vision_pass=0,
                reason=production.producer_notes or "visual review: review manuale consigliata",
            )

    return {
        "image_id": image_id,
        "processed_file": str(final_path),
        "business_category": biz,
        "platform": platform.value,
        "media_format": media_format.value,
        "retouch": retouch_data,
        "copy": copy_data or {},
        "visual_review": visual_review,
        "visual_score": production.visual_score,
        "visual_status": production.visual_status,
        "editing_required": production.editing_required,
        "source_asset_id": source_asset_id,
    }


def process_drive_asset(
    asset: DriveAsset,
    *,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
    settings: Settings | None = None,
    business_category: str | None = None,
    drive: DriveClient | None = None,
    mode: ProcessMode = "auto",
    auto_approve: bool = False,
    generate_copy: bool = False,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
) -> dict[str, Any]:
    """Scarica un asset Drive scelto dall'utente e lo passa a Story AI V2."""
    s = settings or load_settings()
    oauth_browser = (s.google_oauth_browser or "").strip() or None
    drv = drive or DriveClient.from_paths(
        s.google_credentials_path,
        s.google_token_path,
        open_browser=True,
        oauth_browser=oauth_browser,
    )
    biz = (business_category or asset.category or "photo").strip().lower()
    output_dir = s.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = mimetypes.guess_extension(asset.mime_type) or ".jpg"
    source_path = output_dir / f"drive_{asset.file_id}{suffix}"
    source_path.write_bytes(drv.download_file_bytes(asset.file_id))
    try:
        normalize_image_file(source_path)
    except Exception:
        pass
    out = process_local_photo(
        source_path,
        platform=platform,
        media_format=media_format,
        business_category=biz,
        settings=s,
        mode=mode,
        image_name=asset.name,
        source_asset_id=asset.file_id,
        source_asset_name=asset.name,
        auto_approve=auto_approve,
        generate_copy=generate_copy,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
    )
    return {
        **out,
        "source_asset_id": asset.file_id,
        "source_asset_name": asset.name,
        "source_file": str(source_path),
    }


def process_drive_story_photo(
    *,
    category: str,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
    settings: Settings | None = None,
    categories_config: Path | None = None,
    mode: ProcessMode = "auto",
) -> dict[str, Any]:
    """Scarica asset Drive, Story AI V2, export, registra in DB."""
    s = settings or load_settings()
    cat_cfg = categories_config or _DEFAULT_CATEGORIES
    folder_id = resolve_drive_folder_id(
        folder_id_arg="",
        folder_id_env=s.google_drive_folder_id,
        categories_yaml=cat_cfg,
    )
    if not folder_id:
        raise RuntimeError("Manca folder id Drive (GOOGLE_DRIVE_FOLDER_ID o categories.yaml)")

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
            f"Nessun asset Drive non ancora processato per categoria={category!r} "
            f"platform={platform.value} format={media_format.value}"
        )

    aliases = load_category_aliases(cat_cfg) if cat_cfg.exists() else {}
    business_category = normalize_business_category(category, aliases)

    output_dir = s.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = mimetypes.guess_extension(selected.mime_type) or ".jpg"
    source_path = output_dir / f"drive_{selected.file_id}{suffix}"
    source_path.write_bytes(drive.download_file_bytes(selected.file_id))
    try:
        normalize_image_file(source_path)
    except Exception:
        pass

    return process_local_photo(
        source_path,
        platform=platform,
        media_format=media_format,
        business_category=business_category,
        settings=s,
        mode=mode,
        image_name=selected.name,
        source_asset_id=selected.file_id,
        source_asset_name=selected.name,
    )


def generate_copy_for_image(
    image_id: int,
    *,
    platform: Platform,
    media_format: MediaFormat = MediaFormat.POST,
    marketing_objectives: list[str] | None = None,
    marketing_objective: str | None = None,
    channels: list[Platform] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Genera copy pack per un'immagine già approvata e lo salva in DB."""
    s = settings or load_settings()
    if media_format == MediaFormat.STORY:
        raise ValueError("Il copy non si genera per le story")
    if not api_configured(api_key=s.vision_api_key, model=s.vision_model):
        raise ValueError("VISION_API_KEY e VISION_MODEL richiesti per Story AI")

    row = get_image_record(s.db_path, image_id=int(image_id))
    if row is None:
        raise ValueError(f"Immagine #{image_id} non trovata")
    image_path = Path(str(row.get("path") or ""))
    if not image_path.is_file():
        raise ValueError(f"File immagine assente per #{image_id}: {image_path}")

    meta = latest_metadata_for_image(s.db_path, image_id=int(image_id)) or {}
    biz = str(meta.get("business_category") or "").strip().lower() or None

    copy_data = generate_copy_pack(
        image_path,
        settings=s,
        business_category=biz,
        platform=platform,
        media_format=media_format,
        marketing_objectives=marketing_objectives,
        marketing_objective=marketing_objective,
        channels=channels,
    )
    return copy_data


def revert_image_to_original(
    image_id: int,
    *,
    settings: Settings | None = None,
    approve: bool = False,
) -> Path:
    """
    Sostituisce l'asset processato con l'originale Drive (solo crop formato, niente ritocco AI).
    """
    s = settings or load_settings()
    row = get_image_record(s.db_path, image_id=int(image_id))
    if row is None:
        raise ValueError(f"Immagine #{image_id} non trovata")

    meta = latest_metadata_for_image(s.db_path, image_id=int(image_id)) or {}
    platform_raw = str(meta.get("platform") or "").strip().lower()
    if platform_raw not in {Platform.INSTAGRAM.value, Platform.FACEBOOK.value}:
        raise ValueError(f"Piattaforma mancante per immagine #{image_id}")
    platform = Platform(platform_raw)

    fmt_raw = str(meta.get("media_format") or MediaFormat.POST.value).strip().lower()
    media_format = MediaFormat(fmt_raw if fmt_raw in {MediaFormat.POST.value, MediaFormat.STORY.value} else MediaFormat.POST.value)

    dest = Path(str(row.get("path") or ""))
    if not dest.parent:
        raise ValueError(f"Path output invalido per #{image_id}")

    original_candidates = [
        str(row.get("original_path") or "").strip(),
        str(meta.get("source_file") or "").strip(),
    ]
    source: Path | None = None
    for cand in original_candidates:
        if cand:
            p = Path(cand)
            if p.is_file():
                source = p
                break
    if source is None:
        raise ValueError(
            f"File originale non trovato per #{image_id}. "
            "Riprocessa da Drive o verifica cache locale."
        )

    crop_mode = crop_mode_for_platform(platform, media_format)
    apply_retouch_to_file(
        source,
        dest,
        {
            "crop_mode": crop_mode,
            "exposure": 0.0,
            "contrast": 0.0,
            "sharpness": 0.0,
            "saturation": 0.0,
        },
        fallback_crop=crop_mode,
    )

    update_image_visual_state(
        s.db_path,
        image_id=int(image_id),
        visual_status="original_manual",
        editing_required=False,
    )

    if approve:
        set_image_manual_publication_valid(s.db_path, image_id=int(image_id), value=1)
        update_vision_eval(
            s.db_path,
            image_id=int(image_id),
            vision_pass=1,
            reason="Approvata con immagine originale (ritocco AI scartato)",
        )
    else:
        set_image_manual_publication_valid(s.db_path, image_id=int(image_id), value=None)

    return dest
