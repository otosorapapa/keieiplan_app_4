"""Service layer exports for authentication, persistence and estimations."""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["auth", "database", "security", "fermi_learning", "marketing_strategy"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
