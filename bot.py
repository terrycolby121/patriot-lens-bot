import json
import logging
import random
from datetime import datetime, timedelta

try:
    from datetime import timezone
    UTC = timezone.utc
except Exception:  # Python <3.2 fallback
    from datetime import tzinfo

    class _UTC(tzinfo):
        def utcoffset(self, dt):
            return timedelta(0)

        def tzname(self, dt):
            return "UTC"

        def dst(self, dt):
            return timedelta(0)

    UTC = _UTC()

from dotenv import load_dotenv
from news_fetcher import fetch_headlines, print_article
from composer import TweetConfig
from src.pipeline_with_image import post_tweet_with_image

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

POSTED_CACHE = "posted.json"


def load_posted_cache():
    try:
        with open(POSTED_CACHE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    filtered = []
    for d in data:
        ts = datetime.fromisoformat(d["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts > cutoff:
            filtered.append(d)
    return filtered


def save_posted_cache(data):
    with open(POSTED_CACHE, "w") as f:
        json.dump(data[-50:], f)

def post_latest_tweets(count: int = 1) -> None:
    """Fetch headlines and post ``count`` tweets chosen at random."""
    # Fetch a larger pool of articles to give the bot more variety when
    # picking topics for tweets.
    headlines = fetch_headlines(page_size=20)

    if not headlines:
        logger.info("No headlines returned")
        return

    cache = load_posted_cache()
    available = [h for h in headlines if not any(
        d.get("headline") == h.get("title") for d in cache
    )]

    if not available:
        logger.info("No new headlines available after filtering cache")
        return

    for _ in range(min(count, len(available))):
        choice = random.choice(available)
        available.remove(choice)

        print_article(choice)

        headline = choice.get("title") if isinstance(choice, dict) else choice
        summary = choice.get("summary", "") if isinstance(choice, dict) else ""

        try:
            tweet_id = post_tweet_with_image(headline, summary, TweetConfig())
            logger.info("Posted tweet ID: %s", tweet_id)

            cache.append({
                "type": "headline",
                "headline": headline,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            save_posted_cache(cache)
        except Exception as e:
            logger.error("Error posting: %s", e)


def post_scheduled_tweet() -> None:
    """Post a single headline tweet."""
    post_latest_tweets(1)


if __name__ == "__main__":
    post_scheduled_tweet()
