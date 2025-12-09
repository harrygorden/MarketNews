import asyncio

import pytest

from shared.services.firecrawl import FirecrawlClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, headers):
        self.post_calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_scrape_returns_markdown(monkeypatch):
    payload = {"data": {"markdown": "hello world"}}
    fake_client = _FakeClient(payload)
    monkeypatch.setattr(
        "shared.services.firecrawl.httpx.AsyncClient", lambda timeout: fake_client
    )

    client = FirecrawlClient("token")
    result = await client.scrape("http://example.com")

    assert result == "hello world"
    assert len(fake_client.post_calls) == 1
    assert fake_client.post_calls[0]["url"] == "https://api.firecrawl.dev/v1/scrape"


@pytest.mark.asyncio
async def test_scrape_returns_none_when_no_content(monkeypatch):
    payload = {"data": {}}
    fake_client = _FakeClient(payload)
    monkeypatch.setattr(
        "shared.services.firecrawl.httpx.AsyncClient", lambda timeout: fake_client
    )

    client = FirecrawlClient("token")
    result = await client.scrape("http://example.com")

    assert result is None

