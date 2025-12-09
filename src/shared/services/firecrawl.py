"""
Firecrawl API client for article scraping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.firecrawl.dev/v1/scrape"


@dataclass
class FirecrawlClient:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 20.0
    _http_client: Optional[httpx.AsyncClient] = field(default=None, repr=False)

    async def scrape(self, url: str) -> Optional[str]:
        """
        Scrape the given URL and return the content/body text.
        """

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload: dict[str, Any] = {
            "url": url,
            "formats": ["markdown"],
            "waitFor": 1000,  # Wait 1s for JS to render
            "onlyMainContent": True,  # Strip nav/footer/ads
        }

        # Use shared client if available, otherwise create a temporary one
        if self._http_client is not None:
            resp = await self._http_client.post(self.base_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.base_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

        # Firecrawl v1 nests content under data.data
        inner = data.get("data", {})
        content = inner.get("markdown") or inner.get("content")
        if not content:
            logger.warning("Firecrawl returned no content for %s", url)
            return None
        return content

    def with_client(self, client: httpx.AsyncClient) -> "FirecrawlClient":
        """Return a new instance using the provided HTTP client."""
        return FirecrawlClient(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            _http_client=client,
        )

