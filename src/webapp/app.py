from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from flask import Flask

from shared.config import get_settings
from shared.database.session import create_engine_from_settings, get_session_maker
from webapp.routes import register_blueprints

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """
    Flask application factory.
    """

    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.url_map.strict_slashes = False

    engine = create_engine_from_settings(settings)
    session_maker = get_session_maker(engine)

    app.config.update(
        ENGINE=engine,
        SESSION_MAKER=session_maker,
        SETTINGS=settings,
        PER_PAGE=20,
    )

    register_blueprints(app)
    _register_template_filters(app)

    return app


def _register_template_filters(app: Flask) -> None:
    @app.template_filter("format_datetime")
    def _format_datetime(value: datetime | None) -> str:
        if not value:
            return "—"
        try:
            return value.astimezone(timezone.utc).strftime("%b %d, %Y %H:%M %Z")
        except Exception:
            return str(value)

    @app.template_filter("format_score")
    def _format_score(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value:.2f}"

    @app.template_filter("percent")
    def _percent(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value * 100:.0f}%"

    @app.context_processor
    def inject_globals() -> dict[str, Any]:
        return {
            "app_name": "Market News",
            "sentiment_classes": {
                "bullish": "sentiment-bullish",
                "bearish": "sentiment-bearish",
                "neutral": "sentiment-neutral",
                "mixed": "sentiment-mixed",
            },
        }

