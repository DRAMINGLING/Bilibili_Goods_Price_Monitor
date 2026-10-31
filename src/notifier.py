"""
邮件通知模块。

如果 config/products.yaml 中：

    email.to: ""

则不会发送任何邮件。

SMTP 密码永远不要写入 YAML。
应该使用 GitHub Secrets。
"""

import os
import smtplib
from email.message import EmailMessage
from decimal import Decimal


def send_price_alert(
    *,
    to_email: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    product_name: str,
    price: Decimal,
    target_price: Decimal | None,
    product_url: str,
    previous_price: Decimal | None = None,
):
    """发送价格提醒邮件。"""

    # 邮箱为空时直接退出。
    if not to_email:
        print(
            "INFO: 未设置提醒邮箱，"
            "价格条件即使满足，也不会发送邮件。"
        )
        return

    message = EmailMessage()

    is_price_change = previous_price is not None
    message["Subject"] = (
        f"[Bilibili价格变动] {product_name}"
        if is_price_change
        else f"[Bilibili价格提醒] {product_name}"
    )

    if is_price_change:
        direction = "上涨" if price > previous_price else "下降"
        alert_details = (
            f"上次价格：¥{previous_price}\n"
            f"当前价格：¥{price}\n"
            f"价格变化：{direction}"
        )
        alert_reason = "该星标商品价格发生变化。"
    else:
        alert_details = f"当前价格：¥{price}\n目标价格：≤ ¥{target_price}"
        alert_reason = "当前价格已经达到你设置的提醒条件。"

    message["From"] = smtp_user
    message["To"] = to_email

    message.set_content(
        f"""
Bilibili 商品价格通知

商品：
{product_name}

{alert_details}

商品链接：
{product_url}

{alert_reason}

请以 Bilibili 页面最终结算价格为准。
""".strip()
    )

    with smtplib.SMTP_SSL(
        smtp_host,
        smtp_port,
        timeout=30,
    ) as server:

        server.login(
            smtp_user,
            smtp_password,
        )

        server.send_message(message)


def load_smtp_password() -> str:
    """
    从环境变量读取 SMTP 密码。

    GitHub Actions 中通过 Secrets 注入。
    """

    return os.environ.get(
        "SMTP_PASSWORD",
        "",
    )
