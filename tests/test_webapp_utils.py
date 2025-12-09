from datetime import datetime, timezone
from types import SimpleNamespace

from webapp import utils


def _analysis(sentiment: str | None = None, impact: float | None = None, topics: list[str] | None = None):
    return SimpleNamespace(sentiment=sentiment, impact_score=impact, key_topics=topics or [])


def test_sentiment_rollup_majority_wins():
    analyses = [
        _analysis(sentiment="Bullish"),
        _analysis(sentiment="Bullish"),
        _analysis(sentiment="Bearish"),
    ]
    assert utils.sentiment_rollup(analyses) == "Bullish"


def test_sentiment_rollup_mixed_on_tie():
    analyses = [_analysis(sentiment="Bullish"), _analysis(sentiment="Bearish")]
    assert utils.sentiment_rollup(analyses) == "Mixed"


def test_average_ignores_none():
    assert utils.average([1.0, None, 3.0]) == 2.0


def test_collect_topics_deduplicates():
    analyses = [
        _analysis(topics=["Fed", "Inflation"]),
        _analysis(topics=["inflation", "Jobs"]),
    ]
    assert utils.collect_topics(analyses) == ["Fed", "Inflation", "Jobs"]


def test_parse_date_returns_aware_datetime():
    parsed = utils.parse_date("2025-02-01")
    assert parsed.tzinfo == timezone.utc
    assert parsed.year == 2025

