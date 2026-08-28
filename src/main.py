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
from src.visualization import generate_visualization


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
    recorded_price = False
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

            print(
                f"当前价格：¥{info.price}"
            )

            # 先保存历史价格。
            storage.add_price(info.cluster_id, info.price, info.url)
            recorded_price = True

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

        except Exception as exc:

            # 一个商品失败不应该导致整个 workflow
            # 无法检查其它商品。
            print(
                f"ERROR: 商品检查失败：{exc}"
            )
            failures.append(f"{product['name']}: {exc}")

    # The page is derived only from raw successful observations.
    if recorded_price:
        generate_visualization()

    if failures:
        # 让 GitHub Actions 明确标红，避免错误被误认为成功的价格检查。
        raise RuntimeError("以下商品无法完成可靠价格检查：" + "；".join(failures))


if __name__ == "__main__":
    main()
