"""
Bilibili 商品价格监控主程序。
"""

import os
from pathlib import Path
from decimal import Decimal

import yaml

from src.bilibili import BilibiliFetcher
from src.conditions import check_condition
from src.notifier import send_price_alert
from src.storage import PriceStorage


CONFIG_FILE = Path(
    "config/products.yaml"
)


def load_config():
    """读取 YAML 配置。"""

    with CONFIG_FILE.open(
        "r",
        encoding="utf-8",
    ) as f:
        return yaml.safe_load(f)


def main():

    config = load_config()

    storage = PriceStorage()

    fetcher = BilibiliFetcher()

    email_config = config.get(
        "email",
        {},
    )

    email_to = email_config.get(
        "to",
        "",
    )

    # SMTP 密码只从环境变量读取。
    smtp_password = os.environ.get(
        "SMTP_PASSWORD",
        "",
    )

    failures = []
    checked_products = 0
    for product in config.get(
        "products",
        [],
    ):

        # 已下架的商品链接会使会员购接口返回 404。跳过明确禁用的
        # 配置项，避免把一个已知无法查询的商品误报为本次检查失败。
        # 未设置时仍默认启用，以免静默停止已有监控项。
        if not product.get("enabled", True):
            print("=" * 60)
            print(f"跳过已禁用商品：{product['name']}")
            continue

        print("=" * 60)

        print(
            f"检查商品：{product['name']}"
        )

        url = product["url"]

        try:
            info = fetcher.fetch(url)
        except Exception as exc:
            # 单个商品无法读取时跳过该商品并继续检查其余商品。
            # 不会为读取失败的商品写入虚构的价格。
            print(f"WARNING: 商品价格读取失败：{exc}")
            failures.append(
                f"{product['name']}: {exc}".replace("\r", " ").replace("\n", " ")
            )
            continue

        checked_products += 1

        print(
            f"当前价格：¥{info.price}"
        )

        # 先保存历史价格。
        storage.add_price(
            info.cluster_id,
            info.price,
            info.url,
            product_type=product.get("product_type", "resell"),
            product_name=product["name"],
        )

        condition = product[
            "condition"
        ]

        matched = check_condition(
            info.price,
            condition,
        )

        if not matched:

            print(
                "价格条件未满足，不发送提醒。"
            )

            continue

        print(
            "价格条件满足！"
        )

        # 当前例子的 condition 是：
        #
        # price <= 45
        #
        # 因此取目标价格 45。
        target_price = Decimal(
            str(condition["price"])
        )

        # 邮箱为空时，函数内部会直接跳过。
        send_price_alert(
            to_email=email_to,
            smtp_host=email_config.get(
                "smtp_host",
                "",
            ),
            smtp_port=int(
                email_config.get(
                    "smtp_port",
                    465,
                )
            ),
            smtp_user=email_config.get(
                "smtp_user",
                "",
            ),
            smtp_password=smtp_password,
            product_name=info.name,
            price=info.price,
            target_price=target_price,
            product_url=info.url,
        )

    if failures:
        print(
            f"::warning::价格检查部分完成：{checked_products} 个商品读取成功，"
            f"{len(failures)} 个商品读取失败。详情见本次运行摘要。"
        )

        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with Path(summary_path).open("a", encoding="utf-8") as summary:
                summary.write("## 价格检查部分完成\n\n")
                summary.write(
                    f"- 成功读取：{checked_products} 个启用商品\n"
                    f"- 读取失败：{len(failures)} 个启用商品\n\n"
                )
                summary.write(
                    "读取失败的商品未写入新价格；其他商品照常处理：\n\n"
                )
                summary.write("\n".join(f"- {failure}" for failure in failures))
                summary.write("\n")

        if checked_products == 0:
            raise RuntimeError("没有任何启用商品成功读取价格。")


if __name__ == "__main__":
    main()
