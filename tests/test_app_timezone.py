from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from social_automation.app_timezone import (
    combine_app,
    format_hhmm_local,
    normalize_scheduled_for,
    parse_iso_datetime,
    scheduled_for_db_iso,
)
from social_automation.settings import Settings


def test_scheduled_for_db_iso_stores_utc():
    naive_rome = datetime(2026, 5, 8, 12, 0, 0)
    assert scheduled_for_db_iso(naive_rome) == "2026-05-08T10:00:00+00:00"


def test_combine_app_is_timezone_aware():
    dt = combine_app(date(2026, 6, 23), time(12, 30))
    assert dt.tzinfo == ZoneInfo("Europe/Rome")
    assert dt.hour == 12
    assert dt.minute == 30


def test_parse_naive_iso_as_rome():
    dt = parse_iso_datetime("2026-06-23T12:30:00")
    assert dt is not None
    assert dt.tzinfo == ZoneInfo("Europe/Rome")
    assert dt.strftime("%H:%M") == "12:30"


def test_normalize_scheduled_for_from_naive():
    naive = datetime(2026, 6, 23, 9, 15)
    dt = normalize_scheduled_for(naive)
    assert dt is not None
    assert dt.tzinfo == ZoneInfo("Europe/Rome")


def test_format_hhmm_local():
    assert format_hhmm_local("2026-06-23T12:30:00+02:00") == "12:30"


def test_settings_app_timezone_override():
    s = Settings(app_timezone="Europe/Rome")
    dt = combine_app(date(2026, 1, 1), time(8, 0), s)
    assert dt.tzinfo == ZoneInfo("Europe/Rome")
