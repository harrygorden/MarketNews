"""
Schemas for messages sent to Azure Storage Queue.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ArticleQueueMessage(BaseModel):
    article_id: int = Field(..., description="Database ID of the article to process")
    news_url: str | None = Field(None, description="Original article URL")
    source: str | None = Field(None, description="Article source name")
    published_at: datetime | None = Field(None, description="Publication time in ISO format")

