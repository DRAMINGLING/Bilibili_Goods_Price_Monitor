"""Generate a chart whose datasets are isolated by stable product identity."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.storage import HISTORY_FILE, aggregate_price_history, load_price_history

CHART_FILE = Path("docs/index.html")
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
    return {"products": products}


def generate_visualization(history_path: Path = HISTORY_FILE, chart_path: Path = CHART_FILE, data_path: Path = DATA_FILE, config_path: Path = CONFIG_FILE) -> None:
    payload = build_chart_data(load_price_history(history_path), config_path)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chart_path.write_text(_html(), encoding="utf-8")


def _html() -> str:
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Bilibili 商品价格历史</title><script src="https://cdn.jsdelivr.net/npm/chart.js"></script><main><h1 id="title">Bilibili 商品价格历史</h1><p id="identity"></p><label>商品 <select id="product"></select></label> <label>时间单位 <select id="granularity"><option value="hourly">按小时</option><option value="daily">按天</option></select></label> <label>指标 <select id="metric"><option value="max">最高价</option><option value="min">最低价</option><option value="average" selected>均价</option></select></label><canvas id="chart"></canvas></main><script>let data,chart;const labels={max:'最高价',min:'最低价',average:'均价'};async function render(){const p=data.products[product.value],m=metric.value,points=p[granularity.value];title.textContent=p.name+' 价格走势';identity.textContent=`${p.product_type} / Cluster ID: ${p.product_id}`;if(chart)chart.destroy();chart=new Chart(document.getElementById('chart'),{type:'line',data:{labels:points.map(x=>new Date(x.time).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})),datasets:[{label:labels[m]+'（元）',data:points.map(x=>x[m]),borderColor:'#00a1d6',spanGaps:false}]},options:{responsive:true,interaction:{intersect:false},scales:{y:{title:{display:true,text:'价格（元）'}}},plugins:{tooltip:{callbacks:{label:c=>c.parsed.y===null?'无数据':`${labels[m]}：¥${c.parsed.y}`}}}}});}fetch('price_history.json').then(r=>r.json()).then(v=>{data=v;Object.entries(data.products).forEach(([key,p])=>product.add(new Option(`${p.name} (${p.product_id})`,key)));if(product.options.length)render()});product.onchange=render;granularity.onchange=render;metric.onchange=render;</script></html>'''
