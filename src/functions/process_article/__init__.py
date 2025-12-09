"""
Queue-triggered function: scrape article content and run multi-LLM analysis.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

import azure.functions as func
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from shared.config import get_settings
from shared.database.models import Article, ArticleAnalysis
from shared.database.session import create_engine_from_settings, get_session_maker
from shared.schemas.analysis import AnalysisResult
from shared.schemas.queue_messages import ArticleQueueMessage
from shared.services.analyzers import (
    ClaudeAnalyzer,
    GeminiAnalyzer,
    OpenAIAnalyzer,
    run_all_analyzers,
)
from shared.services.discord import discord_notifier
from shared.services.firecrawl import FirecrawlClient

logger = logging.getLogger(__name__)


async def main(msg: func.QueueMessage) -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    try:
        data = json.loads(msg.get_body().decode("utf-8"))
        qmsg = ArticleQueueMessage(**data)
    except Exception as exc:
        logger.exception("Invalid queue message: %s", exc)
        return

    engine = create_engine_from_settings(settings)
    session_maker = get_session_maker(engine)

    async with session_maker() as session:
        article = await session.scalar(
            select(Article).options(selectinload(Article.analyses)).where(Article.id == qmsg.article_id)
        )
        if not article:
            logger.warning("Article %s not found; skipping.", qmsg.article_id)
            await engine.dispose()
            return

        # Scrape content (skip Firecrawl for YouTube links)
        content: str | None = None
        youtube_link = _is_youtube(article.news_url)

        if youtube_link:
            logger.info("YouTube link; skipping scrape for article %s", article.id)
        elif settings.FIRECRAWL_API_KEY:
            scraper = FirecrawlClient(settings.FIRECRAWL_API_KEY)
            try:
                content = await _retry_async(lambda: scraper.scrape(article.news_url))
            except Exception as exc:
                logger.exception("Scrape failed for article %s: %s", article.id, exc)
                await _mark_scrape_failed(session, article.id)
        else:
            logger.warning("FIRECRAWL_API_KEY not set; skipping scrape.")

        if content:
            article.scraped_content = content
            article.scraped_at = datetime.now(timezone.utc)
            article.scrape_failed = False
            await session.commit()
        elif youtube_link:
            # YouTube: Gemini can analyze the video directly; no scrape content required
            content = "[YouTube Video - Gemini will analyze video content]"
            article.scraped_at = datetime.now(timezone.utc)
            article.scrape_failed = False
            await session.commit()
        else:
            # No content and not YouTube: mark failed and stop.
            article.scraped_at = datetime.now(timezone.utc)
            article.scrape_failed = True
            await session.commit()
            await engine.dispose()
            return

        analyzers = _build_analyzers(settings, article.news_url)

        if not analyzers:
            logger.warning("No LLM API keys configured (or none applicable); skipping analysis.")
            await engine.dispose()
            return

        try:
            results = await _retry_async(
                lambda: run_all_analyzers(
                    analyzers=analyzers,
                    title=article.title,
                    source=article.source,
                    published_at=article.published_at,
                    content=content,
                    youtube_url=article.news_url if youtube_link else None,
                )
            )
        except Exception as exc:
            logger.exception("Analysis failed for article %s: %s", article.id, exc)
            await engine.dispose()
            return

        await _persist_results(session, article.id, results)
        
        # Send Discord notification if criteria met
        await _send_notification_if_needed(article, results)

    await engine.dispose()
    logger.info("Processed article %s", qmsg.article_id)


async def _mark_scrape_failed(session, article_id: int) -> None:
    await session.execute(
        update(Article)
        .where(Article.id == article_id)
        .values(scrape_failed=True, scraped_at=datetime.now(timezone.utc))
    )


async def _persist_results(session, article_id: int, results: list[tuple[str, str, AnalysisResult]]) -> None:
    for provider, model_name, res in results:
        session.add(
            ArticleAnalysis(
                article_id=article_id,
                model_provider=provider,
                model_name=model_name,
                summary=res.summary,
                sentiment=res.sentiment,
                sentiment_score=res.sentiment_score,
                confidence=res.confidence,
                impact_score=res.impact_score,
                key_topics=res.key_topics,
                raw_response=res.model_dump(),
            )
        )
    try:
        await session.commit()
    except SQLAlchemyError:
        logger.exception("Failed to persist analysis for article %s", article_id)
        await session.rollback()


async def _send_notification_if_needed(article: Article, results: list[tuple[str, str, AnalysisResult]]) -> None:
    """
    Send Discord notification if article meets alert criteria.
    
    Criteria:
    - All LLMs agree on sentiment (consensus)
    - Average impact score >= threshold
    """
    if not results:
        return
    
    # Calculate consensus sentiment and averages
    sentiments = [res.sentiment for _, _, res in results]
    sentiment_scores = [res.sentiment_score for _, _, res in results]
    impact_scores = [res.impact_score for _, _, res in results]
    
    # Determine consensus sentiment (most common, or first if tie)
    sentiment_counts = {}
    for s in sentiments:
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1
    consensus_sentiment = max(sentiment_counts, key=sentiment_counts.get)
    
    avg_sentiment_score = sum(sentiment_scores) / len(sentiment_scores)
    avg_impact_score = sum(impact_scores) / len(impact_scores)
    
    # Prepare analyses for notification
    analyses_dicts = [
        {
            "model_provider": provider,
            "model_name": model_name,
            "summary": res.summary,
            "sentiment": res.sentiment,
            "sentiment_score": res.sentiment_score,
                "confidence": res.confidence,
            "impact_score": res.impact_score,
        }
        for provider, model_name, res in results
    ]
    
    # Check if should send alert
    if not discord_notifier.should_send_alert(analyses_dicts, consensus_sentiment, avg_impact_score):
        logger.info(
            f"Article {article.id} does not meet alert criteria: "
            f"sentiment={consensus_sentiment}, impact={avg_impact_score:.2f}"
        )
        return
    
    # Combine all key topics
    all_topics = []
    for _, _, res in results:
        if res.key_topics:
            all_topics.extend(res.key_topics)
    # Deduplicate while preserving order
    unique_topics = []
    seen = set()
    for topic in all_topics:
        if topic.lower() not in seen:
            seen.add(topic.lower())
            unique_topics.append(topic)
    
    # Send notification
    try:
        await discord_notifier.send_article_alert(
            article_id=article.id,
            title=article.title,
            source=article.source,
            published_at=article.published_at,
            news_url=article.news_url,
            sentiment=consensus_sentiment,
            avg_sentiment_score=avg_sentiment_score,
            avg_impact_score=avg_impact_score,
            analyses=analyses_dicts,
            key_topics=unique_topics,
        )
    except Exception as e:
        logger.error(f"Failed to send notification for article {article.id}: {e}", exc_info=True)


def _build_analyzers(settings, news_url: str | None):
    analyzers = []
    youtube_only = _is_youtube(news_url)

    if settings.GOOGLE_AI_API_KEY:
        analyzers.append(GeminiAnalyzer(settings.GOOGLE_AI_API_KEY))

    if not youtube_only:
        if settings.ANTHROPIC_API_KEY:
            analyzers.append(ClaudeAnalyzer(settings.ANTHROPIC_API_KEY))
        if settings.OPENAI_API_KEY:
            analyzers.append(OpenAIAnalyzer(settings.OPENAI_API_KEY))
    else:
        if not settings.GOOGLE_AI_API_KEY:
            logger.warning("YouTube link requires Gemini; GOOGLE_AI_API_KEY not configured.")
            return []

    return analyzers


def _is_youtube(url: str | None) -> bool:
    if not url:
        return False
    host = urlparse(url).hostname or ""
    return "youtube.com" in host.lower() or "youtu.be" in host.lower()


async def _retry_async(fn, attempts: int = 3, base_delay: float = 0.5):
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == attempts:
                break
            await asyncio.sleep(base_delay * attempt)
    if last_exc:
        raise last_exc

