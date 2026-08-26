"""Bilibili 市集详情接口的最低价解析与请求测试。"""

from decimal import Decimal

import pytest
import requests

from src.bilibili import BilibiliFetchError, BilibiliFetcher


def _payload(first_price: object = "55.50") -> dict:
    return {
        "code": 0,
        "data": {
            "clusterPriceFloorVO": {"priceTag": {"firstPrice": first_price}}
        },
    }


class _Response:
    """用于验证公开请求参数的最小响应替身。"""

    def __init__(self, payload: object, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

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
        self.request: tuple[str, dict, int] | None = None

    def get(self, url: str, *, params: dict, timeout: int) -> _Response:
        self.request = (url, params, timeout)
        return self.response


def test_parse_first_price() -> None:
    """最低价从唯一允许的 firstPrice JSON 路径读取。"""
    assert BilibiliFetcher._parse_price(_payload()) == Decimal("55.50")


def test_parse_decimal_price_and_threshold_comparison() -> None:
    """小数价格保持 Decimal 精度，能直接与配置阈值比较。"""
    price = BilibiliFetcher._parse_price(_payload("45.00"))
    assert price == Decimal("45.00")
    assert price <= Decimal("45")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"code": 0, "data": {"clusterPriceFloorVO": {"priceTag": {}}}}, "firstPrice"),
        (_payload(""), "非空 firstPrice"),
        (_payload("not-a-price"), "格式无效"),
        ({"code": 0}, "data 对象"),
        ({"code": 0, "data": {}}, "clusterPriceFloorVO"),
    ],
)
def test_parse_price_rejects_missing_or_invalid_fields(payload: dict, message: str) -> None:
    """缺失或无效的必要字段必须有明确错误，不能猜测价格。"""
    with pytest.raises(BilibiliFetchError, match=message):
        BilibiliFetcher._parse_price(payload)


def test_fetch_uses_cluster_info_api() -> None:
    """获取器必须将链接中的 clusterId 传给新的市集详情接口。"""
    session = _Session(_Response(_payload("45.00")))
    info = BilibiliFetcher(session=session).fetch(
        "https://mall.bilibili.com/neul-next/resell/detail.html?clusterId=10000008690"
    )
    assert session.request == (
        BilibiliFetcher.DETAIL_API,
        {"clusterId": "10000008690"},
        BilibiliFetcher.REQUEST_TIMEOUT,
    )
    assert info.price == Decimal("45.00")


def test_get_price_rejects_api_error() -> None:
    """HTTP 成功但业务 code 非零时不能使用响应中的价格。"""
    session = _Session(_Response({"code": 1001, "message": "商品不存在"}))
    with pytest.raises(BilibiliFetchError, match="code=1001，message=商品不存在"):
        BilibiliFetcher(session=session).get_price("10000008690")


def test_get_price_wraps_http_error() -> None:
    """非 2xx 响应必须转换为清晰的领域异常。"""
    response = _Response({}, requests.HTTPError("404 Client Error"))
    with pytest.raises(BilibiliFetchError, match="请求 Bilibili 市集商品详情接口失败"):
        BilibiliFetcher(session=_Session(response)).get_price("10000008690")


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
