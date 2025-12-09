"""
Purge all articles and their analyses.

Usage:
  python scripts/purge_articles.py --force

Safety:
- Requires --force to actually execute.
- This will TRUNCATE article_analyses and articles (with RESTART IDENTITY, CASCADE).
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy.sql import text

from shared.config import get_settings
from shared.database.session import create_engine_from_settings


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Purge all articles and analyses.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Actually execute the purge. Without this flag, the script will abort.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be purged without executing.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Log level (default: INFO)",
    )
    return parser.parse_args()


async def purge_all(engine) -> None:
    async with engine.begin() as conn:
        logger.info("Truncating article_analyses and articles...")
        await conn.execute(text("TRUNCATE TABLE article_analyses RESTART IDENTITY CASCADE;"))
        await conn.execute(text("TRUNCATE TABLE articles RESTART IDENTITY CASCADE;"))
    logger.info("Purge complete.")


async def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    if args.dry_run:
        logger.info("[DRY-RUN] Would truncate article_analyses and articles (RESTART IDENTITY CASCADE).")
        return

    if not args.force:
        logger.error("Refusing to purge without --force. Aborting.")
        return

    settings = get_settings()
    engine = create_engine_from_settings(settings)

    try:
        await purge_all(engine)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

