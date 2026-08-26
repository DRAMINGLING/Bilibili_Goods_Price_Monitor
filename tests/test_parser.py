"""
Bilibili 商品价格解析测试。

这些测试用于确保价格解析器不会因为简单的页面结构变化
而立即失效。

注意：
目前 Bilibili 会员购页面的真实 API 返回结构仍需要进一步确认。
因此这里测试的是 parser 本身，而不是假定某个未经验证的 API。
"""

from decimal import Decimal

from src.bilibili import BilibiliFetcher


def test_extract_price_from_string_json():
    """测试 JSON 中 price 为字符串的情况。"""

    html = """
    <script>
    {
        "price": "42.50"
    }
    </script>
    """

    price = BilibiliFetcher._extract_price(html)

    assert price == Decimal("42.50")


def test_extract_price_from_numeric_json():
    """测试 JSON 中 price 为数字的情况。"""

    html = """
    <script>
    {
        "price": 43.99
    }
    </script>
    """

    price = BilibiliFetcher._extract_price(html)

    assert price == Decimal("43.99")


def test_extract_sale_price():
    """测试 salePrice 字段。"""

    html = """
    <script>
    {
        "salePrice": "39.90"
    }
    </script>
    """

    price = BilibiliFetcher._extract_price(html)

    assert price == Decimal("39.90")


def test_extract_current_price():
    """测试 currentPrice 字段。"""

    html = """
    <script>
    {
        "currentPrice": 44.00
    }
    </script>
    """

    price = BilibiliFetcher._extract_price(html)

    assert price == Decimal("44.00")


def test_extract_multiple_prices_uses_lowest_candidate():
    """
    当前 fallback parser 的行为：

    如果页面中出现多个候选价格，
    暂时选择最小值。

    这只是 fallback 行为。

    一旦确认 Bilibili 官方/公开接口的真实字段，
    应修改 parser，使其精确选择商品实际售价，
    而不是简单取最小值。
    """

    html = """
    <script>
    {
        "originalPrice": "59.90",
        "price": "45.00",
        "salePrice": "42.00"
    }
    </script>
    """

    price = BilibiliFetcher._extract_price(html)

    assert price == Decimal("42.00")


def test_extract_price_returns_none_when_missing():
    """没有价格字段时应该返回 None，而不是猜测价格。"""

    html = """
    <script>
    {
        "name": "某个商品",
        "description": "没有价格信息"
    }
    </script>
    """

    price = BilibiliFetcher._extract_price(html)

    assert price is None


def test_extract_cluster_id():
    """测试从你提供的 URL 中解析 clusterId。"""

    url = (
        "https://mall.bilibili.com/"
        "neul-next/resell/detail.html"
        "?clusterId=10000008690&noTitleBar=1"
    )

    cluster_id = BilibiliFetcher.extract_cluster_id(url)

    assert cluster_id == "10000008690"
