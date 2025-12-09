from datetime import datetime, timezone
from types import SimpleNamespace

from functions.send_digest import ET, determine_pending_digest, rank_articles


class DummyAnalysis:
    def __init__(self, sentiment: str, sentiment_score: float, impact_score: float):
        self.sentiment = sentiment
        self.sentiment_score = sentiment_score
        self.impact_score = impact_score


def _article(article_id: int, analyses: list[DummyAnalysis], published_at: datetime):
    return SimpleNamespace(
        id=article_id,
        title=f"Article {article_id}",
        source="TestSource",
        published_at=published_at,
        news_url=f"http://example.com/{article_id}",
        analyses=analyses,
    )


def test_determine_pending_digest_within_window():
    now_et = datetime(2024, 1, 2, 6, 35, tzinfo=ET)  # Tuesday
    result = determine_pending_digest(now_et)
    assert result is not None
    digest_type, scheduled = result
    assert digest_type == "premarket"
    assert scheduled.hour == 6 and scheduled.minute == 30


def test_determine_pending_digest_outside_window():
    now_et = datetime(2024, 1, 2, 7, 5, tzinfo=ET)  # Outside tolerance
    assert determine_pending_digest(now_et) is None


def test_rank_articles_prioritizes_consensus():
    published = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)

    consensus_article = _article(
        1,
        [
            DummyAnalysis("Bearish", -0.6, 0.8),
            DummyAnalysis("Bearish", -0.65, 0.9),
            DummyAnalysis("Bearish", -0.7, 0.85),
        ],
        published,
    )

    mixed_article = _article(
        2,
        [
            DummyAnalysis("Bullish", 0.9, 0.9),
            DummyAnalysis("Neutral", 0.1, 0.95),
        ],
        published,
    )

    ranked = rank_articles([mixed_article, consensus_article])
    assert ranked[0]["article_id"] == consensus_article.id  # consensus first
    assert ranked[1]["article_id"] == mixed_article.id

