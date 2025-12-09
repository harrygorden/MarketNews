"""
Azure Timer Function: poll StockNewsAPI, filter paywalled items, deduplicate by URL, and store.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import azure.functions as func
from sqlalchemy import select
from sqlalchemy.engine.url import make_url

from shared.config import get_settings
from shared.database.models import Article
from shared.database.session import create_engine_from_settings, get_session_maker
from shared.schemas.queue_messages import ArticleQueueMessage
from shared.services.news_api import StockNewsClient, filter_new_articles, is_paywalled
from shared.services.queue import QueueService

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def _should_run_now(now_utc: datetime) -> bool:
    """
    Weekdays: run every invocation (configured for 5 min).
    Weekends: only run at the top of the hour to reduce calls.
    """

    now_et = now_utc.astimezone(ET)
    if now_et.weekday() >= 5:  # Saturday/Sunday
        return now_et.minute == 0
    return True


async def main(timer: func.TimerRequest) -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    if not settings.STOCKNEWS_API_KEY:
        logger.error("STOCKNEWS_API_KEY not configured; skipping poll.")
        return

    if not _should_run_now(datetime.now(timezone.utc)):
        logger.info("Weekend invocation outside top-of-hour; skipping poll.")
        return

    engine = create_engine_from_settings(settings)
    safe_url = make_url(settings.DATABASE_URL).render_as_string(hide_password=True)
    logger.info("Polling StockNewsAPI and writing to database: %s", safe_url)

    client = StockNewsClient(settings.STOCKNEWS_API_KEY)
    session_maker = get_session_maker(engine)

    try:
        articles = await client.fetch_latest(items=50, section="general", page=1)
    except Exception as exc:  # http errors or validation issues
        logger.exception("Failed to fetch StockNewsAPI articles: %s", exc)
        await engine.dispose()
        return

    urls = [item.news_url for item in articles]
    new_articles_count = 0

    async with session_maker() as session:
        if urls:
            result = await session.execute(select(Article.news_url).where(Article.news_url.in_(urls)))
            existing_urls = {row[0] for row in result}
        else:
            existing_urls = set()

        filtered = filter_new_articles(articles, existing_urls)
        skipped_paywall = sum(1 for item in articles if is_paywalled(item.topics))
        skipped_duplicates = sum(
            1 for item in articles if not is_paywalled(item.topics) and item.news_url in existing_urls
        )

        if not filtered:
            logger.info(
                "No new articles to insert. fetched=%s paywalled=%s duplicates=%s",
                len(articles),
                skipped_paywall,
                skipped_duplicates,
            )
            await engine.dispose()
            return

        to_insert: list[Article] = []
        for item in filtered:
            to_insert.append(
                Article(
                    news_url=item.news_url,
                    title=item.title,
                    source=item.source_name,
                    published_at=item.published_at(),
                    topics=item.topics,
                    api_sentiment=item.sentiment,
                    raw_api_response=item.model_dump(),
                )
            )

        session.add_all(to_insert)
        await session.commit()
        new_articles_count = len(to_insert)

        if settings.AZURE_STORAGE_CONNECTION_STRING:
            queue = QueueService(
                connection_string=settings.AZURE_STORAGE_CONNECTION_STRING,
                queue_name=settings.QUEUE_NAME,
            )
            for article in to_insert:
                try:
                    await queue.send_article_message(
                        ArticleQueueMessage(
                            article_id=article.id,
                            news_url=article.news_url,
                            source=article.source,
                            published_at=article.published_at,
                        )
                    )
                except Exception as exc:
                    logger.exception("Failed to enqueue article %s: %s", article.id, exc)
        else:
            logger.warning("AZURE_STORAGE_CONNECTION_STRING not set; skipping queue enqueue.")

    await engine.dispose()
    logger.info(
        "Poll complete. fetched=%s inserted=%s paywalled=%s duplicates=%s",
        len(articles),
        new_articles_count,
        skipped_paywall,
        skipped_duplicates,
    )

