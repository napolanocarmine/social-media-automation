"""Espansione slot editoriali da schedule.yaml e occupazione calendario."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from social_automation.app_timezone import app_timezone_name, app_tz, now_app
from social_automation.db.store import list_calendar_items
from social_automation.models import EditorialSchedule, Platform, ScheduleSlot

_WEEKDAY_TO_INT: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class ResolvedSlot:
    """Istanza concreta di uno slot editoriale."""

    platform: Platform
    scheduled_for: datetime
    weekday: str
    time_hhmm: str
    category: str | None = None


def _parse_hhmm(time_hhmm: str) -> tuple[int, int]:
    parts = str(time_hhmm).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Orario slot non valido: {time_hhmm!r}")
    hh, mm = int(parts[0]), int(parts[1])
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise ValueError(f"Orario slot fuori range: {time_hhmm!r}")
    return hh, mm


def _slot_category(slot: ScheduleSlot) -> str | None:
    cat = str(slot.category or "").strip().lower()
    return cat or None


def iter_schedule_slots(
    schedule: EditorialSchedule,
    *,
    start: datetime,
    end: datetime,
) -> list[ResolvedSlot]:
    """Genera occorrenze concrete degli slot tra ``start`` e ``end`` (escluso end)."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    tz = ZoneInfo(schedule.timezone or app_timezone_name())
    start_local = start.astimezone(tz)
    end_local = end.astimezone(tz)
    out: list[ResolvedSlot] = []
    day = start_local.date()
    end_day = end_local.date()
    while day <= end_day:
        wd = day.weekday()
        for slot in schedule.slots:
            target_wd = _WEEKDAY_TO_INT.get(str(slot.weekday).strip().lower())
            if target_wd is None or target_wd != wd:
                continue
            hh, mm = _parse_hhmm(slot.time_hhmm)
            local_dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
            if local_dt < start_local or local_dt >= end_local:
                continue
            cat = _slot_category(slot)
            for plat in slot.platforms:
                out.append(
                    ResolvedSlot(
                        platform=plat,
                        scheduled_for=local_dt.astimezone(UTC),
                        weekday=str(slot.weekday).lower(),
                        time_hhmm=slot.time_hhmm,
                        category=cat,
                    )
                )
        day += timedelta(days=1)
    out.sort(key=lambda s: (s.scheduled_for, s.platform.value))
    return out


def _slot_occupied(
    db_path,
    *,
    platform: Platform,
    scheduled_for: datetime,
    tolerance_minutes: int = 5,
) -> bool:
    """True se esiste già un evento pianificato nello stesso slot (± tolleranza)."""
    if scheduled_for.tzinfo is None:
        scheduled_for = scheduled_for.replace(tzinfo=UTC)
    start = scheduled_for - timedelta(minutes=tolerance_minutes)
    end = scheduled_for + timedelta(minutes=tolerance_minutes + 1)
    rows = list_calendar_items(
        db_path,
        start_inclusive=start,
        end_exclusive=end,
        platform=platform,
        limit=50,
    )
    return len(rows) > 0


def list_free_schedule_slots(
    db_path,
    schedule: EditorialSchedule,
    *,
    start: datetime,
    end: datetime,
    platform: Platform | None = None,
) -> list[ResolvedSlot]:
    """Slot editoriali liberi (nessun evento pianificato nel calendario)."""
    candidates = iter_schedule_slots(schedule, start=start, end=end)
    free: list[ResolvedSlot] = []
    for slot in candidates:
        if platform is not None and slot.platform != platform:
            continue
        if not _slot_occupied(db_path, platform=slot.platform, scheduled_for=slot.scheduled_for):
            free.append(slot)
    return free


def suggest_next_free_slot(
    db_path,
    schedule: EditorialSchedule,
    *,
    platform: Platform,
    after: datetime | None = None,
    horizon_days: int = 28,
) -> ResolvedSlot | None:
    """Primo slot libero per la piattaforma entro ``horizon_days`` da ``after``."""
    base = after or now_app()
    if base.tzinfo is None:
        base = base.replace(tzinfo=app_tz())
    end = base + timedelta(days=max(1, int(horizon_days)))
    free = list_free_schedule_slots(db_path, schedule, start=base, end=end, platform=platform)
    return free[0] if free else None
