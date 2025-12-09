"""
Analyze existing articles to see which would trigger Discord alerts
under the current alert criteria.

Usage:
  python scripts/analyze_alert_eligibility.py [--limit N] [--log-level INFO]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import List, Tuple
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared.config import get_settings
from shared.database.models import Article
from shared.database.session import create_engine_from_settings, get_session_maker
from shared.services.discord import discord_notifier

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate which articles would send Discord alerts.")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit on number of most recent articles to evaluate.")
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")
    return parser.parse_args()


def _is_youtube(url: str | None) -> bool:
    if not url:
        return False
    host = urlparse(url).hostname or ""
    return "youtube.com" in host.lower() or "youtu.be" in host.lower()


def _to_float(val) -> float | None:
    try:
        return float(val)
    except Exception:
        return None


def _prepare_analyses(article) -> Tuple[List[dict], str, float]:
    analyses_dicts: list[dict] = []
    sentiments: list[str] = []
    impacts: list[float] = []

    for analysis in article.analyses:
        sentiment = analysis.sentiment or ""
        impact = _to_float(analysis.impact_score) or 0.0
        sentiments.append(sentiment)
        impacts.append(impact)
        analyses_dicts.append(
            {
                "model_provider": analysis.model_provider,
                "model_name": analysis.model_name,
                "summary": analysis.summary,
                "sentiment": sentiment,
                "sentiment_score": _to_float(analysis.sentiment_score),
                "confidence": _to_float(getattr(analysis, "confidence", None)),
                "impact_score": impact,
                "key_topics": analysis.key_topics or [],
            }
        )

    # Majority sentiment (simple leader); used only for display and as a placeholder arg
    consensus = sentiments[0] if sentiments else "Unknown"
    if sentiments:
        counts = {}
        for s in sentiments:
            counts[s] = counts.get(s, 0) + 1
        consensus = max(counts, key=counts.get)

    avg_impact = sum(impacts) / len(impacts) if impacts else 0.0
    return analyses_dicts, consensus, avg_impact


def _impact_bucket(min_impact: float | None) -> str:
    if min_impact is None:
        return "unknown"
    if min_impact >= 0.9:
        return "90-100"
    if min_impact >= 0.8:
        return "80-89"
    if min_impact >= 0.7:
        return "70-79"
    if min_impact >= 0.6:
        return "60-69"
    if min_impact >= 0.5:
        return "50-59"
    return "<50"


async def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    settings = get_settings()
    engine = create_engine_from_settings(settings)
    session_maker = get_session_maker(engine)

    total = 0
    eligible = 0
    youtube_total = 0
    youtube_eligible = 0
    eligible_articles: list[str] = []
    impact_buckets: dict[str, int] = {
        "90-100": 0,
        "80-89": 0,
        "70-79": 0,
        "60-69": 0,
        "50-59": 0,
        "<50": 0,
        "unknown": 0,
    }

    async with session_maker() as session:
        stmt = (
            select(Article)
            .options(selectinload(Article.analyses))
            .order_by(Article.created_at.desc())
        )
        if args.limit:
            stmt = stmt.limit(args.limit)

        articles = await session.scalars(stmt)

        for article in articles:
            total += 1
            is_yt = _is_youtube(article.news_url)
            if is_yt:
                youtube_total += 1

            analyses_dicts, consensus, avg_impact = _prepare_analyses(article)
            min_impact = min([a.get("impact_score", 0) for a in analyses_dicts], default=None)
            bucket = _impact_bucket(min_impact)
            impact_buckets[bucket] = impact_buckets.get(bucket, 0) + 1

            should_send = discord_notifier.should_send_alert(
                analyses_dicts, consensus, avg_impact
            )

            if should_send:
                eligible += 1
                if is_yt:
                    youtube_eligible += 1
                eligible_articles.append(
                    f"[{article.id}] {article.title} | {article.source} | sentiments={[a.get('sentiment') for a in analyses_dicts]} | minImpact={min([a.get('impact_score',0) for a in analyses_dicts], default=0):.2f}"
                )

    await engine.dispose()

    print("=== Articles that WOULD alert ===")
    if eligible_articles:
        for line in eligible_articles:
            print(line)
    else:
        print("(none)")

    print("\n=== Summary ===")
    print(f"Eligible: {eligible}/{total} articles")
    print(f"YouTube Eligible: {youtube_eligible}/{youtube_total} YouTube articles")
    print("\nImpact score (min per article) buckets:")
    for key in ["90-100", "80-89", "70-79", "60-69", "50-59", "<50", "unknown"]:
        print(f"  {key}: {impact_buckets.get(key, 0)}")


if __name__ == "__main__":
    asyncio.run(main())

