"""Bilibili 市集商品详情请求及最低价格解析。"""

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
    通过市集公开 JSON 接口获取商品最低价格。

    ``clusterId`` 从商品链接中取得，并作为请求参数传给详情接口。本类不
    解析 HTML，也不使用登录状态、Cookie 或反爬绕过手段。
    """

    DETAIL_API = "https://mall.bilibili.com/mall-search-items/items_detail/cluster_info"
    USER_AGENT = "BilibiliPriceMonitor/1.0 (+https://github.com/)"
    REQUEST_TIMEOUT = 15

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

    def get_price(self, cluster_id: str) -> Decimal:
        """请求 ``cluster_info`` 并返回该商品的最低价。"""

        try:
            response = self.session.get(
                self.DETAIL_API,
                params={"clusterId": cluster_id},
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise BilibiliFetchError(f"请求 Bilibili 市集商品详情接口失败：{exc}") from exc
        except ValueError as exc:
            raise BilibiliFetchError("Bilibili 市集商品详情接口没有返回合法 JSON，无法可靠取得价格。") from exc

        if not isinstance(payload, dict):
            raise BilibiliFetchError("Bilibili 市集商品详情接口响应必须是 JSON 对象。")
        if payload.get("code") != 0:
            raise BilibiliFetchError(
                "Bilibili 市集商品详情接口返回错误："
                f"code={payload.get('code')}，message={payload.get('message') or ''}"
            )
        return self._parse_price(payload)

    def fetch(self, url: str) -> ProductInfo:
        """从商品链接提取标识、请求详情并构造监控所需商品资料。"""

        cluster_id = self.extract_cluster_id(url)
        price = self.get_price(cluster_id)
        return ProductInfo(
            cluster_id=cluster_id,
            name="Bilibili 会员购转售商品",
            price=price,
            url=url,
        )

    @staticmethod
    def _parse_price(payload: dict[str, Any]) -> Decimal:
        """从 ``data.clusterPriceFloorVO.priceTag.firstPrice`` 解析最低价。"""

        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliFetchError("Bilibili 市集商品详情响应缺少 data 对象。")
        floor = data.get("clusterPriceFloorVO")
        if not isinstance(floor, dict):
            raise BilibiliFetchError("Bilibili 市集商品详情响应缺少 clusterPriceFloorVO 对象。")
        price_tag = floor.get("priceTag")
        if not isinstance(price_tag, dict):
            raise BilibiliFetchError("Bilibili 市集商品详情响应缺少 priceTag 对象。")
        price = price_tag.get("firstPrice")
        if price is None or (isinstance(price, str) and not price.strip()):
            raise BilibiliFetchError("Bilibili 市集商品详情响应缺少非空 firstPrice 字段。")
        try:
            parsed = Decimal(str(price))
        except (InvalidOperation, ValueError) as exc:
            raise BilibiliFetchError(f"Bilibili 市集商品详情 firstPrice 格式无效：{price!r}") from exc
        if not parsed.is_finite() or parsed < 0:
            raise BilibiliFetchError(f"Bilibili 市集商品详情 firstPrice 不合法：{price!r}")
        return parsed
       
