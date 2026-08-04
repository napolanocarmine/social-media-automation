from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from social_automation.api.deps import SettingsDep
from social_automation.api.schemas.uploads import (
    UploadBatchResponse,
    UploadDimensionValidation,
    UploadItemResult,
    UploadValidateResponse,
)
from social_automation.models import MediaFormat, Platform
from social_automation.services.batch_queue import process_batch_queue
from social_automation.services.upload import (
    parse_objectives_list,
    parse_resize_actions,
    register_uploaded_image,
    start_upload_ai_batch,
    validate_upload_bytes,
)
from social_automation.visual.input_fidelity import (
    normalize_input_fidelity,
    settings_with_input_fidelity,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

_ALLOWED_MIME_PREFIXES = ("image/",)


def _parse_platform_media(
    platform_raw: str,
    format_raw: str,
) -> tuple[Platform, MediaFormat]:
    try:
        media_format = MediaFormat(format_raw.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if media_format == MediaFormat.STORY:
        platform = Platform.INSTAGRAM
    else:
        try:
            platform = Platform(platform_raw.strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return platform, media_format


def _channels_for(platform: Platform, media_format: MediaFormat) -> list[str]:
    if media_format == MediaFormat.STORY:
        return ["instagram", "facebook"]
    return [platform.value]


@router.post("/validate", response_model=UploadValidateResponse)
async def validate_upload(
    file: UploadFile = File(...),
    platform: str = Form(...),
    media_format: str = Form(...),
) -> UploadValidateResponse:
    plat, fmt = _parse_platform_media(platform, media_format)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File vuoto")
    content_type = (file.content_type or "").lower()
    if content_type and not content_type.startswith(_ALLOWED_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail="Solo immagini supportate")
    try:
        dims = validate_upload_bytes(data, platform=plat, media_format=fmt)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadValidateResponse(
        filename=file.filename or "upload.jpg",
        dimensions=UploadDimensionValidation(**dims),
    )


def _form_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@router.post("", response_model=UploadBatchResponse)
async def upload_images(
    settings: SettingsDep,
    files: list[UploadFile] = File(...),
    platform: str = Form(...),
    media_format: str = Form(...),
    category: str = Form(...),
    run_ai_retouch: str = Form("false"),
    marketing_objectives: str = Form("[]"),
    resize_actions: str = Form("{}"),
    visual_image_input_fidelity: str | None = Form(None),
) -> UploadBatchResponse:
    ai_retouch = _form_bool(run_ai_retouch)
    if not files:
        raise HTTPException(status_code=400, detail="Seleziona almeno un file")

    plat, fmt = _parse_platform_media(platform, media_format)
    if not category.strip():
        raise HTTPException(status_code=422, detail="Categoria obbligatoria")

    try:
        objectives = parse_objectives_list(marketing_objectives)
        actions = parse_resize_actions(resize_actions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    fidelity_override: str | None = None
    if visual_image_input_fidelity:
        try:
            fidelity_override = normalize_input_fidelity(visual_image_input_fidelity)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    channels = _channels_for(plat, fmt)
    output_dir = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_items: list[dict] = []
    for upload in files:
        data = await upload.read()
        if not data:
            continue
        content_type = (upload.content_type or "").lower()
        if content_type and not content_type.startswith(_ALLOWED_MIME_PREFIXES):
            raise HTTPException(
                status_code=400,
                detail=f"Formato non supportato: {upload.filename}",
            )
        filename = upload.filename or "upload.jpg"
        upload_id = uuid.uuid4().hex[:12]
        source_path = output_dir / f"upload_src_{upload_id}.jpg"
        source_path.write_bytes(data)
        action = actions.get(filename, "keep")
        saved_items.append(
            {
                "local_path": str(source_path),
                "name": filename,
                "mime_type": upload.content_type or "image/jpeg",
                "upload_id": upload_id,
                "resize_action": action,
            }
        )

    if not saved_items:
        raise HTTPException(status_code=400, detail="Nessun file valido")

    results: list[UploadItemResult] = []
    image_ids: list[int] = []

    if ai_retouch:
        try:
            batch_id = start_upload_ai_batch(
                settings,
                category=category.strip(),
                platform=plat,
                media_format=fmt,
                items=saved_items,
                marketing_objectives=objectives,
                channels=channels,
                visual_image_input_fidelity=fidelity_override,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if settings.batch_auto_process:
            effective = settings_with_input_fidelity(settings, fidelity_override)
            process_batch_queue(effective, max_items=len(saved_items))

        for item in saved_items:
            results.append(
                UploadItemResult(
                    name=str(item["name"]),
                    processed_file=None,
                )
            )
        return UploadBatchResponse(
            run_ai_retouch=True,
            batch_id=batch_id,
            image_ids=[],
            items=results,
            redirect="/workflow/output",
        )

    for item in saved_items:
        try:
            out = register_uploaded_image(
                settings,
                source_path=Path(str(item["local_path"])),
                image_name=str(item["name"]),
                platform=plat,
                media_format=fmt,
                business_category=category.strip(),
                marketing_objectives=objectives,
                channels=channels,
                resize_action=item["resize_action"],
            )
            image_ids.append(int(out["image_id"]))
            results.append(
                UploadItemResult(
                    image_id=int(out["image_id"]),
                    name=str(out["name"]),
                    processed_file=str(out.get("processed_file") or ""),
                    dimensions=UploadDimensionValidation(**out["dimensions"]),
                )
            )
        except Exception as exc:
            results.append(
                UploadItemResult(
                    name=str(item["name"]),
                    error=str(exc).strip() or repr(exc),
                )
            )

    if not image_ids:
        raise HTTPException(status_code=400, detail="Nessun upload registrato")

    redirect = f"/workflow/plan?format={fmt.value}"
    if fmt == MediaFormat.POST:
        redirect += f"&platform={plat.value}"
    if len(image_ids) == 1:
        redirect += f"&imageId={image_ids[0]}"

    return UploadBatchResponse(
        run_ai_retouch=False,
        batch_id=None,
        image_ids=image_ids,
        items=results,
        redirect=redirect,
    )
