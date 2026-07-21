"""Endpoint cron Vercel (dispatch + batch queue)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException, Query

from social_automation.api.deps import SettingsDep
from social_automation.app_timezone import (
    app_timezone_name,
    is_within_dispatch_cron_window,
    now_app,
)
from social_automation.services.batch_queue import process_next_batch_item
from social_automation.services.dispatch import run_dispatch

router = APIRouter(prefix="/cron", tags=["cron"])


def _verify_cron_auth(
    settings: SettingsDep,
    authorization: str | None = Header(None),
    secret: str | None = Query(None),
) -> None:
    expected_secret = (settings.cron_secret or os.environ.get("CRON_SECRET") or "").strip()
    if not expected_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET non configurato")

    auth_ok = authorization == f"Bearer {expected_secret}"
    query_ok = secret == expected_secret
    if not auth_ok and not query_ok:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _production_only() -> None:
    env = (os.environ.get("VERCEL_ENV") or "").strip().lower()
    if env == "development":
        raise HTTPException(status_code=403, detail="Cron non disponibile in development Vercel")


@router.get("/dispatch")
def cron_dispatch(
    settings: SettingsDep,
    authorization: str | None = Header(None),
    secret: str | None = Query(None),
):
    _production_only()
    _verify_cron_auth(settings, authorization, secret)
    if not is_within_dispatch_cron_window(settings):
        now_local = now_app(settings)
        return {
            "ok": True,
            "skipped": True,
            "reason": "outside_dispatch_window",
            "timezone": app_timezone_name(settings),
            "local_time": now_local.isoformat(),
            "window": f"{settings.dispatch_cron_hour_start:02d}:00-{settings.dispatch_cron_hour_end:02d}:59",
            "published": 0,
            "failed": 0,
        }
    result = run_dispatch(
        settings.db_path,
        limit=int(os.getenv("DISPATCH_LIMIT", "100")),
        settings=settings,
    )
    return {"ok": True, **result}


@router.get("/process-batch")
def cron_process_batch(
    settings: SettingsDep,
    authorization: str | None = Header(None),
    secret: str | None = Query(None),
):
    _production_only()
    _verify_cron_auth(settings, authorization, secret)
    result = process_next_batch_item(settings)
    return {"ok": True, **result}
