"""
Initialize the PostgreSQL schema for MarketNews.

Run:
    python scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import logging

from shared.config import Settings, get_settings
from shared.database.session import create_engine_from_settings, init_models

logger = logging.getLogger(__name__)


def configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


async def initialize_database(settings: Settings) -> None:
    engine = create_engine_from_settings(settings)
    logger.info("Initializing database schema...")
    await init_models(engine)
    await engine.dispose()
    logger.info("Database schema created.")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    asyncio.run(initialize_database(settings))


if __name__ == "__main__":
    main()

