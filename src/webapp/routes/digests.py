from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, render_template
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared.database.models import Article, Digest, DigestArticle
from webapp.utils import average, collect_topics, sentiment_class, sentiment_rollup, to_percent

bp = Blueprint("digests", __name__, url_prefix="/digests")


@bp.get("/")
async def history():
    """Show previously sent digests with their ranked articles."""
    async with current_app.config["SESSION_MAKER"]() as session:
        stmt = (
            select(Digest)
            .options(
                selectinload(Digest.digest_articles)
                .selectinload(DigestArticle.article)
                .selectinload(Article.analyses)
            )
            .order_by(Digest.sent_at.desc())
        )
        digests = list(await session.scalars(stmt))

    prepared = [_prepare_digest_view(digest) for digest in digests]

    return render_template("digests/history.html", digests=prepared)


def _prepare_digest_view(digest: Digest) -> dict[str, Any]:
    articles = []
    for record in sorted(digest.digest_articles or [], key=lambda da: da.rank or 0):
        article = record.article
        if not article:
            continue

        analyses = article.analyses or []
        sentiment = sentiment_rollup(analyses)
        avg_impact = average(a.impact_score for a in analyses)

        articles.append(
            {
                "article": article,
                "rank": record.rank,
                "sentiment": sentiment,
                "sentiment_class": sentiment_class(sentiment),
                "impact_percent": to_percent(avg_impact),
                "avg_impact": avg_impact,
                "topics": collect_topics(analyses, limit=4),
            }
        )

    return {"digest": digest, "articles": articles}

