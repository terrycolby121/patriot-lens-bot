import os
import logging
import random
from dotenv import load_dotenv
from composer import craft_tweet
from news_fetcher import fetch_top_articles
from src.pipeline_auto_card import post_headline_with_card
from src.post_thread import post_single

logger = logging.getLogger(__name__)

load_dotenv()

AUTO_CARD = os.getenv("AUTO_CARD_ENABLED", "1") == "1"


def post_scheduled_tweet() -> None:
    """Post a scheduled tweet using either the card pipeline or text-only path."""
    if AUTO_CARD:
        logger.info("AUTO_CARD_ENABLED=1; using card pipeline")
        post_headline_with_card()
        return
    logger.info("AUTO_CARD_ENABLED=0; posting text-only headline")
    arts = fetch_top_articles(limit=10)
    if not arts:
        logger.warning("No articles fetched; skipping")
        return
    ranked = []
    for article in arts:
        title = article.get("title") or ""
        summary = article.get("summary") or ""
        if not title:
            continue
        score = len(summary) * 0.02
        if len(title) > 70:
            score += 0.4
        if any(ch.isdigit() for ch in title):
            score += 0.5
        ranked.append((score, article))
    if not ranked:
        logger.warning("No valid articles after filtering; skipping")
        return
    ranked.sort(key=lambda item: item[0], reverse=True)
    best_pool = [a for _, a in ranked[: min(4, len(ranked))]]
    a = random.choice(best_pool)
    try:
        text = craft_tweet(headline=a["title"], url=a.get("url", ""), summary=a.get("summary", ""))
    except Exception as e:  # pragma: no cover - network dependent
        logger.exception("craft_tweet failed; falling back to headline only: %s", e)
        text = a["title"][:280]
    post_single(text=text)
