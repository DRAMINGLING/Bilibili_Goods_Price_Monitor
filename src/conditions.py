"""
价格条件判断模块。

目前支持：

    lte
        price <= target

    lt
        price < target

    gte
        price >= target

    gt
        price > target

    range
        min <= price <= max
"""

from decimal import Decimal
from typing import Any


def check_condition(price: Decimal, condition: dict[str, Any]) -> bool:
    """判断当前价格是否满足用户设置的条件。"""

    condition_type = condition["type"]

    if condition_type == "lte":
        target = Decimal(str(condition["price"]))
        return price <= target

    if condition_type == "lt":
        target = Decimal(str(condition["price"]))
        return price < target

    if condition_type == "gte":
        target = Decimal(str(condition["price"]))
        return price >= target

    if condition_type == "gt":
        target = Decimal(str(condition["price"]))
        return price > target

    if condition_type == "range":
        minimum = Decimal(str(condition["min"]))
        maximum = Decimal(str(condition["max"]))

        return minimum <= price <= maximum

    raise ValueError(
        f"Unknown condition type: {condition_type}"
    )
