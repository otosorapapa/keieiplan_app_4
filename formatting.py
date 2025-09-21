"""Helper utilities for formatting numeric outputs."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

UNIT_FACTORS: Mapping[str, Decimal] = {
    "百万円": Decimal("1000000"),
    "千円": Decimal("1000"),
    "円": Decimal("1"),
}


def to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def format_money(value: object, unit: str = "円") -> str:
    try:
        amount = to_decimal(value)
    except Exception:
        return "—"
    factor = UNIT_FACTORS.get(unit, Decimal("1"))
    if factor == 0:
        factor = Decimal("1")
    scaled = amount / factor
    if scaled.is_nan() or scaled.is_infinite():
        return "—"
    quant = Decimal("1") if abs(scaled) >= 1 else Decimal("0.01")
    scaled = scaled.quantize(quant, rounding=ROUND_HALF_UP)
    if quant == Decimal("1"):
        return f"¥{scaled:,.0f}"
    return f"¥{scaled:,.2f}"


def format_amount_with_unit(value: object, unit: str) -> str:
    formatted = format_money(value, unit)
    return formatted if formatted == "—" else f"{formatted} {unit}"


def format_ratio(value: object) -> str:
    try:
        ratio = to_decimal(value)
    except Exception:
        return "—"
    if ratio.is_nan() or ratio.is_infinite():
        return "—"
    return f"{ratio * Decimal('100'):.1f}%"


def format_delta(value: object, unit: str) -> str:
    try:
        amount = to_decimal(value)
    except Exception:
        return "±0"
    if amount == 0 or amount.is_nan() or amount.is_infinite():
        return "±0"
    sign = "+" if amount > 0 else "-"
    return f"{sign}{format_amount_with_unit(abs(amount), unit)}"


def format_ratio_delta(value: object) -> str:
    try:
        amount = to_decimal(value)
    except Exception:
        return "±0"
    if amount == 0 or amount.is_nan() or amount.is_infinite():
        return "±0"
    return f"{amount * Decimal('100'):+.1f}pt"


__all__ = [
    "UNIT_FACTORS",
    "format_money",
    "format_amount_with_unit",
    "format_ratio",
    "format_delta",
    "format_ratio_delta",
    "to_decimal",
]
