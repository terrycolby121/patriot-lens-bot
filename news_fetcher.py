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

def fetch_headlines(country="us", category="politics", page_size=5):
    params = {
        "apiKey": NEWS_API_KEY,
        "country": country,
        "category": category,
        "pageSize": page_size,
        "from": (datetime.now() - timedelta(hours=2)).isoformat()
    }
    logger.info("Fetching from %s", BASE_URL)
    logger.info("Params: %s", params)
    resp = requests.get(BASE_URL, params=params)
    logger.info("Status: %s", resp.status_code)
    resp.raise_for_status()
    articles = [
        {
            "title": a.get("title"),
            "summary": a.get("description", "")
        }
        for a in resp.json()["articles"]
    ]
    logger.info("Fetched %s headlines", len(articles))
    for art in articles:
        logger.info("- %s | %s", art["title"], art["summary"])
    return articles


def print_article(article):
    """Print the headline and summary of a chosen article."""
    if not article:
        return
    title = article.get("title") if isinstance(article, dict) else str(article)
    summary = article.get("summary", "") if isinstance(article, dict) else ""
    logger.info("Selected article: %s", title)
    if summary:
        logger.info("Summary: %s", summary)
