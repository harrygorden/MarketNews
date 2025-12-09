"""
StockNewsAPI client with paywall filtering and basic dedup helpers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, List, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Use the category endpoint per StockNewsAPI docs.
DEFAULT_BASE_URL = "https://stocknewsapi.com/api/v1/category"


class NewsItem(BaseModel):
    news_url: str
    title: str
    text: str | None = None
    source_name: str | None = None
    date: str | None = None
    topics: list[str] = Field(default_factory=list)
    sentiment: str | None = None

    def published_at(self) -> Optional[datetime]:
        if not self.date:
            return None
        date_str = self.date

        # Try ISO8601 first (StockNewsAPI sometimes returns this)
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Fallback: StockNewsAPI also returns RFC 2822 strings, e.g. "Mon, 08 Dec 2025 16:27:10 -0500"
        try:
            parsed = parsedate_to_datetime(date_str)
            if parsed:
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass

        logger.warning("Could not parse date %s", self.date)
        return None


class NewsApiResponse(BaseModel):
    data: list[NewsItem] = Field(default_factory=list)
    message: str | None = None
    total_pages: int | None = None
    page: int | None = None


@dataclass
class StockNewsClient:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 10.0
    _http_client: Optional[httpx.AsyncClient] = field(default=None, repr=False)

    async def fetch_latest(
        self,
        *,
        section: str = "general",
        items: int = 50,
        page: int = 1,
        tickers: str | None = None,
        topicexclude: str | None = "paywall,paylimitwall,podcast",
    ) -> list[NewsItem]:
        """
        Fetch latest news from StockNewsAPI category endpoint.
        """

        params = {
            "token": self.api_key,
            "section": section,
            "items": items,
            "page": page,
        }
        if tickers:
            params["tickers"] = tickers
        if topicexclude:
            params["topicexclude"] = topicexclude

        # Use shared client if available, otherwise create a temporary one
        if self._http_client is not None:
            response = await self._http_client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()

        try:
            parsed = NewsApiResponse(**payload)
        except ValidationError as exc:
            logger.error("Failed to parse StockNewsAPI response: %s", exc)
            raise

        return parsed.data

    def with_client(self, client: httpx.AsyncClient) -> "StockNewsClient":
        """Return a new instance using the provided HTTP client."""
        return StockNewsClient(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            _http_client=client,
        )


def is_paywalled(topics: Iterable[str]) -> bool:
    """
    Determine if the article topics indicate a paywall.
    """

    normalized = {t.lower() for t in topics}
    return "paywall" in normalized or "paylimitwall" in normalized


def filter_new_articles(
    items: Iterable[NewsItem], existing_urls: set[str]
) -> list[NewsItem]:
    """
    Filter out paywalled or duplicate articles by URL (existing in DB or within the same fetch).
    """

    results: list[NewsItem] = []
    seen_new: set[str] = set()
    for item in items:
        if is_paywalled(item.topics):
            logger.debug("Skipping paywalled article: %s", item.news_url)
            continue
        if item.news_url in existing_urls:
            logger.debug("Skipping duplicate article: %s", item.news_url)
            continue
        if item.news_url in seen_new:
            logger.debug("Skipping in-batch duplicate article: %s", item.news_url)
            continue
        seen_new.add(item.news_url)
        results.append(item)
    return results

