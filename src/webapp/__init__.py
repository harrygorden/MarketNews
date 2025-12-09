"""
Flask web interface for MarketNews.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - hints only
    from flask import Flask


def create_app() -> "Flask":
    """
    Lazy import wrapper to avoid pulling Flask unless needed.
    """

    from .app import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]

