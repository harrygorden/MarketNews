"""
Quick utility to clear all rows from the article_analyses table.
Run before testing to get a clean slate.

Usage:
  python scripts/clear_analyses.py
  python scripts/clear_analyses.py --yes  # Skip confirmation
"""

import argparse
import asyncio

from sqlalchemy import delete, func, select

from shared.config import get_settings
from shared.database.models import ArticleAnalysis
from shared.database.session import create_engine_from_settings, get_session_maker


async def main(skip_confirm: bool = False) -> None:
    settings = get_settings()
    engine = create_engine_from_settings(settings)
    session_maker = get_session_maker(engine)

    async with session_maker() as session:
        # Count before delete
        count = await session.scalar(select(func.count()).select_from(ArticleAnalysis))
        print(f"Found {count} rows in article_analyses table.")

        if count and count > 0:
            if skip_confirm:
                confirm = "y"
            else:
                confirm = input("Delete all rows? [y/N]: ").strip().lower()

            if confirm == "y":
                await session.execute(delete(ArticleAnalysis))
                await session.commit()
                print(f"Deleted {count} rows.")
            else:
                print("Aborted.")
        else:
            print("Table is already empty.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear all article_analyses rows.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    asyncio.run(main(skip_confirm=args.yes))

