"""
Timer-triggered function: aggregate recent analyses and publish Discord digests.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

try:  # Azure Functions runtime provides this, tests may not have the package installed.
    import azure.functions as func
except ModuleNotFoundError:  # pragma: no cover - fallback stub for local tests
    class _TimerRequest:  # noqa: D401 - lightweight stub, no runtime behavior
        """Stub to satisfy type checks when azure.functions is unavailable."""

    class _FuncStub:
        TimerRequest = _TimerRequest

    func = _FuncStub()  # type: ignore
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from shared.config import get_settings
from shared.database.models import Article, Digest, DigestArticle
from shared.database.session import create_engine_from_settings, get_session_maker
from shared.services.discord import discord_notifier

logger = logging.getLogger(__name__)

# Eastern Time handling for schedule checks
ET = ZoneInfo("America/New_York")

# How long after a scheduled time we still permit sending (to avoid duplicates)
DISPATCH_TOLERANCE = timedelta(minutes=20)

# Target digest windows (local ET clock)
DIGEST_WINDOWS = (
    {"digest_type": "premarket", "hour": 6, "minute": 30, "weekdays": {0, 1, 2, 3, 4}},  # Mon-Fri
    {"digest_type": "lunch", "hour": 12, "minute": 0, "weekdays": {0, 1, 2, 3, 4}},  # Mon-Fri
    {"digest_type": "postmarket", "hour": 16, "minute": 30, "weekdays": {0, 1, 2, 3, 4}},  # Mon-Fri
    {"digest_type": "weekly", "hour": 12, "minute": 0, "weekdays": {5}},  # Saturday
)

# Fallback lookback windows when no prior digest exists
DEFAULT_LOOKBACK = {
    "premarket": timedelta(hours=24),
    "lunch": timedelta(hours=6),
    "postmarket": timedelta(hours=6),
    "weekly": timedelta(days=7),
}


async def main(timer: func.TimerRequest) -> None:  # noqa: ARG001
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    if not discord_notifier.digests_webhook:
        logger.error("DISCORD_WEBHOOK_DIGESTS not configured; skipping digest run.")
        return

    now_utc = datetime.now(timezone.utc)
    pending = determine_pending_digest(now_utc.astimezone(ET))
    if not pending:
        logger.info("No digest window at this invocation; skipping.")
        return

    digest_type, scheduled_et = pending
    scheduled_utc = scheduled_et.astimezone(timezone.utc)
    logger.info("Starting %s digest for window ending %s ET", digest_type, scheduled_et.isoformat())

    engine = create_engine_from_settings(settings)
    session_maker = get_session_maker(engine)

    async with session_maker() as session:
        last_digest = await session.scalar(
            select(Digest)
            .where(Digest.digest_type == digest_type)
            .order_by(Digest.sent_at.desc())
        )

        if last_digest and last_digest.sent_at >= scheduled_utc - DISPATCH_TOLERANCE:
            logger.info(
                "%s digest already recorded at %s; skipping.", digest_type, last_digest.sent_at.isoformat()
            )
            await engine.dispose()
            return

        period_start = calculate_period_start(digest_type, last_digest.sent_at if last_digest else None, now_utc)
        period_end = now_utc

        articles = await fetch_articles(session, period_start, period_end)
        ranked = rank_articles(articles)

        message_id = await discord_notifier.send_digest(
            digest_type=digest_type,
            articles=ranked,
            period_start=period_start,
            period_end=period_end,
        )

        digest_row = Digest(
            digest_type=digest_type,
            sent_at=now_utc,
            article_count=len(ranked),
            discord_message_id=message_id,
        )
        session.add(digest_row)
        await session.flush()  # assign ID for junction rows

        if ranked:
            session.add_all(
                DigestArticle(digest_id=digest_row.id, article_id=item["article_id"], rank=idx + 1)
                for idx, item in enumerate(ranked)
            )

            # Mark included articles (preserve earliest timestamp if already set)
            await session.execute(
                update(Article)
                .where(Article.id.in_([item["article_id"] for item in ranked]), Article.included_in_digest_at.is_(None))
                .values(included_in_digest_at=now_utc)
            )

        await session.commit()

    await engine.dispose()
    logger.info("Completed %s digest with %s articles", digest_type, len(ranked))


def determine_pending_digest(now_et: datetime) -> tuple[str, datetime] | None:
    """
    Return the digest type and scheduled ET datetime if within the dispatch tolerance window.
    """
    for window in DIGEST_WINDOWS:
        if now_et.weekday() not in window["weekdays"]:
            continue

        target = now_et.replace(
            hour=window["hour"],
            minute=window["minute"],
            second=0,
            microsecond=0,
        )
        if target <= now_et <= target + DISPATCH_TOLERANCE:
            return window["digest_type"], target
    return None


def calculate_period_start(digest_type: str, last_sent_at: datetime | None, now_utc: datetime) -> datetime:
    """
    Determine the start of the aggregation period.
    Uses last sent time when available, otherwise a sensible default lookback.
    """
    if last_sent_at:
        return last_sent_at
    return now_utc - DEFAULT_LOOKBACK.get(digest_type, timedelta(hours=24))


async def fetch_articles(session, start: datetime, end: datetime) -> list[Article]:
    """
    Load articles with analyses within the requested window.
    """
    stmt = (
        select(Article)
        .options(selectinload(Article.analyses))
        .join(Article.analyses)
        .where(Article.created_at >= start, Article.created_at <= end)
        .distinct()
    )
    result = await session.scalars(stmt)
    return list(result)


def rank_articles(articles: Iterable[Article]) -> list[dict]:
    """
    Rank articles by (1) consensus, (2) sentiment strength, (3) impact score.
    Returns a list of dictionaries ready for Discord digest payloads.
    """
    ranked: list[dict] = []
    for article in articles:
        analyses = article.analyses or []
        if not analyses:
            continue

        sentiments = [str(a.sentiment or "").lower() for a in analyses if a.sentiment]
        sentiment_counts = Counter(sentiments)
        consensus = len(sentiment_counts) == 1 and len(analyses) >= 3

        avg_sentiment = _average([a.sentiment_score for a in analyses])
        avg_impact = _average([a.impact_score for a in analyses])
        if avg_sentiment is None or avg_impact is None:
            continue

        leader = sentiment_counts.most_common(1)[0][0] if sentiment_counts else "neutral"
        sentiment_strength = abs(avg_sentiment)

        ranked.append(
            {
                "article_id": article.id,
                "title": article.title,
                "source": article.source or "",
                "published_at": article.published_at,
                "news_url": article.news_url,
                "sentiment": leader.capitalize(),
                "avg_sentiment_score": avg_sentiment,
                "avg_impact_score": avg_impact,
                "consensus": consensus,
                "sentiment_strength": sentiment_strength,
            }
        )

    ranked.sort(
        key=lambda item: (
            item["consensus"],
            item["sentiment_strength"],
            item["avg_impact_score"],
            item["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return ranked


def _average(values: Iterable[float | None]) -> float | None:
    """
    Compute a safe average, converting Decimals to float and skipping None values.
    """
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


