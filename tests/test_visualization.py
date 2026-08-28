from pathlib import Path

from src.visualization import build_chart_data


def record(product_id: str, price: float) -> dict:
    minute = int(price) % 60
    return {"timestamp": f"2026-08-28T10:{minute:02d}:00+08:00", "price": price,
            "cluster_id": product_id, "product_id": product_id,
            "product_type": "resell", "product_name": f"商品 {product_id}", "url": "u"}


def test_chart_products_contain_only_their_own_prices(tmp_path: Path) -> None:
    payload = build_chart_data([record("A", 40), record("A", 44), record("B", 100), record("B", 120)], tmp_path / "missing.yaml")
    a = payload["products"]["resell:A"]["hourly"][0]
    b = payload["products"]["resell:B"]["hourly"][0]
    assert a["max"] == 44 and a["average"] == 42 and a["max"] < 100
    assert b["min"] == 100 and b["average"] == 110
