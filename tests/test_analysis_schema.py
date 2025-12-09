from shared.schemas.analysis import AnalysisResult


def test_analysis_result_validation():
    res = AnalysisResult(
        summary="Brief summary",
        sentiment="Bullish",
        sentiment_score=0.25,
        confidence=0.9,
        impact_score=0.6,
        key_topics=["Fed", "Rates"],
    )

    data = res.model_dump()
    assert data["sentiment"] == "Bullish"
    assert data["sentiment_score"] == 0.25
    assert data["confidence"] == 0.9
    assert "Fed" in data["key_topics"]


def test_analysis_result_allows_missing_summary():
    res = AnalysisResult(
        sentiment="Bearish",
        sentiment_score=-0.1,
        confidence=0.5,
        impact_score=0.4,
        key_topics=["economy"],
    )

    assert res.summary is None
    assert res.confidence == 0.5
