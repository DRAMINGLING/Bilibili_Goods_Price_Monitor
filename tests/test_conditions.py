from decimal import Decimal

from src.conditions import check_condition


def test_price_below_target():

    assert check_condition(
        Decimal("40"),
        {
            "type": "lte",
            "price": 45,
        },
    )


def test_price_equal_target():

    assert check_condition(
        Decimal("45"),
        {
            "type": "lte",
            "price": 45,
        },
    )


def test_price_above_target():

    assert not check_condition(
        Decimal("46"),
        {
            "type": "lte",
            "price": 45,
        },
    )
