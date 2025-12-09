from __future__ import annotations

import math
from typing import Any

from flask import Blueprint, abort, current_app, render_template, request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from shared.database.models import Article, ArticleAnalysis
from webapp.utils import (
    average,
    collect_topics,
    parse_date,
    sentiment_class,
    sentiment_rollup,
    to_percent,
    to_float,
)

bp = Blueprint("articles", __name__)

SENTIMENT_CHOICES = {"Bullish", "Bearish", "Neutral"}
IMPACT_LEVELS: dict[str, tuple[float, float]] = {
    "high": (0.75, 1.01),
    "medium": (0.5, 0.75),
    "low": (0.0, 0.5),
}


@bp.get("/")
@bp.get("/articles")
async def list_articles():
    """List recent articles with filters, search, and pagination."""
    per_page = int(current_app.config.get("PER_PAGE", 20))
    try:
        page = max(int(request.args.get("page", "1") or "1"), 1)
    except ValueError:
        page = 1

    filters, state = _build_filters()

    async with current_app.config["SESSION_MAKER"]() as session:
        total = await session.scalar(select(func.count()).select_from(Article).where(*filters)) or 0

        stmt = (
            select(Article)
            .options(selectinload(Article.analyses))
            .where(*filters)
            .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        articles = list(await session.scalars(stmt))

        sources_result = await session.execute(
            select(func.distinct(Article.source))
            .where(Article.source.is_not(None))
            .order_by(Article.source)
        )
        sources = [row[0] for row in sources_result if row[0]]

    total_pages = max(math.ceil(total / per_page), 1) if total else 1
    view_models = [_prepare_article_view(article) for article in articles]

    return render_template(
        "articles/list.html",
        articles=view_models,
        page=page,
        total_pages=total_pages,
        total=total,
        filters=state,
        sources=sources,
        per_page=per_page,
    )


@bp.get("/articles/<int:article_id>")
async def article_detail(article_id: int):
    """Show a single article with all LLM analyses."""
    async with current_app.config["SESSION_MAKER"]() as session:
        article = await session.scalar(
            select(Article).options(selectinload(Article.analyses)).where(Article.id == article_id)
        )

    if not article:
        abort(404)

    view_model = _prepare_article_view(article)
    analyses = [_prepare_analysis_view(a) for a in view_model["analyses"]]

    return render_template(
        "articles/detail.html",
        article=article,
        article_view=view_model,
        analyses=analyses,
    )


def _build_filters() -> tuple[list[Any], dict[str, str]]:
    filters: list[Any] = []
    state = {
        "q": (request.args.get("q") or "").strip(),
        "start": (request.args.get("start") or "").strip(),
        "end": (request.args.get("end") or "").strip(),
        "sentiment": (request.args.get("sentiment") or "").strip(),
        "source": (request.args.get("source") or "").strip(),
        "impact": (request.args.get("impact") or "").strip(),
    }

    if state["q"]:
        like = f"%{state['q']}%"
        filters.append(or_(Article.title.ilike(like), Article.scraped_content.ilike(like)))

    if state["sentiment"] in SENTIMENT_CHOICES:
        filters.append(Article.analyses.any(ArticleAnalysis.sentiment == state["sentiment"]))

    impact_range = IMPACT_LEVELS.get(state["impact"])
    if impact_range:
        low, high = impact_range
        filters.append(
            Article.analyses.any(
                and_(ArticleAnalysis.impact_score >= low, ArticleAnalysis.impact_score < high)
            )
        )

    if state["source"]:
        filters.append(Article.source == state["source"])

    start = parse_date(state["start"])
    if start:
        filters.append(Article.published_at >= start)

    end = parse_date(state["end"])
    if end:
        filters.append(Article.published_at <= end)

    return filters, state


def _prepare_article_view(article: Article) -> dict[str, Any]:
    analyses = sorted(article.analyses or [], key=_analysis_sort_key)
    sentiment = sentiment_rollup(analyses)
    avg_sentiment = average(a.sentiment_score for a in analyses)
    avg_impact = average(a.impact_score for a in analyses)

    return {
        "article": article,
        "analyses": analyses,
        "sentiment": sentiment,
        "sentiment_class": sentiment_class(sentiment),
        "avg_sentiment": to_float(avg_sentiment),
        "avg_impact": to_float(avg_impact),
        "impact_percent": to_percent(avg_impact),
        "topics": collect_topics(analyses),
    }


def _prepare_analysis_view(analysis: ArticleAnalysis) -> dict[str, Any]:
    return {
        "provider": (analysis.model_provider or "").capitalize(),
        "model": analysis.model_name,
        "sentiment": analysis.sentiment,
        "sentiment_class": sentiment_class(analysis.sentiment),
        "sentiment_score": to_float(analysis.sentiment_score),
        "impact_score": to_float(analysis.impact_score),
        "confidence": to_float(analysis.confidence),
        "summary": analysis.summary,
        "key_topics": analysis.key_topics or [],
        "analyzed_at": analysis.analyzed_at,
    }


def _analysis_sort_key(analysis: ArticleAnalysis) -> tuple[str, str]:
    provider_order = {"anthropic": 0, "openai": 1, "google": 2}
    provider = (analysis.model_provider or "").lower()
    return provider_order.get(provider, 99), analysis.model_name or ""

