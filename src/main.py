"""
Bilibili 商品价格监控主程序。
"""

import os
from pathlib import Path
from decimal import Decimal

import yaml

from bilibili import BilibiliFetcher
from conditions import check_condition
from notifier import send_price_alert
from storage import PriceStorage


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

    for product in config.get(
        "products",
        [],
    ):

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
            storage.add_price(
                info.cluster_id,
                info.price,
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

        except Exception as exc:

            # 一个商品失败不应该导致整个 workflow
            # 无法检查其它商品。
            print(
                f"ERROR: 商品检查失败：{exc}"
            )


if __name__ == "__main__":
    main()
