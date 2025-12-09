import pytest
from datetime import datetime, timedelta, timezone

from shared.services.news_api import NewsItem, filter_new_articles, is_paywalled


def test_is_paywalled_detects_paywall_flags():
    samples = [
        (["Market", "PayWall"], True),
        (["paylimitwall"], True),
        (["finance", "economy"], False),
    ]

    for topics, expected in samples:
        result = is_paywalled(topics)
        print(f"topics={topics} => is_paywalled={result}")
        assert result is expected


def test_filter_new_articles_removes_duplicates_and_paywalls():
    items = [
        NewsItem(news_url="http://a.com", title="A", topics=["finance"]),
        NewsItem(news_url="http://b.com", title="B", topics=["paywall"]),
        NewsItem(news_url="http://c.com", title="C", topics=["economy"]),
    ]
    existing = {"http://c.com"}

    filtered = filter_new_articles(items, existing)
    print(
        "input_urls=",
        [i.news_url for i in items],
        "existing_urls=",
        existing,
        "filtered_urls=",
        [i.news_url for i in filtered],
    )

    assert len(filtered) == 1
    assert filtered[0].news_url == "http://a.com"


def test_published_at_parses_rfc2822_date():
    item = NewsItem(
        news_url="http://example.com",
        title="Sample",
        date="Mon, 08 Dec 2025 16:27:10 -0500",
    )

    dt = item.published_at()

    assert dt is not None
    assert dt == datetime(2025, 12, 8, 16, 27, 10, tzinfo=timezone(timedelta(hours=-5)))

