"""Bilibili 会员购转售商品的公开详情请求及响应解析。"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests


@dataclass(frozen=True)
class ProductInfo:
    """一次成功查询得到的、可用于监控的商品资料。"""

    cluster_id: str
    name: str
    price: Decimal
    url: str


class BilibiliFetchError(RuntimeError):
    """公开接口不可用或其响应不能可靠地表示价格时抛出。"""

class BilibiliFetcher:
    """
    通过转售详情页使用的公开 JSON 请求获取商品价格。
    分析方式：该页面的 ``clusterId`` 是转售商品簇标识，而不是普通
    ``itemsId``。页面会以它作为 ``clusterId`` 参数调用下面的公开详情接口。
    因此这里不解析易变的 HTML，也不尝试登录、验证码或反爬绕过。
    """

    DETAIL_API = "https://mall.bilibili.com/mall-c-resell/resell/cluster/detail"
    USER_AGENT = "BilibiliPriceMonitor/1.0 (+https://github.com/)"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT, "Accept": "application/json"})

    @staticmethod
    def extract_cluster_id(url: str) -> str:
        """从用户提供的详情链接提取非空 ``clusterId``。"""

        cluster_id = parse_qs(urlparse(url).query).get("clusterId", [""])[0]
        if not cluster_id:
            raise ValueError("商品 URL 中没有有效的 clusterId 参数。")
        return cluster_id

    def fetch(self, url: str) -> ProductInfo:
        """请求公开详情接口；接口拒绝访问时保留其原因并明确失败。"""

        cluster_id = self.extract_cluster_id(url)

        try:
            response = self.session.get(self.DETAIL_API, params={"clusterId": cluster_id}, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise BilibiliFetchError(f"请求 Bilibili 公开转售详情接口失败：{exc}") from exc
        except ValueError as exc:
            raise BilibiliFetchError("Bilibili 公开转售详情接口没有返回 JSON，无法可靠取得价格。") from exc

        if payload.get("code") not in (0, None):
            raise BilibiliFetchError(f"Bilibili 公开接口返回错误：code={payload.get('code')}，message={payload.get('message', '')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliFetchError("Bilibili 公开接口响应缺少 data 对象，无法可靠取得价格。")
        return ProductInfo(cluster_id=cluster_id, name=self._parse_name(data), price=self._parse_price(data), url=url)

    @staticmethod
    def _parse_name(data: dict[str, Any]) -> str:
        """只读取详情响应中明确的商品名称字段。"""

        for key in ("title", "name", "goodsName"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "Bilibili 会员购转售商品"

    @staticmethod
    def _parse_price(data: dict[str, Any]) -> Decimal:
        """解析详情响应的实际转售价；字段缺失或歧义时绝不猜测。"""

        price = data.get("salePrice", data.get("price"))
        if price is None:
            raise BilibiliFetchError("Bilibili 公开接口响应没有 salePrice/price 字段，无法可靠取得价格。")
        try:
            parsed = Decimal(str(price))
        except (InvalidOperation, ValueError) as exc:
            raise BilibiliFetchError(f"Bilibili 公开接口价格格式无效：{price!r}") from exc
        if not parsed.is_finite() or parsed < 0:
            raise BilibiliFetchError(f"Bilibili 公开接口价格不合法：{price!r}")
        return parsed
       
