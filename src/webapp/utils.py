"""
Shared helpers for the Flask web interface.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from shared.database.models import ArticleAnalysis


def parse_date(value: str | None) -> datetime | None:
    """
    Parse an ISO date string (YYYY-MM-DD) to an aware datetime in UTC.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_float(value: Decimal | float | int | None) -> float | None:
    """Convert Decimal values to floats for template-friendly rendering."""
    if value is None:
        return None
    return float(value)


def average(values: Iterable[Decimal | float | int | None]) -> float | None:
    """Return the arithmetic mean, ignoring None values."""
    numeric = [to_float(v) for v in values if v is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def sentiment_rollup(analyses: Iterable[ArticleAnalysis]) -> str | None:
    """
    Return the dominant sentiment (Bullish/Bearish/Neutral) or 'Mixed' when tied.
    """
    sentiments: dict[str, int] = {}
    for analysis in analyses:
        if not analysis.sentiment:
            continue
        normalized = analysis.sentiment.lower()
        sentiments[normalized] = sentiments.get(normalized, 0) + 1

    if not sentiments:
        return None

    leader, count = max(sentiments.items(), key=lambda item: item[1])
    if list(sentiments.values()).count(count) > 1:
        return "Mixed"
    return leader.capitalize()


def sentiment_class(sentiment: str | None) -> str:
    """Map sentiment text to a CSS class suffix."""
    if not sentiment:
        return "sentiment-neutral"
    mapping = {
        "bullish": "sentiment-bullish",
        "bearish": "sentiment-bearish",
        "neutral": "sentiment-neutral",
        "mixed": "sentiment-mixed",
    }
    return mapping.get(sentiment.lower(), "sentiment-neutral")


def collect_topics(analyses: Iterable[ArticleAnalysis], limit: int = 6) -> list[str]:
    """Combine and deduplicate key topics across analyses."""
    topics: list[str] = []
    seen: set[str] = set()
    for analysis in analyses:
        for topic in analysis.key_topics or []:
            normalized = topic.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            topics.append(topic)
            if len(topics) >= limit:
                return topics
    return topics


def to_percent(value: float | None) -> int | None:
    """Convert a decimal score to a rounded percentage (0-100)."""
    if value is None:
        return None
    return round(value * 100)

