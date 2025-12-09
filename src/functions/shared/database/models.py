"""
SQLAlchemy ORM models for the MarketNews application.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("idx_articles_published_at", text("published_at DESC")),
        Index("idx_articles_created_at", text("created_at DESC")),
        Index("idx_articles_source", "source"),
        Index("idx_articles_scrape_failed", "scrape_failed", postgresql_where=text("scrape_failed = TRUE")),
    )

    id = Column(Integer, primary_key=True)
    news_url = Column(String(2048), nullable=False, unique=True)
    title = Column(String(500), nullable=False)
    source = Column(String(100))
    published_at = Column(DateTime(timezone=True))
    topics = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    api_sentiment = Column(String(50))
    raw_api_response = Column(JSONB)
    scraped_content = Column(Text)
    scraped_at = Column(DateTime(timezone=True))
    scrape_failed = Column(Boolean, nullable=False, server_default=text("FALSE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    included_in_digest_at = Column(DateTime(timezone=True))

    analyses = relationship(
        "ArticleAnalysis", back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )
    digest_articles = relationship(
        "DigestArticle", back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )
    failures = relationship(
        "ProcessingQueueFailure", back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )


class ArticleAnalysis(Base):
    __tablename__ = "article_analyses"
    __table_args__ = (
        UniqueConstraint("article_id", "model_provider", name="uq_article_analysis_provider"),
        CheckConstraint(
            "sentiment_score >= -1.0 AND sentiment_score <= 1.0", name="ck_analysis_sentiment_score_range"
        ),
        CheckConstraint(
            "impact_score >= 0.0 AND impact_score <= 1.0", name="ck_analysis_impact_score_range"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_analysis_confidence_range",
        ),
        Index("idx_analyses_article_id", "article_id"),
        Index("idx_analyses_sentiment", "sentiment"),
        Index("idx_analyses_impact_score", text("impact_score DESC")),
    )

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    model_provider = Column(String(50), nullable=False)  # anthropic/openai/google
    model_name = Column(String(100), nullable=False)  # claude-sonnet-4-5/gpt-4o/gemini-2.5-pro
    summary = Column(Text)
    sentiment = Column(String(20))
    sentiment_score = Column(Numeric(4, 3))
    confidence = Column(Numeric(4, 3))
    impact_score = Column(Numeric(4, 3))
    key_topics = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    raw_response = Column(JSONB)
    analyzed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    article = relationship("Article", back_populates="analyses", lazy="joined")


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (Index("idx_digests_type_sent", "digest_type", text("sent_at DESC")),)

    id = Column(Integer, primary_key=True)
    digest_type = Column(String(20), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    article_count = Column(Integer, nullable=False, server_default=text("0"))
    discord_message_id = Column(String(100))

    digest_articles = relationship(
        "DigestArticle", back_populates="digest", cascade="all, delete-orphan", lazy="selectin"
    )


class DigestArticle(Base):
    __tablename__ = "digest_articles"
    __table_args__ = (UniqueConstraint("digest_id", "article_id", name="uq_digest_article"),)

    id = Column(Integer, primary_key=True)
    digest_id = Column(Integer, ForeignKey("digests.id", ondelete="CASCADE"), nullable=False)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    rank = Column(Integer)

    digest = relationship("Digest", back_populates="digest_articles", lazy="joined")
    article = relationship("Article", back_populates="digest_articles", lazy="joined")


class ProcessingQueueFailure(Base):
    __tablename__ = "processing_queue_failures"
    __table_args__ = (Index("idx_failures_resolved", "resolved", postgresql_where=text("resolved = FALSE")),)

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="SET NULL"))
    error_message = Column(String(1000))
    stack_trace = Column(Text)
    attempt_count = Column(Integer, nullable=False, server_default=text("1"))
    first_failure_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_failure_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved = Column(Boolean, nullable=False, server_default=text("FALSE"))

    article = relationship("Article", back_populates="failures", lazy="joined")

