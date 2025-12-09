"""
Initialize the PostgreSQL schema for MarketNews.

Run:
    python scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from shared.config import Settings, get_settings
from sqlalchemy.engine.url import make_url
from sqlalchemy.sql import text

from shared.database.models import Base
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
    safe_url = make_url(settings.DATABASE_URL).render_as_string(hide_password=True)
    logger.info("Connecting to database: %s", safe_url)

    logger.info("Initializing database schema...")
    await init_models(engine)
    await _ensure_confidence_column(engine)

    await _log_tables(engine)
    await engine.dispose()
    logger.info("Database schema created.")


async def _log_tables(engine) -> None:
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
        )
        tables = [row[0] for row in result]
        if not tables:
            logger.warning("No tables found in schema.")
            return

        logger.info("Tables created: %s", ", ".join(tables))

    for table in Base.metadata.sorted_tables:
        logger.info("Schema for table '%s': %s", table.name, _format_columns(table.columns))


def _format_columns(columns: Iterable) -> str:
    parts: list[str] = []
    for col in columns:
        col_type = getattr(col.type, "compile", lambda dialect=None: str(col.type))()
        nullable = "NULL" if col.nullable else "NOT NULL"
        default = f" DEFAULT {col.default.arg}" if col.default is not None else ""
        parts.append(f"{col.name} {col_type} {nullable}{default}")
    return "; ".join(parts)


async def _ensure_confidence_column(engine) -> None:
    """
    Add the confidence column and range constraint to article_analyses if missing.
    This is a lightweight migration helper to avoid manual ALTERs when deploying.
    """
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'article_analyses'
                  AND column_name = 'confidence'
                """
            )
        )
        has_column = result.first() is not None

        if not has_column:
            logger.info("Adding column 'confidence' to article_analyses...")
            await conn.execute(text("ALTER TABLE article_analyses ADD COLUMN IF NOT EXISTS confidence numeric(4,3);"))

        # Ensure the range check exists (Postgres lacks IF NOT EXISTS for check constraints pre-v16)
        # We guard by checking pg_constraint to avoid errors if already present.
        result = await conn.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_analysis_confidence_range'
                """
            )
        )
        has_constraint = result.first() is not None
        if not has_constraint:
            logger.info("Adding constraint ck_analysis_confidence_range to article_analyses...")
            await conn.execute(
                text(
                    """
                    ALTER TABLE article_analyses
                    ADD CONSTRAINT ck_analysis_confidence_range
                    CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0));
                    """
                )
            )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    asyncio.run(initialize_database(settings))


if __name__ == "__main__":
    main()

