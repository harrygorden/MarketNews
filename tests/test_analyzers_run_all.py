import asyncio

from shared.schemas.analysis import AnalysisResult
from shared.services.analyzers import run_all_analyzers


class _FakeAnalyzer:
    def __init__(self, provider: str, model: str, summary: str):
        self.provider = provider
        self.model = model
        self._summary = summary

    async def analyze(self, *, title: str, source: str | None, published_at, content: str) -> AnalysisResult:
        return AnalysisResult(
            summary=self._summary,
            sentiment="Neutral",
            sentiment_score=0.0,
            impact_score=0.1,
            key_topics=["test"],
        )


def test_run_all_analyzers_returns_provider_and_model():
    analyzers = [
        _FakeAnalyzer("anthropic", "claude", "A"),
        _FakeAnalyzer("openai", "gpt", "B"),
    ]

    results = asyncio.run(
        run_all_analyzers(
            analyzers=analyzers, title="t", source="s", published_at=None, content="c"
        )
    )

    providers = [p for p, _m, _r in results]
    models = [m for _p, m, _r in results]
    summaries = [r.summary for _p, _m, r in results]

    assert providers == ["anthropic", "openai"]
    assert models == ["claude", "gpt"]
    assert summaries == ["A", "B"]

