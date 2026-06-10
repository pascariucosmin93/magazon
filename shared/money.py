from decimal import Decimal, ROUND_HALF_UP
from typing import Any


MONEY_QUANTUM = Decimal("0.01")


def as_money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def money_json(value: Any) -> float:
    return float(as_money(value))


def money_minor_units(value: Any) -> int:
    return int((as_money(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))
