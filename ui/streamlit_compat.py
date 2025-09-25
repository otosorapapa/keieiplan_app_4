"""Compatibility helpers for optional Streamlit keyword arguments."""
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict

import streamlit as st

ComponentCallable = Callable[..., Any]

_ACCEPTS_CACHE: Dict[int, bool] = {}


def _unwrap_callable(func: ComponentCallable) -> ComponentCallable:
    """Return the underlying callable for decorated functions."""
    wrapped = getattr(func, "__wrapped__", None)
    while wrapped is not None:
        func = wrapped
        wrapped = getattr(func, "__wrapped__", None)
    return func


def _accepts_use_container_width(func: ComponentCallable) -> bool:
    """Check if a Streamlit API supports the ``use_container_width`` argument."""
    normalized = _unwrap_callable(func)
    cache_key = id(normalized)
    if cache_key in _ACCEPTS_CACHE:
        return _ACCEPTS_CACHE[cache_key]

    try:
        signature = inspect.signature(normalized)
    except (TypeError, ValueError):
        result = False
    else:
        result = "use_container_width" in signature.parameters

    _ACCEPTS_CACHE[cache_key] = result
    return result


def use_container_width_kwargs(
    func: ComponentCallable, *, value: bool = True
) -> Dict[str, bool]:
    """Return kwargs enabling ``use_container_width`` when the component allows it.

    Parameters
    ----------
    func:
        Streamlit callable (e.g. :func:`st.download_button`).
    value:
        Desired value for ``use_container_width`` when supported.

    Returns
    -------
    dict
        ``{"use_container_width": value}`` if the callable accepts the argument,
        otherwise an empty dict.
    """

    if _accepts_use_container_width(func):
        return {"use_container_width": value}
    return {}


def rerun() -> None:
    """Trigger a rerun across supported Streamlit versions."""

    if hasattr(st, "rerun"):
        st.rerun()
    else:  # pragma: no cover - legacy fallback
        st.experimental_rerun()


__all__ = ["use_container_width_kwargs", "rerun"]
