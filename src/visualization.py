"""Generate a chart whose datasets are isolated by stable product identity."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.storage import HISTORY_FILE, aggregate_price_history, load_price_history

DATA_FILE = Path("docs/price_history.json")
CONFIG_FILE = Path("config/products.yaml")


def build_chart_data(records: list[dict], config_path: Path = CONFIG_FILE) -> dict:
    """Build independent hourly/daily datasets for every product."""
    metadata: dict[tuple[str, str], dict[str, str]] = {}
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for product in config.get("products", []):
            product_id = str(product.get("cluster_id", ""))
            if product_id:
                product_type = str(product.get("product_type", "resell"))
                metadata[(product_type, product_id)] = {
                    "name": str(product.get("name", product_id)),
                    "url": str(product.get("url", "")),
                }
    for record in records:
        key = (record["product_type"], record["product_id"])
        current = metadata.setdefault(key, {"name": record.get("product_name") or record["product_id"], "url": record.get("url", "")})
        if record.get("product_name"):
            current["name"] = record["product_name"]
        if record.get("url"):
            current["url"] = record["url"]

    products = {}
    for (product_type, product_id), details in sorted(metadata.items()):
        key = f"{product_type}:{product_id}"
        products[key] = {
            "product_id": product_id,
            "product_type": product_type,
            **details,
            "hourly": aggregate_price_history(records, "hour", product_id=product_id, product_type=product_type),
            "daily": aggregate_price_history(records, "day", product_id=product_id, product_type=product_type),
        }
    updated_at = max((record["timestamp"] for record in records), default=None)
    return {"updated_at": updated_at, "products": products}


def generate_visualization(history_path: Path = HISTORY_FILE, data_path: Path = DATA_FILE, config_path: Path = CONFIG_FILE) -> None:
    """Regenerate the dashboard data; the hand-maintained HTML is not generated."""
    payload = build_chart_data(load_price_history(history_path), config_path)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
