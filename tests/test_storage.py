from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.storage import (
    SHANGHAI_TZ,
    aggregate_price_history,
    append_price_record,
    cleanup_old_history,
    subtract_months,
)


def record(timestamp: str, price: str) -> dict[str, object]:
    return {"timestamp": timestamp, "price": float(price), "cluster_id": "1", "url": "https://example.test"}


def test_hour_buckets_are_left_closed_right_open() -> None:
    points = aggregate_price_history([record("2026-08-28T10:00:00+08:00", "40"), record("2026-08-28T10:30:00+08:00", "45"), record("2026-08-28T10:59:59+08:00", "50"), record("2026-08-28T11:00:00+08:00", "60")], "hour")
    assert [(point["time"], point["average"]) for point in points] == [("2026-08-28T10:00:00+08:00", 45.0), ("2026-08-28T11:00:00+08:00", 60.0)]


def test_day_boundary_and_raw_statistics() -> None:
    points = aggregate_price_history([record("2026-08-28T00:10:00+08:00", "40"), record("2026-08-28T10:00:00+08:00", "45"), record("2026-08-28T15:30:00+08:00", "50"), record("2026-08-28T23:59:59+08:00", "45"), record("2026-08-29T00:00:00+08:00", "99")], "day")
    assert points[0] == {"time": "2026-08-28T00:00:00+08:00", "max": 50.0, "min": 40.0, "average": 45.0}
    assert points[1]["average"] == 99.0


def test_utc_timestamp_is_grouped_in_shanghai_hour() -> None:
    points = aggregate_price_history([record("2026-08-28T02:30:00+00:00", "45")], "hour")
    assert points[0]["time"] == "2026-08-28T10:00:00+08:00"


def test_empty_buckets_are_null_not_zero() -> None:
    points = aggregate_price_history([record("2026-08-28T10:05:00+08:00", "45"), record("2026-08-28T12:05:00+08:00", "50")], "hour")
    assert points[1] == {"time": "2026-08-28T11:00:00+08:00", "max": None, "min": None, "average": None}


def test_natural_month_cleanup_handles_month_end_and_leap_year() -> None:
    now = datetime(2024, 5, 31, 14, tzinfo=SHANGHAI_TZ)
    assert subtract_months(now, 3) == datetime(2024, 2, 29, 14, tzinfo=SHANGHAI_TZ)
    kept = cleanup_old_history([record("2024-02-29T14:00:00+08:00", "1"), record("2024-02-29T13:59:59+08:00", "2"), record("2024-05-30T00:00:00+08:00", "3")], now)
    assert [item["price"] for item in kept] == [1.0, 3.0]


def test_append_records_uses_shanghai_timestamp() -> None:
    timestamp = datetime(2026, 8, 28, 2, 30, tzinfo=ZoneInfo("UTC"))
    records = append_price_record([], cluster_id="1", price=Decimal("45.5"), url="u", timestamp=timestamp)
    assert records[0]["timestamp"] == "2026-08-28T10:30:00+08:00"
