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
    points = aggregate_price_history([record("2026-08-28T10:00:00+08:00", "40"), record("2026-08-28T10:30:00+08:00", "45"), record("2026-08-28T10:59:59+08:00", "50"), record("2026-08-28T11:00:00+08:00", "60")], "hour", product_id="1")
    assert [(point["time"], point["average"]) for point in points] == [("2026-08-28T10:00:00+08:00", 45.0), ("2026-08-28T11:00:00+08:00", 60.0)]


def test_day_boundary_and_raw_statistics() -> None:
    points = aggregate_price_history([record("2026-08-28T00:10:00+08:00", "40"), record("2026-08-28T10:00:00+08:00", "45"), record("2026-08-28T15:30:00+08:00", "50"), record("2026-08-28T23:59:59+08:00", "45"), record("2026-08-29T00:00:00+08:00", "99")], "day", product_id="1")
    assert points[0] == {"time": "2026-08-28T00:00:00+08:00", "max": 50.0, "min": 40.0, "average": 45.0}
    assert points[1]["average"] == 99.0


def test_utc_timestamp_is_grouped_in_shanghai_hour() -> None:
    points = aggregate_price_history([record("2026-08-28T02:30:00+00:00", "45")], "hour", product_id="1")
    assert points[0]["time"] == "2026-08-28T10:00:00+08:00"


def test_empty_buckets_are_null_not_zero() -> None:
    points = aggregate_price_history([record("2026-08-28T10:05:00+08:00", "45"), record("2026-08-28T12:05:00+08:00", "50")], "hour", product_id="1")
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


def multi_record(product_id: str, timestamp: str, price: float) -> dict[str, object]:
    return {"timestamp": timestamp, "price": price, "cluster_id": product_id,
            "product_id": product_id, "product_type": "resell", "url": "u"}


def test_multi_product_hourly_statistics_never_mix() -> None:
    records = [
        multi_record("A", "2026-08-28T10:05:00+08:00", 40),
        multi_record("A", "2026-08-28T10:30:00+08:00", 44),
        multi_record("B", "2026-08-28T10:10:00+08:00", 100),
        multi_record("B", "2026-08-28T10:40:00+08:00", 120),
    ]
    a = aggregate_price_history(records, "hour", product_id="A")[0]
    b = aggregate_price_history(records, "hour", product_id="B")[0]
    assert a == {"time": "2026-08-28T10:00:00+08:00", "min": 40, "max": 44, "average": 42}
    assert b == {"time": "2026-08-28T10:00:00+08:00", "min": 100, "max": 120, "average": 110}
    assert a["average"] != 76 and b["average"] != 76


def test_deduplication_keeps_same_timestamp_and_price_for_different_products() -> None:
    from src.storage import merge_price_records
    timestamp = "2026-08-28T10:30:00+08:00"
    merged = merge_price_records([
        multi_record("A", timestamp, 50), multi_record("B", timestamp, 50)
    ])
    assert [(item["product_id"], item["price"]) for item in merged] == [("A", 50), ("B", 50)]


def test_multi_product_daily_boundary_is_isolated() -> None:
    records = [
        multi_record("A", "2026-08-28T23:50:00+08:00", 40),
        multi_record("A", "2026-08-29T00:10:00+08:00", 42),
        multi_record("B", "2026-08-28T23:55:00+08:00", 100),
        multi_record("B", "2026-08-29T00:05:00+08:00", 110),
    ]
    assert [p["average"] for p in aggregate_price_history(records, "day", product_id="A")] == [40, 42]
    assert [p["average"] for p in aggregate_price_history(records, "day", product_id="B")] == [100, 110]


def test_saved_multi_product_history_can_be_loaded_again(tmp_path) -> None:
    """持久化不得改变商品身份或把多个商品合并。"""
    from src.storage import load_price_history, save_price_history

    path = tmp_path / "price_history.json"
    original = [
        multi_record("A", "2026-08-28T10:00:00+08:00", 55.5),
        multi_record("B", "2026-08-28T10:00:00+08:00", 99.9),
    ]
    save_price_history(original, path)
    loaded = load_price_history(path)
    assert [(item["product_id"], item["price"]) for item in loaded] == [
        ("A", 55.5), ("B", 99.9)
    ]
