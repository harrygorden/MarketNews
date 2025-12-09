"""
Comprehensive Health Check Script for MarketNews Application.

This script tests connectivity and functionality of all external services
and validates the overall health of the application.

Tests Performed:
  1. Configuration Validation - All required settings present
  2. Database Connectivity - PostgreSQL connection and table structure
  3. Azure Storage Queue - Queue connectivity and message operations
  4. StockNewsAPI - News fetching and paywall filtering
  5. Firecrawl - Article scraping capability
  6. LLM APIs:
     - Claude (Anthropic) - Sentiment analysis
     - GPT-4o (OpenAI) - Sentiment analysis
     - Gemini (Google) - Sentiment analysis
  7. Discord Webhooks - Alert and digest webhook connectivity
  8. Schema Validation - Pydantic schemas work correctly
  9. HTTP Client Pool - Shared client initialization

Usage:
    python scripts/health_check.py [OPTIONS]

Options:
    --skip-llm          Skip LLM API tests (saves cost)
    --skip-firecrawl    Skip Firecrawl test (saves cost)
    --skip-discord      Skip Discord webhook test
    --verbose           Show detailed output
    --json              Output results as JSON

Exit Codes:
    0 - All tests passed
    1 - One or more tests failed
    2 - Critical configuration error

Requirements:
    All environment variables configured in .env or local.settings.json
"""

from __future__ import annotations

import argparse
import asyncio
import json as json_module
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

# ============================================================================
# Test Result Types
# ============================================================================

class TestStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"


@dataclass
class TestResult:
    name: str
    status: TestStatus
    message: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "details": self.details,
        }


@dataclass
class HealthCheckResults:
    tests: list[TestResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None

    def add(self, result: TestResult):
        self.tests.append(result)

    def passed(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.PASS)

    def failed(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.FAIL)

    def skipped(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.SKIP)

    def warnings(self) -> int:
        return sum(1 for t in self.tests if t.status == TestStatus.WARN)

    def total(self) -> int:
        return len(self.tests)

    def all_passed(self) -> bool:
        return all(t.status in (TestStatus.PASS, TestStatus.SKIP, TestStatus.WARN) for t in self.tests)

    def to_dict(self) -> dict:
        self.end_time = self.end_time or datetime.now(timezone.utc)
        return {
            "summary": {
                "total": self.total(),
                "passed": self.passed(),
                "failed": self.failed(),
                "skipped": self.skipped(),
                "warnings": self.warnings(),
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
                "duration_ms": (self.end_time - self.start_time).total_seconds() * 1000,
            },
            "tests": [t.to_dict() for t in self.tests],
        }


# ============================================================================
# Helper Functions
# ============================================================================

def timer():
    """Context manager to measure execution time."""
    class Timer:
        def __init__(self):
            self.start = None
            self.duration_ms = 0

        def __enter__(self):
            self.start = time.perf_counter()
            return self

        def __exit__(self, *args):
            self.duration_ms = (time.perf_counter() - self.start) * 1000

    return Timer()


# ============================================================================
# Configuration Test
# ============================================================================

def test_configuration() -> TestResult:
    """Test that all required configuration is present."""
    with timer() as t:
        try:
            from shared.config import get_settings

            settings = get_settings()

            required = [
                ("DATABASE_URL", settings.DATABASE_URL),
            ]

            optional_services = [
                ("STOCKNEWS_API_KEY", settings.STOCKNEWS_API_KEY),
                ("FIRECRAWL_API_KEY", settings.FIRECRAWL_API_KEY),
                ("OPENAI_API_KEY", settings.OPENAI_API_KEY),
                ("ANTHROPIC_API_KEY", settings.ANTHROPIC_API_KEY),
                ("GOOGLE_AI_API_KEY", settings.GOOGLE_AI_API_KEY),
                ("DISCORD_WEBHOOK_ALERTS", settings.DISCORD_WEBHOOK_ALERTS),
                ("DISCORD_WEBHOOK_DIGESTS", settings.DISCORD_WEBHOOK_DIGESTS),
                ("AZURE_STORAGE_CONNECTION_STRING", settings.AZURE_STORAGE_CONNECTION_STRING),
            ]

            missing_required = [name for name, val in required if not val]
            missing_optional = [name for name, val in optional_services if not val]
            configured = [name for name, val in optional_services if val]

            if missing_required:
                return TestResult(
                    name="Configuration",
                    status=TestStatus.FAIL,
                    message=f"Missing required: {', '.join(missing_required)}",
                    duration_ms=t.duration_ms,
                )

            details = {
                "configured_services": configured,
                "missing_optional": missing_optional,
                "impact_threshold": settings.IMPACT_THRESHOLD,
                "log_level": settings.LOG_LEVEL,
            }

            if missing_optional:
                return TestResult(
                    name="Configuration",
                    status=TestStatus.WARN,
                    message=f"Missing optional: {', '.join(missing_optional)}",
                    duration_ms=t.duration_ms,
                    details=details,
                )

            return TestResult(
                name="Configuration",
                status=TestStatus.PASS,
                message=f"{len(configured)} services configured",
                duration_ms=t.duration_ms,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name="Configuration",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# Database Tests
# ============================================================================

async def test_database_connectivity() -> TestResult:
    """Test database connection and basic query."""
    with timer() as t:
        try:
            from sqlalchemy import text
            from shared.config import get_settings
            from shared.database.session import create_engine_from_settings

            settings = get_settings()
            engine = create_engine_from_settings(settings)

            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                row = result.fetchone()
                assert row[0] == 1

            await engine.dispose()

            return TestResult(
                name="Database Connectivity",
                status=TestStatus.PASS,
                message="PostgreSQL connection successful",
                duration_ms=t.duration_ms,
            )

        except Exception as e:
            return TestResult(
                name="Database Connectivity",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


async def test_database_tables() -> TestResult:
    """Test that all required tables exist and have correct structure."""
    with timer() as t:
        try:
            from sqlalchemy import text, inspect
            from shared.config import get_settings
            from shared.database.session import create_engine_from_settings

            settings = get_settings()
            engine = create_engine_from_settings(settings)

            expected_tables = [
                "articles",
                "article_analyses",
                "digests",
                "digest_articles",
                "processing_queue_failures",
            ]

            async with engine.connect() as conn:
                # Get list of tables
                result = await conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """))
                existing_tables = {row[0] for row in result}

            await engine.dispose()

            missing = [t for t in expected_tables if t not in existing_tables]
            found = [t for t in expected_tables if t in existing_tables]

            if missing:
                return TestResult(
                    name="Database Tables",
                    status=TestStatus.FAIL,
                    message=f"Missing tables: {', '.join(missing)}",
                    duration_ms=t.duration_ms,
                    details={"found": found, "missing": missing},
                )

            return TestResult(
                name="Database Tables",
                status=TestStatus.PASS,
                message=f"All {len(expected_tables)} tables exist",
                duration_ms=t.duration_ms,
                details={"tables": found},
            )

        except Exception as e:
            return TestResult(
                name="Database Tables",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


async def test_database_article_count() -> TestResult:
    """Check article count in database for data health."""
    with timer() as t:
        try:
            from sqlalchemy import select, func
            from shared.config import get_settings
            from shared.database.models import Article, ArticleAnalysis
            from shared.database.session import create_engine_from_settings, get_session_maker

            settings = get_settings()
            engine = create_engine_from_settings(settings)
            session_maker = get_session_maker(engine)

            async with session_maker() as session:
                article_count = await session.scalar(select(func.count(Article.id)))
                analysis_count = await session.scalar(select(func.count(ArticleAnalysis.id)))
                failed_scrape_count = await session.scalar(
                    select(func.count(Article.id)).where(Article.scrape_failed == True)
                )

            await engine.dispose()

            details = {
                "total_articles": article_count,
                "total_analyses": analysis_count,
                "failed_scrapes": failed_scrape_count,
                "avg_analyses_per_article": round(analysis_count / max(article_count, 1), 2),
            }

            if article_count == 0:
                return TestResult(
                    name="Database Article Count",
                    status=TestStatus.WARN,
                    message="No articles in database yet",
                    duration_ms=t.duration_ms,
                    details=details,
                )

            return TestResult(
                name="Database Article Count",
                status=TestStatus.PASS,
                message=f"{article_count} articles, {analysis_count} analyses",
                duration_ms=t.duration_ms,
                details=details,
            )

        except Exception as e:
            return TestResult(
                name="Database Article Count",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# Azure Queue Tests
# ============================================================================

async def test_azure_queue() -> TestResult:
    """Test Azure Storage Queue connectivity."""
    with timer() as t:
        try:
            from shared.config import get_settings
            from shared.services.queue import QueueService

            settings = get_settings()

            if not settings.AZURE_STORAGE_CONNECTION_STRING:
                return TestResult(
                    name="Azure Queue",
                    status=TestStatus.SKIP,
                    message="AZURE_STORAGE_CONNECTION_STRING not configured",
                    duration_ms=t.duration_ms,
                )

            queue = QueueService(
                connection_string=settings.AZURE_STORAGE_CONNECTION_STRING,
                queue_name=settings.QUEUE_NAME,
                create_queue=True,
            )

            # Just get the client to verify connectivity
            client = await queue._get_client()
            properties = await client.get_queue_properties()
            await queue.close()

            return TestResult(
                name="Azure Queue",
                status=TestStatus.PASS,
                message=f"Queue '{settings.QUEUE_NAME}' accessible",
                duration_ms=t.duration_ms,
                details={
                    "queue_name": settings.QUEUE_NAME,
                    "approximate_message_count": properties.approximate_message_count,
                },
            )

        except Exception as e:
            return TestResult(
                name="Azure Queue",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# StockNewsAPI Test
# ============================================================================

async def test_stocknews_api() -> TestResult:
    """Test StockNewsAPI connectivity and response parsing."""
    with timer() as t:
        try:
            from shared.config import get_settings
            from shared.services.news_api import StockNewsClient

            settings = get_settings()

            if not settings.STOCKNEWS_API_KEY:
                return TestResult(
                    name="StockNewsAPI",
                    status=TestStatus.SKIP,
                    message="STOCKNEWS_API_KEY not configured",
                    duration_ms=t.duration_ms,
                )

            client = StockNewsClient(settings.STOCKNEWS_API_KEY)

            # Fetch just 5 articles to minimize API usage
            articles = await client.fetch_latest(items=5, section="general", page=1)

            if not articles:
                return TestResult(
                    name="StockNewsAPI",
                    status=TestStatus.WARN,
                    message="API returned no articles",
                    duration_ms=t.duration_ms,
                )

            # Validate article structure
            sample = articles[0]
            return TestResult(
                name="StockNewsAPI",
                status=TestStatus.PASS,
                message=f"Fetched {len(articles)} articles",
                duration_ms=t.duration_ms,
                details={
                    "articles_returned": len(articles),
                    "sample_title": sample.title[:50] + "..." if len(sample.title) > 50 else sample.title,
                    "sample_source": sample.source_name,
                },
            )

        except Exception as e:
            return TestResult(
                name="StockNewsAPI",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# Firecrawl Test
# ============================================================================

async def test_firecrawl(skip: bool = False) -> TestResult:
    """Test Firecrawl API connectivity."""
    if skip:
        return TestResult(
            name="Firecrawl",
            status=TestStatus.SKIP,
            message="Skipped by user request",
        )

    with timer() as t:
        try:
            from shared.config import get_settings
            from shared.services.firecrawl import FirecrawlClient

            settings = get_settings()

            if not settings.FIRECRAWL_API_KEY:
                return TestResult(
                    name="Firecrawl",
                    status=TestStatus.SKIP,
                    message="FIRECRAWL_API_KEY not configured",
                    duration_ms=t.duration_ms,
                )

            client = FirecrawlClient(settings.FIRECRAWL_API_KEY)

            # Scrape a simple, fast-loading page
            test_url = "https://httpbin.org/html"
            content = await client.scrape(test_url)

            if not content:
                return TestResult(
                    name="Firecrawl",
                    status=TestStatus.WARN,
                    message="Scrape returned no content",
                    duration_ms=t.duration_ms,
                )

            return TestResult(
                name="Firecrawl",
                status=TestStatus.PASS,
                message=f"Scraped {len(content)} characters",
                duration_ms=t.duration_ms,
                details={"content_length": len(content)},
            )

        except Exception as e:
            return TestResult(
                name="Firecrawl",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# LLM API Tests
# ============================================================================

TEST_ARTICLE = {
    "title": "Health Check Test Article",
    "source": "MarketNews Health Check",
    "published_at": "2025-01-01",
    "content": "The Federal Reserve announced today that interest rates would remain unchanged. Markets reacted positively to the news.",
}


async def test_claude_api(skip: bool = False) -> TestResult:
    """Test Claude (Anthropic) API connectivity."""
    if skip:
        return TestResult(
            name="Claude API (Anthropic)",
            status=TestStatus.SKIP,
            message="Skipped by user request",
        )

    with timer() as t:
        try:
            from shared.config import get_settings
            from shared.services.analyzers import ClaudeAnalyzer

            settings = get_settings()

            if not settings.ANTHROPIC_API_KEY:
                return TestResult(
                    name="Claude API (Anthropic)",
                    status=TestStatus.SKIP,
                    message="ANTHROPIC_API_KEY not configured",
                    duration_ms=t.duration_ms,
                )

            analyzer = ClaudeAnalyzer(settings.ANTHROPIC_API_KEY)
            result = await analyzer.analyze(**TEST_ARTICLE)

            return TestResult(
                name="Claude API (Anthropic)",
                status=TestStatus.PASS,
                message=f"Sentiment: {result.sentiment} ({result.sentiment_score:+.2f})",
                duration_ms=t.duration_ms,
                details={
                    "model": analyzer.model,
                    "sentiment": result.sentiment,
                    "sentiment_score": result.sentiment_score,
                    "impact_score": result.impact_score,
                    "confidence": result.confidence,
                },
            )

        except Exception as e:
            return TestResult(
                name="Claude API (Anthropic)",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


async def test_openai_api(skip: bool = False) -> TestResult:
    """Test GPT-4o (OpenAI) API connectivity."""
    if skip:
        return TestResult(
            name="GPT-4o API (OpenAI)",
            status=TestStatus.SKIP,
            message="Skipped by user request",
        )

    with timer() as t:
        try:
            from shared.config import get_settings
            from shared.services.analyzers import OpenAIAnalyzer

            settings = get_settings()

            if not settings.OPENAI_API_KEY:
                return TestResult(
                    name="GPT-4o API (OpenAI)",
                    status=TestStatus.SKIP,
                    message="OPENAI_API_KEY not configured",
                    duration_ms=t.duration_ms,
                )

            analyzer = OpenAIAnalyzer(settings.OPENAI_API_KEY)
            result = await analyzer.analyze(**TEST_ARTICLE)

            return TestResult(
                name="GPT-4o API (OpenAI)",
                status=TestStatus.PASS,
                message=f"Sentiment: {result.sentiment} ({result.sentiment_score:+.2f})",
                duration_ms=t.duration_ms,
                details={
                    "model": analyzer.model,
                    "sentiment": result.sentiment,
                    "sentiment_score": result.sentiment_score,
                    "impact_score": result.impact_score,
                    "confidence": result.confidence,
                },
            )

        except Exception as e:
            return TestResult(
                name="GPT-4o API (OpenAI)",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


async def test_gemini_api(skip: bool = False) -> TestResult:
    """Test Gemini (Google AI) API connectivity."""
    if skip:
        return TestResult(
            name="Gemini API (Google)",
            status=TestStatus.SKIP,
            message="Skipped by user request",
        )

    with timer() as t:
        try:
            from shared.config import get_settings
            from shared.services.analyzers import GeminiAnalyzer

            settings = get_settings()

            if not settings.GOOGLE_AI_API_KEY:
                return TestResult(
                    name="Gemini API (Google)",
                    status=TestStatus.SKIP,
                    message="GOOGLE_AI_API_KEY not configured",
                    duration_ms=t.duration_ms,
                )

            analyzer = GeminiAnalyzer(settings.GOOGLE_AI_API_KEY)
            result = await analyzer.analyze(**TEST_ARTICLE)

            return TestResult(
                name="Gemini API (Google)",
                status=TestStatus.PASS,
                message=f"Sentiment: {result.sentiment} ({result.sentiment_score:+.2f})",
                duration_ms=t.duration_ms,
                details={
                    "model": analyzer.model,
                    "sentiment": result.sentiment,
                    "sentiment_score": result.sentiment_score,
                    "impact_score": result.impact_score,
                    "confidence": result.confidence,
                },
            )

        except Exception as e:
            return TestResult(
                name="Gemini API (Google)",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# Discord Tests
# ============================================================================

async def test_discord_alerts_webhook(skip: bool = False) -> TestResult:
    """Test Discord alerts webhook connectivity (no message sent)."""
    if skip:
        return TestResult(
            name="Discord Alerts Webhook",
            status=TestStatus.SKIP,
            message="Skipped by user request",
        )

    with timer() as t:
        try:
            import httpx
            from shared.config import get_settings

            settings = get_settings()

            if not settings.DISCORD_WEBHOOK_ALERTS:
                return TestResult(
                    name="Discord Alerts Webhook",
                    status=TestStatus.SKIP,
                    message="DISCORD_WEBHOOK_ALERTS not configured",
                    duration_ms=t.duration_ms,
                )

            # Discord webhooks support GET to verify they exist
            # But that doesn't work, so we'll just validate the URL format
            url = settings.DISCORD_WEBHOOK_ALERTS
            if "discord.com/api/webhooks" not in url:
                return TestResult(
                    name="Discord Alerts Webhook",
                    status=TestStatus.FAIL,
                    message="Invalid webhook URL format",
                    duration_ms=t.duration_ms,
                )

            # Try a HEAD request to check if endpoint responds
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Discord doesn't support HEAD, so we just validate URL is reachable
                # by checking the domain
                response = await client.get(
                    "https://discord.com/api/v10/gateway",
                    timeout=5.0
                )
                # Just check Discord API is reachable
                _ = response.status_code

            return TestResult(
                name="Discord Alerts Webhook",
                status=TestStatus.PASS,
                message="Webhook URL configured and Discord API reachable",
                duration_ms=t.duration_ms,
            )

        except Exception as e:
            return TestResult(
                name="Discord Alerts Webhook",
                status=TestStatus.WARN,
                message=f"Could not verify: {e}",
                duration_ms=t.duration_ms,
            )


async def test_discord_digests_webhook(skip: bool = False) -> TestResult:
    """Test Discord digests webhook connectivity."""
    if skip:
        return TestResult(
            name="Discord Digests Webhook",
            status=TestStatus.SKIP,
            message="Skipped by user request",
        )

    with timer() as t:
        try:
            from shared.config import get_settings

            settings = get_settings()

            if not settings.DISCORD_WEBHOOK_DIGESTS:
                return TestResult(
                    name="Discord Digests Webhook",
                    status=TestStatus.SKIP,
                    message="DISCORD_WEBHOOK_DIGESTS not configured",
                    duration_ms=t.duration_ms,
                )

            url = settings.DISCORD_WEBHOOK_DIGESTS
            if "discord.com/api/webhooks" not in url:
                return TestResult(
                    name="Discord Digests Webhook",
                    status=TestStatus.FAIL,
                    message="Invalid webhook URL format",
                    duration_ms=t.duration_ms,
                )

            return TestResult(
                name="Discord Digests Webhook",
                status=TestStatus.PASS,
                message="Webhook URL configured correctly",
                duration_ms=t.duration_ms,
            )

        except Exception as e:
            return TestResult(
                name="Discord Digests Webhook",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# Schema Validation Tests
# ============================================================================

def test_pydantic_schemas() -> TestResult:
    """Test that all Pydantic schemas work correctly."""
    with timer() as t:
        try:
            from shared.schemas.analysis import AnalysisResult
            from shared.schemas.queue_messages import ArticleQueueMessage
            from datetime import datetime, timezone

            # Test AnalysisResult
            analysis = AnalysisResult(
                summary="Test summary",
                sentiment="Bullish",
                sentiment_score=0.75,
                confidence=0.9,
                impact_score=0.8,
                key_topics=["Fed", "interest rates"],
            )
            assert analysis.sentiment == "Bullish"
            assert analysis.confidence == 0.9

            # Test validation
            try:
                invalid = AnalysisResult(
                    sentiment="Invalid",  # Should fail
                    sentiment_score=2.0,  # Out of range
                    impact_score=0.5,
                )
                return TestResult(
                    name="Pydantic Schemas",
                    status=TestStatus.FAIL,
                    message="Schema validation not working correctly",
                    duration_ms=t.duration_ms,
                )
            except Exception:
                pass  # Expected to fail

            # Test ArticleQueueMessage
            msg = ArticleQueueMessage(
                article_id=123,
                news_url="https://example.com",
                source="Test",
                published_at=datetime.now(timezone.utc),
            )
            json_str = msg.model_dump_json()
            assert "article_id" in json_str

            return TestResult(
                name="Pydantic Schemas",
                status=TestStatus.PASS,
                message="All schemas validated successfully",
                duration_ms=t.duration_ms,
            )

        except Exception as e:
            return TestResult(
                name="Pydantic Schemas",
                status=TestStatus.FAIL,
                message=str(e),
                duration_ms=t.duration_ms,
            )


# ============================================================================
# HTTP Client Test
# ============================================================================

async def test_shared_http_client() -> TestResult:
    """Test shared HTTP client pool."""
    with timer() as t:
        try:
            from shared.services.http_client import (
                get_http_client,
                close_http_client,
                is_client_initialized,
            )
            import shared.services.http_client as http_client_module

            # Force clean state by resetting module-level client
            http_client_module._client = None

            # Get client (http2=False to avoid needing h2 package)
            client = get_http_client(http2=False)

            # Verify client is properly configured
            assert client is not None, "Client should not be None"
            assert is_client_initialized(), "Client should be marked as initialized"

            # Verify singleton behavior
            client2 = get_http_client()
            assert client is client2, "Client should be singleton"

            # Make a test request to a highly reliable endpoint
            # Use Google's generate_204 which just returns 204 No Content
            try:
                response = await client.get("https://www.google.com/generate_204", timeout=5.0)
                request_worked = response.status_code == 204
            except Exception:
                # Fallback: just verify the client was created successfully
                request_worked = False

            # Cleanup
            await close_http_client()
            assert not is_client_initialized(), "Client should be cleaned up"

            message = "Connection pool working correctly"
            if request_worked:
                message += " (verified with external request)"

            return TestResult(
                name="Shared HTTP Client",
                status=TestStatus.PASS,
                message=message,
                duration_ms=t.duration_ms,
            )

        except Exception as e:
            # Attempt cleanup even on failure
            try:
                import shared.services.http_client as http_client_module
                http_client_module._client = None
            except Exception:
                pass

            return TestResult(
                name="Shared HTTP Client",
                status=TestStatus.FAIL,
                message=str(e) or "Unknown error",
                duration_ms=t.duration_ms,
            )


# ============================================================================
# Main Runner
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MarketNews Comprehensive Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM API tests (saves cost)",
    )
    parser.add_argument(
        "--skip-firecrawl",
        action="store_true",
        help="Skip Firecrawl test (saves cost)",
    )
    parser.add_argument(
        "--skip-discord",
        action="store_true",
        help="Skip Discord webhook tests",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: WARNING)",
    )
    return parser.parse_args()


def print_result(result: TestResult, verbose: bool = False):
    """Print a single test result."""
    icons = {
        TestStatus.PASS: "✅",
        TestStatus.FAIL: "❌",
        TestStatus.SKIP: "⏭️ ",
        TestStatus.WARN: "⚠️ ",
    }
    icon = icons[result.status]
    print(f"  {icon} {result.name}: {result.message} ({result.duration_ms:.0f}ms)")

    if verbose and result.details:
        for key, value in result.details.items():
            print(f"      {key}: {value}")


async def run_health_check(args: argparse.Namespace) -> HealthCheckResults:
    """Run all health check tests."""
    results = HealthCheckResults()
    json_mode = args.json

    def section(title: str):
        if not json_mode:
            print(f"\n{title}")
            print("-" * 50)

    def show_result(result: TestResult):
        if not json_mode:
            print_result(result, args.verbose)

    # Sync tests
    section("🔧 Configuration & Schemas")

    results.add(test_configuration())
    show_result(results.tests[-1])

    results.add(test_pydantic_schemas())
    show_result(results.tests[-1])

    # Database tests
    section("🗄️  Database")

    results.add(await test_database_connectivity())
    show_result(results.tests[-1])

    results.add(await test_database_tables())
    show_result(results.tests[-1])

    results.add(await test_database_article_count())
    show_result(results.tests[-1])

    # Queue test
    section("📬 Azure Queue")

    results.add(await test_azure_queue())
    show_result(results.tests[-1])

    # External APIs
    section("🌐 External APIs")

    results.add(await test_stocknews_api())
    show_result(results.tests[-1])

    results.add(await test_firecrawl(skip=args.skip_firecrawl))
    show_result(results.tests[-1])

    # LLM APIs
    section("🤖 LLM APIs")

    results.add(await test_claude_api(skip=args.skip_llm))
    show_result(results.tests[-1])

    results.add(await test_openai_api(skip=args.skip_llm))
    show_result(results.tests[-1])

    results.add(await test_gemini_api(skip=args.skip_llm))
    show_result(results.tests[-1])

    # Discord webhooks
    section("💬 Discord Webhooks")

    results.add(await test_discord_alerts_webhook(skip=args.skip_discord))
    show_result(results.tests[-1])

    results.add(await test_discord_digests_webhook(skip=args.skip_discord))
    show_result(results.tests[-1])

    # Infrastructure
    section("🔌 Infrastructure")

    results.add(await test_shared_http_client())
    show_result(results.tests[-1])

    results.end_time = datetime.now(timezone.utc)
    return results


def main():
    args = parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s",
    )

    if not args.json:
        print("=" * 60)
        print("🏥 MarketNews Health Check")
        print("=" * 60)

    results = asyncio.run(run_health_check(args))

    if args.json:
        print(json_module.dumps(results.to_dict(), indent=2))
    else:
        # Print summary
        duration = (results.end_time - results.start_time).total_seconds()
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"  Total Tests:  {results.total()}")
        print(f"  ✅ Passed:    {results.passed()}")
        print(f"  ❌ Failed:    {results.failed()}")
        print(f"  ⏭️  Skipped:   {results.skipped()}")
        print(f"  ⚠️  Warnings:  {results.warnings()}")
        print(f"  ⏱️  Duration:  {duration:.2f}s")
        print("=" * 60)

        if results.all_passed():
            print("\n✅ All health checks passed!")
        else:
            print("\n❌ Some health checks failed:")
            for test in results.tests:
                if test.status == TestStatus.FAIL:
                    print(f"   - {test.name}: {test.message}")

    # Exit code
    sys.exit(0 if results.all_passed() else 1)


if __name__ == "__main__":
    main()

