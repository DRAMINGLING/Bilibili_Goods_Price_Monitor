"""Bilibili 公开转售详情接口的价格解析测试。"""

from decimal import Decimal

import pytest

from src.bilibili import BilibiliFetchError, BilibiliFetcher

class _Response:
    """用于验证公开请求参数的最小响应替身。"""

    def raise_for_status(self) -> None:
        """模拟成功的 HTTP 响应。"""

    def json(self) -> dict:
        """返回代表公开接口的固定数据。"""
        return {"code": 0, "data": {"title": "测试商品", "salePrice": "45.00"}}

class _Session:
    """记录请求而不实际连接网络。"""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.request: tuple[str, dict, int] | None = None

    def get(self, url: str, *, params: dict, timeout: int) -> _Response:
        self.request = (url, params, timeout)
        return _Response()

def test_parse_sale_price() -> None:
    """salePrice 是转售详情响应的优先价格字段。"""
    assert BilibiliFetcher._parse_price({"salePrice": "42.50", "price": "99"}) == Decimal("42.50")


    price = BilibiliFetcher._extract_price(html)

    assert price == Decimal("39.90")

def test_fetch_uses_cluster_id_with_public_detail_request() -> None:
    """获取器必须把页面 clusterId 传给公开详情请求。"""
    session = _Session()
    info = BilibiliFetcher(session=session).fetch(
        "https://mall.bilibili.com/neul-next/resell/detail.html?clusterId=10000008690"
    )
    assert session.request == (BilibiliFetcher.DETAIL_API, {"clusterId": "10000008690"}, 30)
    assert info.name == "测试商品"
    assert info.price == Decimal("45.00")

def test_parse_numeric_price() -> None:
    """接口也可以将价格编码为 JSON 数字。"""
    assert BilibiliFetcher._parse_price({"price": 43.99}) == Decimal("43.99")

def test_missing_price_raises_instead_of_guessing() -> None:
    """没有明确价格字段必须失败，不能从其他数字推断。"""
    with pytest.raises(BilibiliFetchError, match="没有 salePrice/price"):
        BilibiliFetcher._parse_price({"stock": 1, "originalPrice": "59.90"})

def test_extract_cluster_id() -> None:
    """可以从指定的商品链接解析商品簇标识。"""
    assert BilibiliFetcher.extract_cluster_id("https://mall.bilibili.com/neul-next/resell/detail.html?clusterId=10000008690&noTitleBar=1") == "10000008690"
    
