"""Helpers for persisting and refining Fermi estimation assumptions."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, Iterable, Mapping

from models import EstimateRange


def range_profile_from_estimate(range_obj: EstimateRange, divisor: Decimal) -> Dict[str, float]:
    """Return a normalised range profile dictionary for UI editing."""

    if not isinstance(range_obj, EstimateRange):  # pragma: no cover - defensive
        raise TypeError("range_obj must be an EstimateRange instance")
    if divisor is None:
        divisor = Decimal("1")
    divisor = Decimal(str(divisor)) if divisor != 0 else Decimal("1")
    return {
        "min": float(range_obj.minimum / divisor),
        "typical": float(range_obj.typical / divisor),
        "max": float(range_obj.maximum / divisor),
    }


def update_learning_state(
    current_state: Mapping[str, object] | None,
    plan_total: Decimal,
    actual_total: Decimal,
    *,
    now: Callable[[], datetime] | None = None,
) -> Dict[str, object]:
    """Update Fermi learning history based on plan vs. actual totals."""

    try:
        plan_value = Decimal(str(plan_total))
        actual_value = Decimal(str(actual_total))
    except Exception:  # pragma: no cover - defensive
        return {"history": [], "avg_ratio": 1.0}

    if plan_value <= 0 or actual_value <= 0:
        return dict(current_state or {})

    history: list[Dict[str, object]] = []
    if isinstance(current_state, Mapping):
        existing = current_state.get("history", [])
        if isinstance(existing, Iterable):
            for entry in existing:
                if isinstance(entry, Mapping):
                    history.append(dict(entry))

    ratio = float(actual_value / plan_value) if plan_value else 1.0
    timestamp_factory = now or datetime.utcnow
    history.append(
        {
            "plan": float(plan_value),
            "actual": float(actual_value),
            "ratio": ratio,
            "diff": float(actual_value - plan_value),
            "timestamp": timestamp_factory().isoformat(),
        }
    )
    history = history[-12:]

    ratios = [
        float(entry.get("ratio", 0.0))
        for entry in history
        if isinstance(entry, Mapping) and entry.get("ratio")
    ]
    avg_ratio = sum(ratios) / len(ratios) if ratios else 1.0

    return {"history": history, "avg_ratio": avg_ratio}


__all__ = ["range_profile_from_estimate", "update_learning_state"]
