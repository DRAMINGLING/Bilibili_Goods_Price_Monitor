"""Generate the dependency-free interactive price-history page."""

from __future__ import annotations

import json
from pathlib import Path

from src.storage import HISTORY_FILE, aggregate_price_history, load_price_history

CHART_FILE = Path("docs/index.html")
DATA_FILE = Path("docs/price_history.json")


def generate_visualization(history_path: Path = HISTORY_FILE, chart_path: Path = CHART_FILE, data_path: Path = DATA_FILE) -> None:
    records = load_price_history(history_path)
    payload = {"hour": aggregate_price_history(records, "hour"), "day": aggregate_price_history(records, "day")}
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    chart_path.write_text(_html(), encoding="utf-8")


def _html() -> str:
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Bilibili 商品价格历史</title><script src="https://cdn.jsdelivr.net/npm/chart.js"></script><main><h1>Bilibili 商品价格历史</h1><label>时间单位 <select id="granularity"><option value="hour">按小时</option><option value="day">按天</option></select></label> <label>指标 <select id="metric"><option value="max">最高价</option><option value="min">最低价</option><option value="average" selected>均价</option></select></label><canvas id="chart"></canvas></main><script>let data,chart;const labels={max:'最高价',min:'最低价',average:'均价'};async function render(){const g=granularity.value,m=metric.value,points=data[g];if(chart)chart.destroy();chart=new Chart(document.getElementById('chart'),{type:'line',data:{labels:points.map(p=>new Date(p.time).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})),datasets:[{label:labels[m]+'（元）',data:points.map(p=>p[m]),borderColor:'#00a1d6',spanGaps:false}]},options:{responsive:true,interaction:{intersect:false},scales:{y:{title:{display:true,text:'价格（元）'}}},plugins:{tooltip:{callbacks:{label:c=>c.parsed.y===null?'无数据':`${labels[m]}：¥${c.parsed.y}`}}}}});}fetch('price_history.json').then(r=>r.json()).then(v=>{data=v;render()});granularity.onchange=render;metric.onchange=render;</script></html>'''
