"""
Schemas for LLM analysis results.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, field_validator


class AnalysisResult(BaseModel):
    summary: str | None = Field(None, min_length=1)
    sentiment: str = Field(..., pattern="^(Bullish|Bearish|Neutral)$")
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    impact_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="Model confidence in sentiment classification (0-1).")
    key_topics: List[str] = Field(default_factory=list)
    analyzed_at: datetime | None = None

    @field_validator("key_topics", mode="before")
    @classmethod
    def _coerce_topics(cls, value):
        if value is None:
            return []
        return value

    @field_validator("summary")
    @classmethod
    def _clean_summary(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

