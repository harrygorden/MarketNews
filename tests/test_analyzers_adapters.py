import asyncio
import json

import pytest

from shared.services.analyzers import GeminiAnalyzer


class _FakeModel:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = []

    def generate_content(self, payload):
        self.calls.append(payload)

        class Resp:
            def __init__(self, text: str):
                self.text = text

        return Resp(self.response_text)


def _fake_response():
    return json.dumps(
        {
            "summary": "summary",
            "sentiment": "Neutral",
            "sentiment_score": 0.1,
            "confidence": 0.82,
            "impact_score": 0.2,
            "key_topics": ["markets"],
        }
    )


@pytest.mark.asyncio
async def test_gemini_analyze_text(monkeypatch):
    fake_model = _FakeModel(_fake_response())

    monkeypatch.setattr("shared.services.analyzers.genai.configure", lambda api_key: None)
    monkeypatch.setattr(
        "shared.services.analyzers.genai.GenerativeModel",
        lambda model_name: fake_model,
    )

    analyzer = GeminiAnalyzer("token")
    result = await analyzer.analyze(
        title="Title",
        source="Source",
        published_at="2025-01-01",
        content="Body text",
    )

    assert result.summary is None
    assert result.confidence == 0.82
    assert len(fake_model.calls) == 1
    assert isinstance(fake_model.calls[0], str)
    assert "Title: Title" in fake_model.calls[0]


@pytest.mark.asyncio
async def test_gemini_analyze_youtube(monkeypatch):
    fake_model = _FakeModel(_fake_response())

    monkeypatch.setattr("shared.services.analyzers.genai.configure", lambda api_key: None)
    monkeypatch.setattr(
        "shared.services.analyzers.genai.GenerativeModel",
        lambda model_name: fake_model,
    )

    analyzer = GeminiAnalyzer("token")
    result = await analyzer.analyze(
        title="Title",
        source="Source",
        published_at="2025-01-01",
        content="",
        youtube_url="https://youtu.be/abc",
    )

    assert result.summary is None
    assert result.confidence == 0.82
    assert len(fake_model.calls) == 1
    payload = fake_model.calls[0]
    assert isinstance(payload, list)
    assert payload[0]["file_data"]["file_uri"] == "https://youtu.be/abc"
    assert "Watch the attached YouTube video" in payload[1]

