from datetime import datetime, timezone

from shared.schemas.queue_messages import ArticleQueueMessage


def test_article_queue_message_serialization():
    now = datetime.now(timezone.utc)
    msg = ArticleQueueMessage(
        article_id=123,
        news_url="http://example.com/article",
        source="Example",
        published_at=now,
    )

    payload = msg.model_dump_json()
    assert str(123) in payload
    assert "example.com" in payload
    assert now.isoformat()[:19] in payload

