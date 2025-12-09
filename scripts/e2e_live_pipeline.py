"""
End-to-end live pipeline test:
 - Fetches news articles from StockNewsAPI (category endpoint)
 - Inserts new articles into the database
 - Scrapes content via Firecrawl
 - Runs configured LLM analyzers (Claude/OpenAI/Gemini), with YouTube => Gemini-only
 - Stores analyses into article_analyses

Requires real credentials and reachable services:
  DATABASE_URL
  STOCKNEWS_API_KEY
  FIRECRAWL_API_KEY
  OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_AI_API_KEY (as available)

Usage (from repo root):
  python scripts/e2e_live_pipeline.py --items 50 --section general --page 1

Warning: This will incur API costs (Firecrawl + LLMs) and write to your DB.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select, update

from shared.config import get_settings
from shared.database.models import Article, ArticleAnalysis
from shared.database.session import create_engine_from_settings, get_session_maker
from shared.services.analyzers import ClaudeAnalyzer, GeminiAnalyzer, OpenAIAnalyzer, run_all_analyzers
from shared.services.discord import discord_notifier
from shared.services.firecrawl import FirecrawlClient
from shared.services.news_api import StockNewsClient, filter_new_articles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live end-to-end fetch/scrape/analyze pipeline.")
    parser.add_argument("--items", type=int, default=50, help="Number of articles to request (default: 50)")
    parser.add_argument("--section", type=str, default="general", help="StockNewsAPI section (default: general)")
    parser.add_argument("--page", type=int, default=1, help="StockNewsAPI page (default: 1)")
    parser.add_argument("--tickers", type=str, default=None, help="Optional tickers filter (e.g., ES,NQ)")
    parser.add_argument(
        "--topicexclude",
        type=str,
        default="paywall,paylimitwall,podcast",
        help="Topics to exclude (comma-separated). Default excludes paywalls/podcasts.",
    )
    parser.add_argument("--log-level", type=str, default="INFO", help="Log level (default: INFO)")
    parser.add_argument(
        "--reprocess-existing",
        action="store_true",
        help="Also process existing duplicate URLs already in the database.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    logger = logging.getLogger("e2e_live_pipeline")

    client = StockNewsClient(settings.STOCKNEWS_API_KEY)

    logger.info("Fetching articles: section=%s items=%s page=%s", args.section, args.items, args.page)
    articles = await client.fetch_latest(
        section=args.section,
        items=args.items,
        page=args.page,
        tickers=args.tickers,
        topicexclude=args.topicexclude,
    )
    if not articles:
        logger.warning("No articles returned.")
        return

    engine = create_engine_from_settings(settings)
    session_maker = get_session_maker(engine)

    async with session_maker() as session:
        urls = [a.news_url for a in articles]
        existing_urls = set()
        if urls:
            result = await session.execute(select(Article.news_url).where(Article.news_url.in_(urls)))
            existing_urls = {row[0] for row in result}

        new_items = filter_new_articles(articles, existing_urls)
        logger.info("Fetched=%s new=%s duplicates=%s", len(articles), len(new_items), len(existing_urls))

        inserted_articles: list[Article] = []
        for item in new_items:
            art = Article(
                news_url=item.news_url,
                title=item.title,
                source=item.source_name,
                published_at=item.published_at(),
                topics=item.topics,
                api_sentiment=item.sentiment,
                raw_api_response=item.model_dump(),
            )
            session.add(art)
            inserted_articles.append(art)

        await session.flush()  # assign IDs

        # Optionally reprocess existing duplicates
        existing_articles: list[Article] = []
        if args.reprocess_existing and existing_urls:
            existing_rows = await session.scalars(
                select(Article).where(Article.news_url.in_(existing_urls))
            )
            existing_articles = list(existing_rows)
            logger.info("Reprocessing %s existing articles.", len(existing_articles))

        for art in [*inserted_articles, *existing_articles]:
            await _process_article(session, art, settings, logger)

        await session.commit()

    await engine.dispose()
    logger.info("Completed pipeline. inserted=%s", len(inserted_articles))


async def _process_article(session, article: Article, settings, logger):
    content: str | None = None
    youtube_link = _is_youtube(article.news_url)

    if youtube_link:
        logger.info("YouTube link; skipping scrape for article %s", article.id)
    elif settings.FIRECRAWL_API_KEY:
        scraper = FirecrawlClient(settings.FIRECRAWL_API_KEY)
        try:
            content = await _retry_async(lambda: scraper.scrape(article.news_url))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scrape failed for article %s: %s", article.id, exc)
            await _mark_scrape_failed(session, article.id)
            await session.commit()
            return
    elif not youtube_link:
        logger.warning("FIRECRAWL_API_KEY not set; skipping scrape for %s", article.id)

    if not content and not youtube_link:
        # Non-YouTube article with no scraped content - mark as failed and skip
        await _mark_scrape_failed(session, article.id, mark_failed=True)
        await session.commit()
        return

    if content:
        article.scraped_content = content
        article.scraped_at = datetime.now(timezone.utc)
        article.scrape_failed = False
        await session.commit()
    elif youtube_link:
        # YouTube: Gemini will watch the video directly
        content = f"[YouTube Video - Gemini will analyze video content]"
        logger.info("YouTube video detected; Gemini will watch video for article %s", article.id)

    analyzers = _build_analyzers(settings, article.news_url, logger)
    if not analyzers:
        logger.warning("No analyzers configured/applicable for article %s; skipping analysis.", article.id)
        return

    try:
        # Pass youtube_url so Gemini can watch the video
        yt_url = article.news_url if youtube_link else None
        results = await _retry_async(
            lambda: run_all_analyzers(
                analyzers=analyzers,
                title=article.title,
                source=article.source,
                published_at=article.published_at,
                content=content,
                youtube_url=yt_url,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis failed for article %s: %s", article.id, exc)
        return

    # Avoid duplicate provider rows
    existing = await session.execute(
        select(ArticleAnalysis.model_provider).where(ArticleAnalysis.article_id == article.id)
    )
    existing_providers = {row[0] for row in existing}

    for provider, model_name, res in results:
        if provider in existing_providers:
            logger.info("Provider %s already exists for article %s, skipping.", provider, article.id)
            continue
        session.add(
            ArticleAnalysis(
                article_id=article.id,
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

    await session.commit()
    logger.info("Processed article %s with %s analyses", article.id, len(results))
    
    # Send Discord notification if criteria met
    await _send_notification_if_needed(article, results, logger)


async def _send_notification_if_needed(article: Article, results: list, logger) -> None:
    """Send Discord notification if article meets alert criteria."""
    if not results:
        return
    
    # Calculate consensus sentiment and averages
    sentiments = [res.sentiment for _, _, res in results]
    sentiment_scores = [res.sentiment_score for _, _, res in results]
    impact_scores = [res.impact_score for _, _, res in results]
    
    # Determine consensus sentiment
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
    # Deduplicate
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
        logger.info(f"✅ Sent Discord notification for article {article.id}")
    except Exception as e:
        logger.error(f"❌ Failed to send notification for article {article.id}: {e}", exc_info=True)


async def _mark_scrape_failed(session, article_id: int, mark_failed: bool = True) -> None:
    await session.execute(
        update(Article)
        .where(Article.id == article_id)
        .values(scrape_failed=mark_failed, scraped_at=datetime.now(timezone.utc))
    )


def _build_analyzers(settings, news_url: str | None, logger) -> list:
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


if __name__ == "__main__":
    asyncio.run(main())

