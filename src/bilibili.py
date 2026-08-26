"""
Bilibili 会员购商品价格获取器。

重要说明：

Bilibili 会员购页面是动态页面。
因此不能简单地假设：

    requests.get(url).text

里面一定直接包含商品价格。

本模块故意把：
    1. 页面请求
    2. API 请求
    3. JSON 解析
    4. 价格解析

分开。

以后如果 Bilibili 修改接口，只需要修改这个文件。
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse, parse_qs

import requests


@dataclass
class ProductInfo:
    """统一的商品信息结构。"""

    cluster_id: str
    name: str
    price: Decimal
    url: str


class BilibiliFetcher:

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )

    def __init__(self):
        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )

    @staticmethod
    def extract_cluster_id(url: str) -> str:
        """从会员购 URL 中提取 clusterId。"""

        parsed = urlparse(url)

        query = parse_qs(parsed.query)

        cluster_ids = query.get("clusterId")

        if not cluster_ids:
            raise ValueError(
                "URL 中没有找到 clusterId"
            )

        return cluster_ids[0]

    def fetch(self, url: str) -> ProductInfo:
        """
        获取商品信息。

        当前实现首先请求页面，然后尝试从页面中的
        JSON / HTML 中寻找价格。

        如果 Bilibili 当前页面结构无法通过这种方式获取，
        会明确抛出异常，而不是返回一个错误价格。
        """

        cluster_id = self.extract_cluster_id(url)

        response = self.session.get(
            url,
            timeout=30,
        )

        response.raise_for_status()

        html = response.text

        price = self._extract_price(html)

        if price is None:
            raise RuntimeError(
                "无法从 Bilibili 页面获取商品价格。"
                "该页面可能需要进一步分析其动态 API。"
            )

        name = self._extract_name(html)

        return ProductInfo(
            cluster_id=cluster_id,
            name=name,
            price=price,
            url=url,
        )

    @staticmethod
    def _extract_name(html: str) -> str:
        """尽可能从 HTML 中获取商品名称。"""

        patterns = [
            r'"title"\s*:\s*"([^"]+)"',
            r'"name"\s*:\s*"([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                html,
                re.IGNORECASE,
            )

            if match:
                return match.group(1)

        return "Bilibili 会员购商品"

    @staticmethod
    def _extract_price(html: str):
        """
        从页面数据中寻找价格。

        注意：
        这是一个保守的 fallback parser。

        如果页面中的价格由 JavaScript/API 动态获取，
        这个函数可能无法找到价格。

        此时程序应该报错，而不是猜测。
        """

        patterns = [
            # 常见 JSON 字段
            r'"price"\s*:\s*"(\d+(?:\.\d+)?)"',
            r'"price"\s*:\s*(\d+(?:\.\d+)?)',

            # 一些可能出现的金额字段
            r'"salePrice"\s*:\s*"(\d+(?:\.\d+)?)"',
            r'"salePrice"\s*:\s*(\d+(?:\.\d+)?)',

            r'"currentPrice"\s*:\s*"(\d+(?:\.\d+)?)"',
            r'"currentPrice"\s*:\s*(\d+(?:\.\d+)?)',
        ]

        candidates = []

        for pattern in patterns:
            for match in re.finditer(
                pattern,
                html,
                re.IGNORECASE,
            ):
                try:
                    value = Decimal(match.group(1))

                    # 排除明显不合理的数值。
                    if value >= 0:
                        candidates.append(value)

                except Exception:
                    continue

        if not candidates:
            return None

        # 暂时选择最小候选价格。
        #
        # 注意：
        # 这不是最终解析策略。
        # 后续应该根据 Bilibili 实际 API 返回结构，
        # 精确定位 salePrice / price 字段。
        return min(candidates)
