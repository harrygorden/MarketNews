"""
LLM analyzers for Claude, GPT-4o, and Gemini.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

import google.generativeai as genai
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import ValidationError

from shared.schemas.analysis import AnalysisResult

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are a financial news analyst specializing in market sentiment analysis for futures traders.

Analyze the following news article and provide a structured assessment.

ARTICLE:
Title: {title}
Source: {source}
Published: {published_at}
Content:
{content}

Provide your analysis in the following JSON format:
{{
  "summary": "A 2-3 sentence summary of the article's key points and market implications",
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "sentiment_score": <float from -1.0 (most bearish) to 1.0 (most bullish)>,
  "confidence": <float from 0.0 (lowest confidence) to 1.0 (highest confidence)>,
  "impact_score": <float from 0.0 (minimal impact) to 1.0 (major market-moving)>,
  "key_topics": ["list", "of", "relevant", "entities", "and", "topics"]
}}

SCORING GUIDELINES:
- Sentiment: Consider implications for S&P 500, Nasdaq, and Gold futures
- Impact Score:
  - 0.0-0.3: Routine news, minor market relevance
  - 0.4-0.6: Notable news, moderate market relevance
  - 0.7-0.9: Significant news, high market relevance
  - 0.9-1.0: Major market-moving event (Fed decisions, major economic data, geopolitical events)

Focus on implications for:
- ES (S&P 500 E-mini futures)
- NQ (Nasdaq E-mini futures)
- GC (Gold futures)
- Federal Reserve / FOMC policy
- Major economic indicators

Return ONLY the JSON object, no additional text.
"""

YOUTUBE_PROMPT_TEMPLATE = """You are a financial news analyst specializing in market sentiment analysis for futures traders.

Watch the attached YouTube video carefully and provide a structured assessment of its financial market implications.

VIDEO METADATA:
Title: {title}
Source: {source}
Published: {published_at}

After watching the video, provide your analysis in the following JSON format:
{{
  "summary": "A 2-3 sentence summary of the video's key points and market implications",
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "sentiment_score": <float from -1.0 (most bearish) to 1.0 (most bullish)>,
  "confidence": <float from 0.0 (lowest confidence) to 1.0 (highest confidence)>,
  "impact_score": <float from 0.0 (minimal impact) to 1.0 (major market-moving)>,
  "key_topics": ["list", "of", "relevant", "entities", "and", "topics"]
}}

SCORING GUIDELINES:
- Sentiment: Consider implications for S&P 500, Nasdaq, and Gold futures
- Impact Score:
  - 0.0-0.3: Routine news, minor market relevance
  - 0.4-0.6: Notable news, moderate market relevance
  - 0.7-0.9: Significant news, high market relevance
  - 0.9-1.0: Major market-moving event (Fed decisions, major economic data, geopolitical events)

Focus on implications for:
- ES (S&P 500 E-mini futures)
- NQ (Nasdaq E-mini futures)
- GC (Gold futures)
- Federal Reserve / FOMC policy
- Major economic indicators

Return ONLY the JSON object, no additional text.
"""

METRICS_PROMPT_TEMPLATE = """You are a financial news analyst specializing in market sentiment analysis for futures traders.

Analyze the following news article and provide ONLY the sentiment, impact, and key topics (no summary).

ARTICLE:
Title: {title}
Source: {source}
Published: {published_at}
Content:
{content}

Provide your analysis in the following JSON format:
{{
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "sentiment_score": <float from -1.0 (most bearish) to 1.0 (most bullish)>,
  "confidence": <float from 0.0 (lowest confidence) to 1.0 (highest confidence)>,
  "impact_score": <float from 0.0 (minimal impact) to 1.0 (major market-moving)>,
  "key_topics": ["list", "of", "relevant", "entities", "and", "topics"]
}}

SCORING GUIDELINES:
- Sentiment: Consider implications for S&P 500, Nasdaq, and Gold futures
- Impact Score:
  - 0.0-0.3: Routine news, minor market relevance
  - 0.4-0.6: Notable news, moderate market relevance
  - 0.7-0.9: Significant news, high market relevance
  - 0.9-1.0: Major market-moving event (Fed decisions, major economic data, geopolitical events)

Focus on implications for:
- ES (S&P 500 E-mini futures)
- NQ (Nasdaq E-mini futures)
- GC (Gold futures)
- Federal Reserve / FOMC policy
- Major economic indicators

Return ONLY the JSON object, no additional text.
"""

YOUTUBE_METRICS_PROMPT_TEMPLATE = """You are a financial news analyst specializing in market sentiment analysis for futures traders.

Watch the attached YouTube video carefully and provide ONLY sentiment, impact, and key topics (no summary).

VIDEO METADATA:
Title: {title}
Source: {source}
Published: {published_at}

After watching the video, provide your analysis in the following JSON format:
{{
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "sentiment_score": <float from -1.0 (most bearish) to 1.0 (most bullish)>,
  "confidence": <float from 0.0 (lowest confidence) to 1.0 (highest confidence)>,
  "impact_score": <float from 0.0 (minimal impact) to 1.0 (major market-moving)>,
  "key_topics": ["list", "of", "relevant", "entities", "and", "topics"]
}}

SCORING GUIDELINES:
- Sentiment: Consider implications for S&P 500, Nasdaq, and Gold futures
- Impact Score:
  - 0.0-0.3: Routine news, minor market relevance
  - 0.4-0.6: Notable news, moderate market relevance
  - 0.7-0.9: Significant news, high market relevance
  - 0.9-1.0: Major market-moving event (Fed decisions, major economic data, geopolitical events)

Focus on implications for:
- ES (S&P 500 E-mini futures)
- NQ (Nasdaq E-mini futures)
- GC (Gold futures)
- Federal Reserve / FOMC policy
- Major economic indicators

Return ONLY the JSON object, no additional text.
"""


def _build_prompt(title: str, source: str | None, published_at: Any, content: str, include_summary: bool = True) -> str:
    template = PROMPT_TEMPLATE if include_summary else METRICS_PROMPT_TEMPLATE
    return template.format(
        title=title,
        source=source or "Unknown",
        published_at=published_at or "Unknown",
        content=content,
    )


def _build_youtube_prompt(title: str, source: str | None, published_at: Any, include_summary: bool = True) -> str:
    template = YOUTUBE_PROMPT_TEMPLATE if include_summary else YOUTUBE_METRICS_PROMPT_TEMPLATE
    return template.format(
        title=title,
        source=source or "Unknown",
        published_at=published_at or "Unknown",
    )


def _strip_code_fences(raw: str) -> str:
    """Strip markdown code fences from LLM responses."""
    text = raw.strip()
    # Handle ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        # Find the end of the first line (may be ```json or just ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Strip trailing ```
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


async def _run_and_parse(run: Callable[[], Coroutine[Any, Any, str]]) -> AnalysisResult:
    raw = await run()
    cleaned = _strip_code_fences(raw)
    try:
        return AnalysisResult.model_validate_json(cleaned)
    except ValidationError as exc:
        logger.error("Failed to parse LLM response: %s", exc)
        raise


@dataclass
class ClaudeAnalyzer:
    api_key: str
    model: str = "claude-sonnet-4-5-20250929"
    provider: str = "anthropic"

    async def analyze(self, *, title: str, source: str | None, published_at: Any, content: str) -> AnalysisResult:
        client = AsyncAnthropic(api_key=self.api_key)
        prompt = _build_prompt(title, source, published_at, content, include_summary=True)

        async def run() -> str:
            msg = await client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text  # type: ignore[index]

        return await _run_and_parse(run)


@dataclass
class OpenAIAnalyzer:
    api_key: str
    model: str = "gpt-4o"
    provider: str = "openai"

    async def analyze(self, *, title: str, source: str | None, published_at: Any, content: str) -> AnalysisResult:
        client = AsyncOpenAI(api_key=self.api_key)
        prompt = _build_prompt(title, source, published_at, content, include_summary=False)

        async def run() -> str:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            return resp.choices[0].message.content or "{}"

        return await _run_and_parse(run)


@dataclass
class GeminiAnalyzer:
    api_key: str
    model: str = "gemini-2.5-pro"
    provider: str = "google"

    async def analyze(
        self,
        *,
        title: str,
        source: str | None,
        published_at: Any,
        content: str,
        youtube_url: str | None = None,
    ) -> AnalysisResult:
        genai.configure(api_key=self.api_key)

        async def run() -> str:
            # google-generativeai does not expose async; run in a thread
            loop = asyncio.get_running_loop()

            def _sync_call() -> str:
                model = genai.GenerativeModel(self.model)
                if youtube_url:
                    # Use multimodal: Gemini watches the YouTube video
                    prompt = _build_youtube_prompt(title, source, published_at, include_summary=False)
                    resp = model.generate_content([
                        {"file_data": {"file_uri": youtube_url}},
                        prompt,
                    ])
                else:
                    prompt = _build_prompt(title, source, published_at, content, include_summary=False)
                    resp = model.generate_content(prompt)
                return resp.text or "{}"

            return await loop.run_in_executor(None, _sync_call)

        return await _run_and_parse(run)


async def run_all_analyzers(
    *,
    analyzers: list[Any],
    title: str,
    source: str | None,
    published_at: Any,
    content: str,
    youtube_url: str | None = None,
) -> list[tuple[str, str, AnalysisResult]]:
    tasks = []
    for analyzer in analyzers:
        provider = getattr(analyzer, "provider", "unknown")
        model_name = getattr(analyzer, "model", "auto")
        # Pass youtube_url only to Gemini (it supports video analysis)
        if provider == "google" and youtube_url:
            coro = analyzer.analyze(
                title=title, source=source, published_at=published_at, content=content, youtube_url=youtube_url
            )
        else:
            coro = analyzer.analyze(title=title, source=source, published_at=published_at, content=content)
        tasks.append(_wrap_with_provider(provider, model_name, coro))
    return await asyncio.gather(*tasks)


async def _wrap_with_provider(provider: str, model: str, coro: Coroutine[Any, Any, AnalysisResult]) -> tuple[str, str, AnalysisResult]:
    res = await coro
    return provider, model, res

