"""Price-history persistence and UTC+8 aggregation utilities."""

from __future__ import annotations

import calendar
import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Literal, TypedDict
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HISTORY_FILE = DATA_DIR / "price_history.json"
Granularity = Literal["hour", "day"]
Metric = Literal["max", "min", "average"]


class PriceRecord(TypedDict):
    timestamp: str
    price: float
    cluster_id: str
    url: str
    product_id: str
    product_type: str
    product_name: str


class AggregatePoint(TypedDict):
    time: str
    max: float | None
    min: float | None
    average: float | None


def shanghai_now() -> datetime:
    """Return an aware timestamp, independent of the runner's local timezone."""
    return datetime.now(SHANGHAI_TZ)


def _parse_timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError(f"历史记录 timestamp 必须带时区：{value!r}")
    return timestamp.astimezone(SHANGHAI_TZ)


def _normalise_record(record: object) -> PriceRecord | None:
    if not isinstance(record, dict):
        return None
    try:
        timestamp = _parse_timestamp(str(record["timestamp"]))
        price = float(Decimal(str(record["price"])))
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    # Existing JSON already contains the stable Bilibili clusterId.  It can be
    # migrated without guessing; records with neither identity are unsafe and
    # are deliberately ignored rather than attributed to an arbitrary product.
    product_id = str(record.get("product_id") or record.get("cluster_id") or "")
    if not product_id:
        return None
    product_type = str(record.get("product_type") or "resell")
    return {
        "timestamp": timestamp.isoformat(),
        "price": price,
        "cluster_id": str(record.get("cluster_id", "")),
        "url": str(record.get("url", "")),
        "product_id": product_id,
        "product_type": product_type,
        "product_name": str(record.get("product_name", "")),
    }


def _load_legacy_sqlite(path: Path) -> list[PriceRecord]:
    """Best-effort migration for the repository's former SQLite history."""
    if not path.exists():
        return []
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                "SELECT cluster_id, price, checked_at FROM price_history"
            ).fetchall()
    except sqlite3.Error:
        return []
    return [record for cluster_id, price, checked_at in rows if (record := _normalise_record({
        "cluster_id": cluster_id, "price": price, "timestamp": checked_at,
    })) is not None]


def merge_price_records(*groups: Iterable[PriceRecord]) -> list[PriceRecord]:
    """Deduplicate only exact logical records, then order them chronologically."""
    merged: dict[tuple[str, str, str], PriceRecord] = {}
    for group in groups:
        for candidate in group:
            record = _normalise_record(candidate)
            if record is not None:
                key = (record["product_type"], record["product_id"], record["timestamp"])
                merged[key] = record
    return sorted(merged.values(), key=lambda record: (record["product_type"], record["product_id"], record["timestamp"]))


def load_price_history(path: Path = HISTORY_FILE) -> list[PriceRecord]:
    """Load raw observations; migrate the old SQLite file when JSON is absent."""
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = []
        if isinstance(payload, dict):  # tolerate an early wrapper-shaped export
            payload = payload.get("records", [])
        return merge_price_records(payload if isinstance(payload, list) else [])
    return merge_price_records(_load_legacy_sqlite(path.with_name("prices.db")))


def save_price_history(records: Iterable[PriceRecord], path: Path = HISTORY_FILE) -> None:
    """Persist raw observations in deterministic JSON for review and Git merges."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merge_price_records(records), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def subtract_months(timestamp: datetime, months: int) -> datetime:
    """Subtract natural calendar months, clamping month-end dates safely."""
    local = timestamp.astimezone(SHANGHAI_TZ)
    month_index = local.year * 12 + local.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(local.day, calendar.monthrange(year, month)[1])
    return local.replace(year=year, month=month, day=day)


def cleanup_old_history(records: Iterable[PriceRecord], now: datetime | None = None) -> list[PriceRecord]:
    """Keep timestamps in the natural-calendar three-month interval ``[cutoff, now]``."""
    reference = (now or shanghai_now()).astimezone(SHANGHAI_TZ)
    cutoff = subtract_months(reference, 3)
    return merge_price_records(record for record in records if cutoff <= _parse_timestamp(record["timestamp"]) <= reference)


def append_price_record(records: Iterable[PriceRecord], *, cluster_id: str, price: Decimal, url: str, timestamp: datetime | None = None, product_type: str = "resell", product_name: str = "") -> list[PriceRecord]:
    checked_at = (timestamp or shanghai_now()).astimezone(SHANGHAI_TZ)
    return merge_price_records(records, [{"timestamp": checked_at.isoformat(), "price": float(price), "cluster_id": cluster_id, "product_id": cluster_id, "product_type": product_type, "product_name": product_name, "url": url}])


def _bucket_start(timestamp: datetime, granularity: Granularity) -> datetime:
    if granularity == "hour":
        return timestamp.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError("granularity 必须是 'hour' 或 'day'")


def aggregate_price_history(records: Iterable[PriceRecord], granularity: Granularity = "hour", metric: Metric | None = None, include_empty: bool = True, *, product_id: str, product_type: str = "resell") -> list[AggregatePoint] | list[tuple[str, float | None]]:
    """Aggregate one product by UTC+8 buckets, each strictly ``[start, end)``.

    Requiring the product identity makes an accidental cross-product statistic
    impossible at the API boundary.
    """
    buckets: dict[datetime, list[Decimal]] = {}
    for record in merge_price_records(records):
        if record["product_id"] != product_id or record["product_type"] != product_type:
            continue
        bucket = _bucket_start(_parse_timestamp(record["timestamp"]), granularity)
        buckets.setdefault(bucket, []).append(Decimal(str(record["price"])))
    if not buckets:
        return []
    starts = sorted(buckets)
    step_hours = 1 if granularity == "hour" else 24
    points: list[AggregatePoint] = []
    cursor = starts[0]
    last = starts[-1]
    while cursor <= last:
        values = buckets.get(cursor, [])
        points.append({
            "time": cursor.isoformat(),
            "max": float(max(values)) if values else None,
            "min": float(min(values)) if values else None,
            "average": float(sum(values) / len(values)) if values else None,
        })
        from datetime import timedelta
        cursor += timedelta(hours=step_hours)
    if metric is not None:
        if metric not in ("max", "min", "average"):
            raise ValueError("metric 必须是 'max'、'min' 或 'average'")
        return [(point["time"], point[metric]) for point in points]
    return points


class PriceStorage:
    """Compatibility façade retained for callers of the former storage class."""
    def __init__(self) -> None:
        # All callers share one canonical file; never derive another history
        # location from the current working directory or a database path.
        self.history_path = HISTORY_FILE

    def add_price(self, cluster_id: str, price: Decimal, url: str = "", *, product_type: str = "resell", product_name: str = "") -> None:
        records = append_price_record(load_price_history(self.history_path), cluster_id=cluster_id, price=price, url=url, product_type=product_type, product_name=product_name)
        save_price_history(cleanup_old_history(records), self.history_path)

    def latest_price(self, cluster_id: str) -> Decimal | None:
        matches = [record for record in load_price_history(self.history_path) if record["cluster_id"] == cluster_id]
        return Decimal(str(matches[-1]["price"])) if matches else None
