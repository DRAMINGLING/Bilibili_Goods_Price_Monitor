"""Bilibili 市集商品详情请求及最低价格解析。"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
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


_DIAGNOSTIC_RESPONSE_HEADERS = {
    "content-type",
    "date",
    "retry-after",
    "server",
    "via",
    "x-b3-traceid",
    "x-request-id",
    "x-trace-id",
}
_SENSITIVE_BODY_FIELD = re.compile(
    r'(?i)("?(?:cookie|set-cookie|authorization|sessdata|bili_jct|dedeuserid|sid|bili_ticket|token|csrf|session|password|secret)[^:=\"]*"?\s*[:=]\s*)("[^"]*"|[^,}\]&\s]+)'
)


def safe_response_body(response: requests.Response) -> str:
    """返回可写入日志的响应文本摘要，不暴露身份凭证或令牌。"""

    body = response.text[:1000]
    return _SENSITIVE_BODY_FIELD.sub(r"\1[REDACTED]", body)


def safe_response_headers(response: requests.Response) -> dict[str, str]:
    """仅保留允许出现在诊断日志中的非敏感响应头。"""

    return {
        name: value
        for name, value in response.headers.items()
        if name.lower() in _DIAGNOSTIC_RESPONSE_HEADERS
    }


class BilibiliFetcher:
    """
    通过市集公开 JSON 接口获取商品最低价格。

    ``clusterId`` 从商品链接中取得，并作为 JSON 请求体传给详情接口。本类不
    解析 HTML，也不使用登录状态、Cookie 或反爬绕过手段。
    """

    DETAIL_API = "https://mall.bilibili.com/mall-search-items/items_detail/cluster_info"
    REQUEST_TIMEOUT = 15

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

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
            response = self.session.post(
                self.DETAIL_API,
                headers=self._headers(cluster_id),
                json={"clusterId": int(cluster_id)},
                timeout=self.REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise BilibiliFetchError(f"请求 Bilibili 市集商品详情接口失败：{exc}") from exc

        if not response.ok:
            raise BilibiliFetchError(
                "Bilibili 市集商品详情接口 HTTP 请求失败："
                f"status={response.status_code}，"
                f"headers={safe_response_headers(response)!r}，"
                f"body={safe_response_body(response)!r}"
            )

        try:
            payload = response.json()
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

    @staticmethod
    def _headers(cluster_id: str) -> dict[str, str]:
        """构造无需登录凭证的最小浏览器兼容请求头。"""

        return {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://mall.bilibili.com",
            "Referer": (
                "https://mall.bilibili.com/"
                "neul-next/resell/detail.html"
                f"?clusterId={cluster_id}&noTitleBar=1"
            ),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
            ),
        }

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
       
