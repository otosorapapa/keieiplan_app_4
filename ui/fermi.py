"""Utilities for building Fermi-style sales estimates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


FERMI_SEASONAL_PATTERNS: Dict[str, Tuple[float, ...]] = {
    "均等": (1.0,) * 12,
    "繁忙期(Q1)": (1.3, 1.2, 1.1, 1.0, 0.9, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2),
    "繁忙期(Q4)": (0.85, 0.9, 0.95, 1.0, 1.0, 1.05, 1.1, 1.15, 1.2, 1.35, 1.5, 1.65),
    "夏繁忙": (0.8, 0.85, 0.9, 0.95, 1.1, 1.25, 1.35, 1.3, 1.15, 1.0, 0.95, 0.9),
    "冬繁忙": (0.85, 0.9, 0.95, 1.0, 1.05, 1.05, 1.1, 1.2, 1.3, 1.4, 1.3, 1.1),
}


def _normalise_pattern(pattern: Sequence[float]) -> List[float]:
    values = [float(v) for v in pattern]
    total = sum(values)
    if total <= 0:
        return [1.0] * 12
    scale = 12.0 / total
    return [value * scale for value in values]


def _ordered_triple(values: Iterable[float], *, clamp_max: float | None = None) -> Tuple[float, float, float]:
    processed: List[float] = []
    for value in values:
        val = float(value)
        if clamp_max is not None:
            val = min(val, clamp_max)
        processed.append(max(0.0, val))
    if not processed:
        return (0.0, 0.0, 0.0)
    ordered = sorted(processed)
    if len(ordered) == 1:
        ordered = [ordered[0], ordered[0], ordered[0]]
    if len(ordered) == 2:
        ordered.append(ordered[-1])
    return ordered[0], ordered[1], ordered[2]


@dataclass(frozen=True)
class FermiEstimate:
    """Result of a Fermi estimate calculation."""

    pattern_key: str
    monthly: List[float]
    monthly_min: List[float]
    monthly_max: List[float]

    @property
    def annual_typical(self) -> float:
        return float(sum(self.monthly))

    @property
    def annual_min(self) -> float:
        return float(sum(self.monthly_min))

    @property
    def annual_max(self) -> float:
        return float(sum(self.monthly_max))

    def typical_with_ratio(self, ratio: float) -> List[float]:
        adjusted = max(0.0, float(ratio))
        return [value * adjusted for value in self.monthly]


def compute_fermi_estimate(
    *,
    daily_visitors: Tuple[float, float, float],
    unit_price: Tuple[float, float, float],
    business_days: Tuple[float, float, float],
    seasonal_key: str,
) -> FermiEstimate:
    """Return a :class:`FermiEstimate` based on the provided assumptions."""

    pattern = FERMI_SEASONAL_PATTERNS.get(seasonal_key, FERMI_SEASONAL_PATTERNS["均等"])
    weights = _normalise_pattern(pattern)

    min_visitors, typical_visitors, max_visitors = _ordered_triple(daily_visitors)
    min_price, typical_price, max_price = _ordered_triple(unit_price)
    min_days, typical_days, max_days = _ordered_triple(business_days, clamp_max=31.0)

    typical_base = typical_visitors * typical_price * typical_days
    min_base = min_visitors * min_price * min_days
    max_base = max_visitors * max_price * max_days

    monthly_typical = [typical_base * weight for weight in weights]
    monthly_min = [min_base * weight for weight in weights]
    monthly_max = [max_base * weight for weight in weights]

    return FermiEstimate(
        pattern_key=seasonal_key,
        monthly=monthly_typical,
        monthly_min=monthly_min,
        monthly_max=monthly_max,
    )


__all__ = ["FERMI_SEASONAL_PATTERNS", "FermiEstimate", "compute_fermi_estimate"]
