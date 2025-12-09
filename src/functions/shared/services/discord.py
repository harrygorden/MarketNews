"""Discord notification service for sending article alerts and digests."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)


class DiscordColor:
    """Discord embed color codes."""
    BULLISH = 0x22C55E  # Green
    BEARISH = 0xEF4444  # Red
    NEUTRAL = 0x6B7280  # Gray
    INFO = 0x3B82F6     # Blue


class DiscordNotifier:
    """Service for sending Discord notifications via webhooks."""
    
    def __init__(
        self,
        alerts_webhook: Optional[str] = None,
        digests_webhook: Optional[str] = None,
        impact_threshold: Optional[float] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Initialize the Discord notifier.
        
        If parameters are not provided, they will be loaded from settings.
        This allows for both eager (from settings) and explicit initialization.
        
        Args:
            alerts_webhook: Discord webhook URL for alerts (optional)
            digests_webhook: Discord webhook URL for digests (optional)
            impact_threshold: Minimum impact score for alerts (optional)
            http_client: Shared HTTP client for connection pooling (optional)
        """
        self._alerts_webhook = alerts_webhook
        self._digests_webhook = digests_webhook
        self._impact_threshold = impact_threshold
        self._http_client = http_client
        self._settings_loaded = False
    
    def _ensure_settings(self) -> None:
        """Lazily load settings if not already provided."""
        if self._settings_loaded:
            return
        
        from ..config import get_settings
        settings = get_settings()
        
        if self._alerts_webhook is None:
            self._alerts_webhook = settings.DISCORD_WEBHOOK_ALERTS
        if self._digests_webhook is None:
            self._digests_webhook = settings.DISCORD_WEBHOOK_DIGESTS
        if self._impact_threshold is None:
            self._impact_threshold = settings.IMPACT_THRESHOLD
        
        self._settings_loaded = True
    
    @property
    def alerts_webhook(self) -> Optional[str]:
        self._ensure_settings()
        return self._alerts_webhook
    
    @property
    def digests_webhook(self) -> Optional[str]:
        self._ensure_settings()
        return self._digests_webhook
    
    @property
    def impact_threshold(self) -> float:
        self._ensure_settings()
        return self._impact_threshold or 0.75
        
    async def send_article_alert(
        self,
        article_id: int,
        title: str,
        source: str,
        published_at: datetime,
        news_url: str,
        sentiment: str,
        avg_sentiment_score: float,
        avg_impact_score: float,
        analyses: list[dict],
        key_topics: list[str]
    ) -> bool:
        """
        Send high-impact article alert to Discord.
        
        Args:
            article_id: Database article ID
            title: Article headline
            source: News source
            published_at: Publication timestamp
            news_url: Original article URL
            sentiment: Consensus sentiment (Bullish/Bearish/Neutral)
            avg_sentiment_score: Average sentiment score (-1 to 1)
            avg_impact_score: Average impact score (0 to 1)
            analyses: List of analysis dicts from all LLMs
            key_topics: Combined key topics from all analyses
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Determine embed color based on sentiment
            color = self._get_sentiment_color(sentiment)
            
            # Format sentiment score display
            sentiment_emoji = self._get_sentiment_emoji(sentiment)
            score_display = f"{sentiment_emoji} **{sentiment}** ({avg_sentiment_score:+.2f})"
            
            # Format impact display with bar
            impact_display = self._format_impact_bar(avg_impact_score)
            
            # Build embed
            footer_text = self._build_sentiment_footer(analyses, sentiment, article_id)

            embed = {
                "title": f"🚨 High-Impact Alert: {title}",
                "description": f"**Source:** {source}\n**Published:** {self._format_timestamp(published_at)}",
                "color": color,
                "fields": [
                    {
                        "name": "📊 Consensus Sentiment",
                        "value": score_display,
                        "inline": True
                    },
                    {
                        "name": "⚡ Impact Score",
                        "value": f"{impact_display}\n`{avg_impact_score:.2f}/1.0`",
                        "inline": True
                    },
                    {
                        "name": "🔍 Key Topics",
                        "value": ", ".join(key_topics[:8]) if key_topics else "None",
                        "inline": False
                    }
                ],
                "url": news_url,
                "footer": {
                    "text": footer_text
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Add model-level sentiment breakdown as inline fields (horizontal layout)
            model_fields = self._build_model_sentiment_fields(analyses)
            embed["fields"].extend(model_fields)
            
            # Add a single, full summary (prefer Claude/Sonnet)
            summary_text, summary_label = self._select_primary_summary(analyses)
            if summary_text:
                embed["fields"].append({
                    "name": "💬 AI Generated Summary",
                    "value": summary_text,
                    "inline": False
                })
            
            # Add links
            embed["fields"].append({
                "name": "🔗 Links",
                "value": f"[Read Original Article]({news_url})",
                "inline": False
            })
            
            # Send webhook
            payload = {
                "embeds": [embed],
                "username": "MarketNews Bot",
                "avatar_url": "https://cdn-icons-png.flaticon.com/512/2593/2593635.png"
            }
            
            # Use shared client if available, otherwise create a temporary one
            if self._http_client is not None:
                response = await self._http_client.post(self.alerts_webhook, json=payload)
                response.raise_for_status()
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(self.alerts_webhook, json=payload)
                    response.raise_for_status()
                
            logger.info(f"Sent Discord alert for article {article_id}: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Discord alert for article {article_id}: {e}", exc_info=True)
            return False
    
    async def send_digest(
        self,
        digest_type: str,
        articles: list[dict],
        period_start: datetime,
        period_end: datetime
    ) -> Optional[str]:
        """
        Send digest summary to Discord.
        
        Args:
            digest_type: Type of digest (premarket/lunch/postmarket/weekly)
            articles: List of article dicts with analyses
            period_start: Start of digest period
            period_end: End of digest period
            
        Returns:
            Discord message ID if sent successfully, None otherwise
        """
        try:
            if not articles:
                # Send empty digest message
                embed = {
                    "title": f"📰 {digest_type.title()} Market Digest",
                    "description": f"No significant market news during this period.\n\n"
                                 f"**Period:** {self._format_timestamp(period_start)} - {self._format_timestamp(period_end)}",
                    "color": DiscordColor.INFO,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                # Build digest with ranked articles
                description = (
                    f"**Period:** {self._format_timestamp(period_start)} - {self._format_timestamp(period_end)}\n"
                    f"**Articles Analyzed:** {len(articles)}\n\n"
                    f"Top articles ranked by consensus and impact:"
                )
                
                embed = {
                    "title": f"📰 {digest_type.title()} Market Digest",
                    "description": description,
                    "color": DiscordColor.INFO,
                    "fields": [],
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Add top articles (limit to 10 for Discord embed limits)
                for i, article in enumerate(articles[:10], 1):
                    sentiment_emoji = self._get_sentiment_emoji(article["sentiment"])
                    impact_bar = self._format_impact_bar(article["avg_impact_score"], width=5)
                    
                    field_value = (
                        f"{sentiment_emoji} **{article['sentiment']}** ({article['avg_sentiment_score']:+.2f}) | "
                        f"Impact: {impact_bar} {article['avg_impact_score']:.2f}\n"
                        f"*{article['source']}* • {self._format_timestamp(article['published_at'])}\n"
                        f"[Read Article]({article['news_url']})"
                    )
                    
                    embed["fields"].append({
                        "name": f"{i}. {article['title'][:100]}{'...' if len(article['title']) > 100 else ''}",
                        "value": field_value,
                        "inline": False
                    })
                
                if len(articles) > 10:
                    embed["footer"] = {
                        "text": f"Showing top 10 of {len(articles)} articles"
                    }
            
            # Send to digests webhook
            payload = {
                "embeds": [embed],
                "username": "MarketNews Digest",
                "avatar_url": "https://cdn-icons-png.flaticon.com/512/2593/2593635.png"
            }
            
            # Use shared client if available, otherwise create a temporary one
            if self._http_client is not None:
                response = await self._http_client.post(self.digests_webhook, json=payload)
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(self.digests_webhook, json=payload)

            response.raise_for_status()
            message_id = self._parse_message_id(response)
                
            logger.info(f"Sent {digest_type} digest with {len(articles)} articles")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to send {digest_type} digest: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _parse_message_id(response: httpx.Response) -> str | None:
        """
        Discord webhooks return 204 No Content by default.
        If content exists, attempt to extract message id; otherwise return None.
        """
        if response.status_code == 204 or not response.content:
            return None
        try:
            data = response.json()
            if isinstance(data, dict):
                return data.get("id")
        except Exception:
            logger.debug("Unable to parse Discord webhook response body for message id.")
        return None
    
    def should_send_alert(
        self,
        analyses: list[dict],
        sentiment: str,
        avg_impact_score: float
    ) -> bool:
        """
        Determine if an article should trigger an alert.
        
        Criteria (updated):
        - At least 1 analysis present (YouTube/Gemini-only is allowed)
        - All analyses have impact >= threshold
        - Sentiment: allow one model to disagree, but:
            * if all sentiments are Neutral -> reject
            * require a simple majority (>=50% rounded up) for the leading sentiment
        
        Args:
            analyses: List of analysis dicts
            sentiment: Consensus sentiment
            avg_impact_score: Average impact score
            
        Returns:
            True if alert should be sent
        """
        if not analyses:
            return False

        # Impact: all analyses must meet threshold
        impacts = []
        for a in analyses:
            try:
                impacts.append(float(a.get("impact_score", 0)))
            except (TypeError, ValueError):
                impacts.append(0.0)
        if not impacts or min(impacts) < self.impact_threshold:
            logger.info(
                "Alert rejected: impact threshold not met (min=%.2f, threshold=%.2f)",
                min(impacts) if impacts else 0.0,
                self.impact_threshold,
            )
            return False

        # Sentiment majority, allow one disagree; reject if all neutral; reject if 2/3 neutral (for 3-model cases)
        sentiments = [str(a.get("sentiment", "")).lower() for a in analyses]
        if sentiments and all(s == "neutral" for s in sentiments):
            logger.info("Alert rejected: all sentiments neutral.")
            return False
        if len(sentiments) == 3 and sentiments.count("neutral") >= 2:
            logger.info("Alert rejected: 2 of 3 sentiments are neutral.")
            return False

        counts = Counter(sentiments)
        leader, leader_count = counts.most_common(1)[0]
        needed = (len(sentiments) + 1) // 2  # simple majority (ceil(n/2))
        has_majority = leader_count >= needed

        if not has_majority:
            logger.info(
                "Alert rejected: no majority sentiment (counts=%s)",
                dict(counts)
            )
            return False

        logger.info(
            "Alert criteria met: majority=%s (%s/%s), min_impact=%.2f >= %.2f",
            leader,
            leader_count,
            len(sentiments),
            min(impacts),
            self.impact_threshold,
        )
        return True
    
    def _build_model_sentiment_fields(self, analyses: list[dict]) -> list[dict]:
        """Build per-model sentiment fields to display horizontally (inline)."""
        fields: list[dict] = []
        for analysis in analyses:
            sentiment = analysis.get("sentiment") or "N/A"
            sentiment_score = analysis.get("sentiment_score")
            impact_score = analysis.get("impact_score")
            confidence = analysis.get("confidence")
            emoji = self._get_sentiment_emoji(str(sentiment))
            label = self._format_model_label(analysis.get("model_provider"), analysis.get("model_name"))
            
            try:
                sentiment_score_display = f"{float(sentiment_score):+.2f}"
            except (TypeError, ValueError):
                sentiment_score_display = "N/A"
            
            try:
                confidence_display = f"{float(confidence) * 100:.0f}%"
            except (TypeError, ValueError):
                confidence_display = "N/A"
            
            try:
                impact_display = f"{float(impact_score):.2f}"
            except (TypeError, ValueError):
                impact_display = "N/A"
            
            value = (
                f"{emoji} {sentiment} ({sentiment_score_display})\n"
                f"Confidence: {confidence_display}\n"
                f"Impact: {impact_display}"
            )
            
            fields.append({
                "name": label,
                "value": value,
                "inline": True
            })
        return fields
    
    def _select_primary_summary(self, analyses: list[dict]) -> tuple[Optional[str], str]:
        """
        Prefer the Claude/Sonnet summary; otherwise return the first available summary.
        """
        ordered = sorted(
            analyses,
            key=lambda a: 0 if (a.get("model_provider") or "").lower() == "anthropic" else 1
        )
        
        for analysis in ordered:
            summary = (analysis.get("summary") or "").strip()
            if not summary:
                continue
            label = self._format_model_label(analysis.get("model_provider"), analysis.get("model_name"))
            return summary, f"{label} Summary"
        
        return None, ""
    
    def _format_model_label(self, provider: Optional[str], model_name: Optional[str]) -> str:
        """Human-friendly model/provider label."""
        provider_lower = (provider or "").lower()
        if provider_lower == "anthropic":
            return "Claude Sonnet 4.5"
        if provider_lower == "openai":
            base = "ChatGPT"
        elif provider_lower == "google":
            base = "Gemini"
        else:
            base = (provider or "Analysis").title()
        
        if model_name:
            return f"{base} ({model_name})"
        return base
    
    def _build_sentiment_footer(self, analyses: list[dict], consensus_sentiment: str, article_id: int) -> str:
        """Build footer text that accurately reflects sentiment agreement/disagreement."""
        sentiments = [str(a.get("sentiment", "")).lower() for a in analyses if a.get("sentiment") is not None]
        counts = Counter(sentiments)
        unique = set(sentiments)
        
        if len(unique) == 1 and sentiments:
            return f"Article ID: {article_id} • All 3 LLMs agree on {consensus_sentiment.lower()} sentiment"
        
        # Build mixed summary e.g., "bearish 2, neutral 1"
        parts = [f"{k} {v}" for k, v in counts.items()]
        breakdown = ", ".join(parts) if parts else "no sentiments"
        return f"Article ID: {article_id} • No consensus across LLMs ({breakdown})"
    
    def _get_sentiment_color(self, sentiment: str) -> int:
        """Get Discord color code for sentiment."""
        sentiment_lower = sentiment.lower()
        if sentiment_lower == "bullish":
            return DiscordColor.BULLISH
        elif sentiment_lower == "bearish":
            return DiscordColor.BEARISH
        else:
            return DiscordColor.NEUTRAL
    
    def _get_sentiment_emoji(self, sentiment: str) -> str:
        """Get colored dot emoji for sentiment."""
        sentiment_lower = sentiment.lower()
        if sentiment_lower == "bullish":
            return "🟢"
        elif sentiment_lower == "bearish":
            return "🔴"
        else:
            return "🟡"
    
    def _format_impact_bar(self, score: float, width: int = 10) -> str:
        """Format impact score as visual bar."""
        filled = int(score * width)
        empty = width - filled
        return "█" * filled + "░" * empty
    
    def _format_timestamp(self, dt: datetime) -> str:
        """Format timestamp for display."""
        if dt:
            return dt.strftime("%b %d, %Y %I:%M %p ET")
        return "Unknown"


# Lazy singleton instance
_discord_notifier: Optional[DiscordNotifier] = None


def get_discord_notifier(
    http_client: Optional[httpx.AsyncClient] = None,
) -> DiscordNotifier:
    """
    Get the Discord notifier singleton instance.
    
    This is the preferred way to access the notifier as it supports
    lazy initialization and optional HTTP client injection.
    
    Args:
        http_client: Optional shared HTTP client for connection pooling
        
    Returns:
        The DiscordNotifier singleton instance
    """
    global _discord_notifier
    
    if _discord_notifier is None:
        _discord_notifier = DiscordNotifier(http_client=http_client)
    
    return _discord_notifier


# Backward compatibility: create instance on first access via property
# This allows existing code using `discord_notifier` to continue working
class _LazyDiscordNotifier:
    """Lazy proxy for backward compatibility with direct discord_notifier imports."""
    
    _instance: Optional[DiscordNotifier] = None
    
    def __getattr__(self, name):
        if self._instance is None:
            self._instance = get_discord_notifier()
        return getattr(self._instance, name)


discord_notifier = _LazyDiscordNotifier()

