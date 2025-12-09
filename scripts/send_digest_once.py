"""
Manually build and send a digest to Discord based on the most recent window.

Usage examples (from repo root):
  python scripts/send_digest_once.py --dry-run
  python scripts/send_digest_once.py --digest-type postmarket
  python scripts/send_digest_once.py --webhook https://discord.com/api/webhooks/...
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from shared.config import get_settings
from shared.database.models import Article, Digest, DigestArticle
from shared.database.session import create_engine_from_settings, get_session_maker
from shared.services.discord import DiscordNotifier
from functions.send_digest import (
    DEFAULT_LOOKBACK,
    DIGEST_WINDOWS,
    calculate_period_start,
    fetch_articles,
    rank_articles,
)

ET = ZoneInfo("America/New_York")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and send a digest on demand.")
    parser.add_argument(
        "--digest-type",
        choices=["premarket", "lunch", "postmarket", "weekly"],
        help="Optional digest type to force; otherwise inferred from the latest window.",
    )
    parser.add_argument(
        "--now",
        type=str,
        help="Override current time (ISO 8601, interpreted as UTC if timezone not provided).",
    )
    parser.add_argument(
        "--webhook",
        type=str,
        help="Override Discord webhook for this run (defaults to DISCORD_WEBHOOK_DIGESTS).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print digest payload counts without sending to Discord.",
    )
    return parser.parse_args()


def coerce_now(now_arg: str | None) -> datetime:
    if not now_arg:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(now_arg)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def previous_window(now_et: datetime, windows: Iterable[dict]) -> tuple[str, datetime]:
    """
    Find the most recent digest window at or before now (search back up to 7 days).
    Returns digest_type and the scheduled ET datetime.
    """
    candidates: list[tuple[datetime, str]] = []
    for offset in range(0, 8):
        day = now_et - timedelta(days=offset)
        for window in windows:
            if day.weekday() not in window["weekdays"]:
                continue
            candidate = day.replace(
                hour=window["hour"], minute=window["minute"], second=0, microsecond=0
            )
            if candidate <= now_et:
                candidates.append((candidate, window["digest_type"]))
    if not candidates:
        raise RuntimeError("No digest window found in the past 7 days.")
    candidate_dt, digest_type = max(candidates, key=lambda x: x[0])
    return digest_type, candidate_dt


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    logger = logging.getLogger("send_digest_once")

    now_utc = coerce_now(args.now)
    now_et = now_utc.astimezone(ET)

    windows = [w for w in DIGEST_WINDOWS if not args.digest_type or w["digest_type"] == args.digest_type]
    if not windows:
        raise SystemExit(f"Unknown digest type: {args.digest_type}")

    digest_type, scheduled_et = previous_window(now_et, windows)
    scheduled_utc = scheduled_et.astimezone(timezone.utc)
    logger.info("Preparing %s digest for window ending %s ET", digest_type, scheduled_et.isoformat())

    webhook = args.webhook or settings.DISCORD_WEBHOOK_DIGESTS
    if not webhook and not args.dry_run:
        raise SystemExit("DISCORD_WEBHOOK_DIGESTS not set and no --webhook provided; cannot send digest.")

    engine = create_engine_from_settings(settings)
    session_maker = get_session_maker(engine)

    async with session_maker() as session:
        last_digest = await session.scalar(
            select(Digest)
            .where(Digest.digest_type == digest_type)
            .order_by(Digest.sent_at.desc())
        )

        period_start = calculate_period_start(
            digest_type, last_digest.sent_at if last_digest else None, now_utc
        )
        period_end = now_utc

        articles = await fetch_articles(session, period_start, period_end)
        ranked = rank_articles(articles)

        logger.info(
            "Found %s articles in window (%s to %s), ranked=%s",
            len(articles),
            period_start.isoformat(),
            period_end.isoformat(),
            len(ranked),
        )

        if args.dry_run:
            for idx, item in enumerate(ranked[:5], 1):
                logger.info(
                    "%s. %s | %s | impact=%.2f sentiment=%s (%.2f) consensus=%s",
                    idx,
                    item["title"][:80],
                    item["source"],
                    item["avg_impact_score"],
                    item["sentiment"],
                    item["avg_sentiment_score"],
                    item["consensus"],
                )
            await engine.dispose()
            return

        notifier = DiscordNotifier(digests_webhook=webhook)
        message_id = await notifier.send_digest(
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
        await session.flush()

        if ranked:
            session.add_all(
                DigestArticle(digest_id=digest_row.id, article_id=item["article_id"], rank=idx + 1)
                for idx, item in enumerate(ranked)
            )
            await session.execute(
                update(Article)
                .where(Article.id.in_([item["article_id"] for item in ranked]), Article.included_in_digest_at.is_(None))
                .values(included_in_digest_at=now_utc)
            )

        await session.commit()
        logger.info(
            "Sent %s digest (message_id=%s) with %s articles",
            digest_type,
            message_id,
            len(ranked),
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

