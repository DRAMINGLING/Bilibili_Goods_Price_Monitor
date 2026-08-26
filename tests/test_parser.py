"""Bilibili 市集详情接口的最低价解析与请求测试。"""

from decimal import Decimal

import pytest
import requests

from src.bilibili import (
    BilibiliFetchError,
    BilibiliFetcher,
    safe_response_body,
    safe_response_headers,
)


def _payload(first_price: object = "55.50") -> dict:
    return {
        "code": 0,
        "data": {
            "clusterPriceFloorVO": {"priceTag": {"firstPrice": first_price}}
        },
    }


class _Response:
    """用于验证公开请求参数的最小响应替身。"""

    def __init__(
        self,
        payload: object,
        error: Exception | None = None,
        *,
        status_code: int = 200,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.error = error
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class _Session:
    """记录请求而不实际连接网络。"""

    def __init__(self, response: _Response) -> None:
        self.headers: dict[str, str] = {}
        self.response = response
        self.request: tuple[str, dict, dict, int] | None = None

    def post(self, url: str, *, headers: dict, json: dict, timeout: int) -> _Response:
        self.request = (url, headers, json, timeout)
        return self.response


def test_parse_first_price() -> None:
    """最低价从唯一允许的 firstPrice JSON 路径读取。"""
    assert BilibiliFetcher._parse_price(_payload()) == Decimal("55.50")


def test_parse_decimal_price_and_threshold_comparison() -> None:
    """小数价格保持 Decimal 精度，能直接与配置阈值比较。"""
    price = BilibiliFetcher._parse_price(_payload("45.00"))
    assert price == Decimal("45.00")
    assert price <= Decimal("45")


def test_parse_price_below_threshold() -> None:
    """低于阈值的价格应保留精确的小数值。"""
    assert BilibiliFetcher._parse_price(_payload("44.99")) == Decimal("44.99")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"code": 0, "data": {"clusterPriceFloorVO": {"priceTag": {}}}}, "firstPrice"),
        (_payload(""), "非空 firstPrice"),
        (_payload("not-a-price"), "格式无效"),
        ({"code": 0}, "data 对象"),
        ({"code": 0, "data": {}}, "clusterPriceFloorVO"),
        ({"code": 0, "data": {"clusterPriceFloorVO": {}}}, "priceTag"),
    ],
)
def test_parse_price_rejects_missing_or_invalid_fields(payload: dict, message: str) -> None:
    """缺失或无效的必要字段必须有明确错误，不能猜测价格。"""
    with pytest.raises(BilibiliFetchError, match=message):
        BilibiliFetcher._parse_price(payload)


def test_fetch_posts_cluster_id_to_cluster_info_api() -> None:
    """获取器必须 POST 整数 clusterId JSON 请求体到新详情接口。"""
    session = _Session(_Response(_payload("45.00")))
    info = BilibiliFetcher(session=session).fetch(
        "https://mall.bilibili.com/neul-next/resell/detail.html?clusterId=10000008690"
    )
    assert session.request == (
        BilibiliFetcher.DETAIL_API,
        {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://mall.bilibili.com",
            "Referer": (
                "https://mall.bilibili.com/"
                "neul-next/resell/detail.html?clusterId=10000008690&noTitleBar=1"
            ),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0"
            ),
        },
        {"clusterId": 10000008690},
        BilibiliFetcher.REQUEST_TIMEOUT,
    )
    assert info.price == Decimal("45.00")


def test_get_price_rejects_api_error() -> None:
    """HTTP 成功但业务 code 非零时不能使用响应中的价格。"""
    session = _Session(_Response({"code": 1001, "message": "商品不存在"}))
    with pytest.raises(BilibiliFetchError, match="code=1001，message=商品不存在"):
        BilibiliFetcher(session=session).get_price("10000008690")


def test_get_price_wraps_http_error() -> None:
    """非 2xx 响应必须输出过滤后的诊断信息。"""
    response = _Response(
        {},
        status_code=412,
        text='{"message":"risk", "SESSDATA":"private"}',
        headers={"Server": "nginx", "Set-Cookie": "private", "X-Request-ID": "abc"},
    )
    with pytest.raises(
        BilibiliFetchError,
        match="status=412.*Server.*X-Request-ID.*REDACTED",
    ):
        BilibiliFetcher(session=_Session(response)).get_price("10000008690")


def test_response_diagnostics_exclude_sensitive_headers_and_body_values() -> None:
    """诊断信息只能包含允许的响应头，并且必须掩码敏感字段。"""
    response = _Response(
        {},
        text='Authorization=Bearer-secret&token=abc&message=risk',
        headers={"Content-Type": "application/json", "Cookie": "secret", "Set-Cookie": "secret"},
    )
    assert safe_response_headers(response) == {"Content-Type": "application/json"}
    assert safe_response_body(response) == (
        "Authorization=[REDACTED]&token=[REDACTED]&message=risk"
    )


def test_get_price_rejects_invalid_json() -> None:
    """无法解码 JSON 的响应必须明确失败。"""
    response = _Response(ValueError("invalid JSON"))
    with pytest.raises(BilibiliFetchError, match="没有返回合法 JSON"):
        BilibiliFetcher(session=_Session(response)).get_price("10000008690")


def test_extract_cluster_id() -> None:
    """可以从指定的商品链接解析商品簇标识。"""
    assert BilibiliFetcher.extract_cluster_id(
        "https://mall.bilibili.com/neul-next/resell/detail.html?clusterId=10000008690&noTitleBar=1"
    ) == "10000008690"
