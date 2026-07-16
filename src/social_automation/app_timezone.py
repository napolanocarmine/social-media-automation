"""Fuso orario applicativo (default Europe/Rome)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from social_automation.settings import Settings

DEFAULT_APP_TIMEZONE = "Europe/Rome"


def app_timezone_name(settings: Settings | None = None) -> str:
    if settings is not None:
        tz = (getattr(settings, "app_timezone", "") or "").strip()
        if tz:
            return tz
    return DEFAULT_APP_TIMEZONE


def app_tz(settings: Settings | None = None) -> ZoneInfo:
    return ZoneInfo(app_timezone_name(settings))


def now_app(settings: Settings | None = None) -> datetime:
    """Ora corrente nel fuso applicativo (timezone-aware)."""
    return datetime.now(app_tz(settings))


def is_within_dispatch_cron_window(settings: Settings | None = None) -> bool:
    """True se l'ora corrente (APP_TIMEZONE) è nella finestra dispatch cron configurata."""
    if settings is None:
        return True
    start = int(getattr(settings, "dispatch_cron_hour_start", 11))
    end = int(getattr(settings, "dispatch_cron_hour_end", 22))
    if start > end:
        return True
    hour = now_app(settings).hour
    return start <= hour <= end


def today_app(settings: Settings | None = None) -> date:
    return now_app(settings).date()


def combine_app(d: date, t: time, settings: Settings | None = None) -> datetime:
    """Combina data e ora nel fuso applicativo (timezone-aware)."""
    return datetime(
        d.year,
        d.month,
        d.day,
        t.hour,
        t.minute,
        t.second,
        t.microsecond,
        tzinfo=app_tz(settings),
    )


def normalize_scheduled_for(
    dt: datetime | None,
    settings: Settings | None = None,
) -> datetime | None:
    """Normalizza un datetime di pianificazione nel fuso applicativo."""
    if dt is None:
        return None
    tz = app_tz(settings)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def scheduled_for_to_db(
    dt: datetime | None,
    settings: Settings | None = None,
) -> datetime | None:
    """Converte un datetime di pianificazione in UTC per persistenza/comparazioni SQL."""
    local = normalize_scheduled_for(dt, settings)
    if local is None:
        return None
    return local.astimezone(UTC)


def scheduled_for_db_iso(
    dt: datetime | None,
    settings: Settings | None = None,
) -> str | None:
    stored = scheduled_for_to_db(dt, settings)
    return stored.isoformat() if stored else None


def query_datetime_utc(dt: datetime, settings: Settings | None = None) -> datetime:
    """Normalizza un bound di query al UTC timezone-aware."""
    if dt.tzinfo is None:
        return normalize_scheduled_for(dt, settings).astimezone(UTC)
    return dt.astimezone(UTC)


def parse_iso_datetime(raw: str, settings: Settings | None = None) -> datetime | None:
    """
    Interpreta ISO da DB/UI.

    Valori naive (legacy) sono trattati come ora locale nel fuso applicativo.
    """
    text = (raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=app_tz(settings))
    return dt.astimezone(app_tz(settings))


def format_hhmm_local(raw: str, settings: Settings | None = None) -> str:
    dt = parse_iso_datetime(raw, settings)
    if dt is None:
        return (raw or "")[:16]
    return dt.strftime("%H:%M")


def month_bounds_local(
    year: int,
    month: int,
    settings: Settings | None = None,
) -> tuple[datetime, datetime]:
    tz = app_tz(settings)
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz)
    return start, end
