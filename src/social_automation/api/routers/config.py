from __future__ import annotations

import os

from fastapi import APIRouter

from social_automation.api.deps import SettingsDep
from social_automation.api.schemas.drive_batches import CategoriesResponse
from social_automation.brand.prompt_context import MARKETING_OBJECTIVES
from social_automation.services.drive_selection import (
    DEFAULT_CATEGORIES_CONFIG,
    business_category_options,
)
from social_automation.visual.input_fidelity import INPUT_FIDELITY_LABELS, INPUT_FIDELITY_OPTIONS

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/categories", response_model=CategoriesResponse)
def list_categories() -> CategoriesResponse:
    return CategoriesResponse(categories=business_category_options(DEFAULT_CATEGORIES_CONFIG))


@router.get("/marketing-objectives")
def list_marketing_objectives() -> dict[str, list[str]]:
    return {"objectives": list(MARKETING_OBJECTIVES)}


@router.get("/visual-pipeline")
def visual_pipeline_config(settings: SettingsDep) -> dict:
    return {
        "input_fidelity_options": [
            {"value": value, "label": INPUT_FIDELITY_LABELS[value]}
            for value in INPUT_FIDELITY_OPTIONS
        ],
        "default_input_fidelity": settings.visual_image_input_fidelity,
    }


@router.get("/dispatch")
def dispatch_config() -> dict:
    """Modalità dispatch: manuale (sempre) + automatico (scheduler Docker/launchd)."""
    interval = max(60, int(os.getenv("DISPATCH_INTERVAL_SECONDS", "600")))
    return {
        "manual_enabled": True,
        "auto_enabled": True,
        "auto_interval_seconds": interval,
        "auto_interval_minutes": interval // 60,
        "manual_endpoints": {
            "run": "/api/v1/dispatch/run",
            "dry_run": "/api/v1/dispatch/dry-run",
            "due": "/api/v1/dispatch/due",
        },
        "cli_command": "python -m social_automation dispatch-scheduled",
    }
