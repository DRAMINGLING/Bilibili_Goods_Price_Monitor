"""主程序的商品启用状态测试。"""

from src import main


def test_disabled_product_is_skipped(monkeypatch, capsys) -> None:
    """禁用项不应发起请求，也不能导致本次工作流失败。"""

    class _Storage:
        pass

    class _Fetcher:
        def fetch(self, url: str) -> None:
            raise AssertionError(f"禁用商品不应被请求：{url}")

    monkeypatch.setattr(main, "load_config", lambda: {"products": [{
        "name": "已下架商品",
        "url": "https://example.invalid/?clusterId=1",
        "enabled": False,
    }]})
    monkeypatch.setattr(main, "PriceStorage", _Storage)
    monkeypatch.setattr(main, "BilibiliFetcher", _Fetcher)

    main.main()

    assert "跳过已禁用商品：已下架商品" in capsys.readouterr().out
