import requests
from datetime import datetime, timedelta
import os
import logging
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
logger = logging.getLogger(__name__)
logger.info("NEWS_API_KEY loaded? %s", bool(NEWS_API_KEY))
BASE_URL = "https://newsapi.org/v2/top-headlines"


def fetch_top_articles(limit: int = 1, country: str = "us", category: str = "politics"):
    """Return a list of top articles with ``title``, ``url``, ``summary`` and ``source``.

    The result length is capped by ``limit``. When ``NEWS_API_KEY`` is missing,
    an empty list is returned.
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
    logger.info("Fetching from %s", BASE_URL)
    logger.info("Params: %s", params)
    resp = requests.get(BASE_URL, params=params)
    logger.info("Status: %s", resp.status_code)
    try:
        resp.raise_for_status()
    except Exception:
        logger.exception("News API request failed")
        return []
    raw = resp.json().get("articles", [])
    articles = [
        {
            "title": a.get("title"),
            "url": a.get("url"),
            "summary": a.get("description") or "",
            "source": (a.get("source") or {}).get("name"),
        }
        for a in raw
    ]
    articles = articles[:limit]
    logger.info("Fetched %s articles", len(articles))
    for art in articles:
        logger.info("- %s | %s", art.get("title"), art.get("source"))
    return articles


def fetch_headlines(country="us", category="politics", page_size=5):
    """Backward compatible wrapper around :func:`fetch_top_articles`."""
    return [
        {"title": a["title"], "summary": a["summary"]}
        for a in fetch_top_articles(limit=page_size, country=country, category=category)
    ]


def print_article(article):
    """Print the headline and summary of a chosen article."""
    if not article:
        return
    title = article.get("title") if isinstance(article, dict) else str(article)
    summary = article.get("summary", "") if isinstance(article, dict) else ""
    logger.info("Selected article: %s", title)
    if summary:
        logger.info("Summary: %s", summary)
