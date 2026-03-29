"""NewsAPI integration — fetch top US political headlines.

All functions are READ from a third-party API (NewsAPI), not from Twitter.
No Twitter read endpoints are used anywhere in this module.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
logger = logging.getLogger(__name__)
logger.info("NEWS_API_KEY loaded? %s", bool(NEWS_API_KEY))

BASE_URL = "https://newsapi.org/v2/top-headlines"


def fetch_top_articles(
    limit: int = 1,
    country: str = "us",
    category: str = "politics",
) -> list[dict]:
    """Return a list of top articles with title, url, summary, source, and published_at.

    The result is capped at *limit* entries. Returns an empty list when
    NEWS_API_KEY is absent or the request fails.
    """
    if not NEWS_API_KEY:
        logger.warning("NEWS_API_KEY not set; cannot fetch headlines")
        return []

    params = {
        "apiKey": NEWS_API_KEY,
        "country": country,
        "category": category,
        "pageSize": max(1, limit),
        "from": (datetime.now() - timedelta(hours=2)).isoformat(),
    }

    safe_params = {k: ("***" if k == "apiKey" else v) for k, v in params.items()}
    logger.info("Fetching from %s  params=%s", BASE_URL, safe_params)

    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
    except Exception:
        logger.exception("NewsAPI request failed")
        return []

    raw = resp.json().get("articles", [])
    articles = [
        {
            "title": a.get("title"),
            "url": a.get("url"),
            "summary": a.get("description") or "",
            "source": (a.get("source") or {}).get("name"),
            # ISO 8601 publish timestamp — used for recency scoring in bot_auto.py
            "published_at": a.get("publishedAt"),
        }
        for a in raw
    ]
    articles = articles[:limit]

    logger.info("Fetched %d articles", len(articles))
    for art in articles:
        logger.info("  - %s | %s | published=%s", art["title"], art["source"], art["published_at"])

    return articles


def fetch_headlines(
    country: str = "us",
    category: str = "politics",
    page_size: int = 20,
) -> list[dict]:
    """Backward-compatible wrapper — returns title and summary only."""
    return [
        {"title": a["title"], "summary": a["summary"]}
        for a in fetch_top_articles(limit=page_size, country=country, category=category)
    ]


def print_article(article: dict) -> None:
    """Log the headline and summary of a chosen article."""
    if not article:
        return
    title = article.get("title") if isinstance(article, dict) else str(article)
    summary = article.get("summary", "") if isinstance(article, dict) else ""
    logger.info("Selected article: %s", title)
    if summary:
        logger.info("  Summary: %s", summary)
