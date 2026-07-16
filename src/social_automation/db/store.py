"""Facade DB — delega a sqlite (dev) o postgres (Vercel)."""

from __future__ import annotations

from typing import Any

from social_automation.db.factory import get_database, get_store_module

_MODULE = None


def _active():
    global _MODULE
    if _MODULE is None:
        _MODULE = get_store_module()
    return _MODULE


def reset_backend() -> None:
    global _MODULE
    _MODULE = None


def __getattr__(name: str) -> Any:
    return getattr(_active(), name)


__all__ = [
    "get_database",
    "reset_backend",
]
