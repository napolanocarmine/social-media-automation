from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from social_automation.api.deps import DbPathDep, SettingsDep
from social_automation.api.schemas.images import (
    ApprovalRequest,
    ApprovalResponse,
    ImageListResponse,
    ImageSummary,
)
from social_automation.api.schemas.plans import GenerateCopyRequest
from social_automation.models import MediaFormat, Platform
from social_automation.services.images import (
    AI_OUTPUT_LIMIT_DEFAULT,
    ApprovalFilter,
    apply_approval_action,
    get_image_detail,
    list_ai_output,
    list_business_categories,
    list_pending_approval,
)
from social_automation.services.planning import (
    PLANNABLE_PAGE_SIZE_DEFAULT,
    generate_image_copy,
    get_copy_pack_for_image,
    list_plannable,
)

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/ai-output", response_model=ImageListResponse)
def ai_output_list(
    settings: SettingsDep,
    db_path: DbPathDep,
    filter: ApprovalFilter = Query(default="all", alias="filter"),
    limit: int = Query(default=AI_OUTPUT_LIMIT_DEFAULT, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ImageListResponse:
    data = list_ai_output(
        db_path,
        approval_filter=filter,
        limit=limit,
        offset=offset,
        settings=settings,
    )
    return ImageListResponse(**data)


@router.get("/pending-approval", response_model=ImageListResponse)
def pending_approval_list(
    settings: SettingsDep,
    db_path: DbPathDep,
    platform: str = Query(default=Platform.INSTAGRAM.value),
    format: str = Query(default=MediaFormat.POST.value, alias="format"),
    category: str = Query(default="tutte"),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ImageListResponse:
    try:
        plat = Platform(platform.strip().lower())
        media_format = MediaFormat(format.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    category_filter = None if category.strip().lower() == "tutte" else category.strip().lower()
    data = list_pending_approval(
        db_path,
        platform=plat,
        media_format=media_format,
        business_category=category_filter,
        page=page,
        page_size=page_size,
        settings=settings,
    )
    return ImageListResponse(**data)


@router.get("/categories")
def image_categories() -> dict[str, list[str]]:
    return {"categories": ["tutte", *list_business_categories()]}


@router.get("/plannable", response_model=ImageListResponse)
def plannable_images(
    settings: SettingsDep,
    db_path: DbPathDep,
    platform: str = Query(default=Platform.INSTAGRAM.value),
    format: str = Query(default=MediaFormat.POST.value, alias="format"),
    category: str = Query(default="tutte"),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=PLANNABLE_PAGE_SIZE_DEFAULT, ge=1, le=100),
) -> ImageListResponse:
    try:
        plat = Platform(platform.strip().lower())
        media_format = MediaFormat(format.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    category_filter = None if category.strip().lower() == "tutte" else category.strip().lower()
    data = list_plannable(
        db_path,
        platform=plat,
        media_format=media_format,
        business_category=category_filter,
        page=page,
        page_size=page_size,
        settings=settings,
    )
    return ImageListResponse(**data)


@router.get("/{image_id}/copy")
def image_copy_pack(
    image_id: int,
    db_path: DbPathDep,
) -> dict:
    pack = get_copy_pack_for_image(db_path, image_id=image_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Copy non generato per questa immagine")
    return {"copy": pack}


@router.post("/{image_id}/copy/generate")
def generate_copy(
    image_id: int,
    req: GenerateCopyRequest,
    settings: SettingsDep,
    db_path: DbPathDep,
) -> dict:
    try:
        plat = Platform(req.platform.strip().lower())
        media_format = MediaFormat(req.media_format.strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        pack = generate_image_copy(
            db_path,
            image_id=image_id,
            platform=plat,
            media_format=media_format,
            marketing_objectives=req.marketing_objectives,
            marketing_objective=req.marketing_objective,
            channels=req.channels,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"copy": pack}


@router.get("/{image_id}", response_model=ImageSummary)
def image_detail(
    image_id: int,
    settings: SettingsDep,
    db_path: DbPathDep,
) -> ImageSummary:
    row = get_image_detail(db_path, image_id=image_id, settings=settings)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Immagine #{image_id} non trovata")
    return ImageSummary(**row)


@router.post("/{image_id}/approval", response_model=ApprovalResponse)
def image_approval(
    image_id: int,
    settings: SettingsDep,
    db_path: DbPathDep,
    req: ApprovalRequest,
) -> ApprovalResponse:
    action_norm = req.action.strip().lower()
    if action_norm not in {"approve", "reject", "use_original"}:
        raise HTTPException(
            status_code=422,
            detail="action deve essere approve, reject o use_original",
        )
    try:
        apply_approval_action(db_path, image_id=image_id, action=action_norm, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = get_image_detail(db_path, image_id=image_id, settings=settings)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Immagine #{image_id} non trovata")
    return ApprovalResponse(id=image_id, approval_status=row["approval_status"])
