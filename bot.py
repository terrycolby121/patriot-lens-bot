import os
import random
import json
import logging
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

import tweepy
from dotenv import load_dotenv
from news_fetcher import fetch_headlines, print_article
from composer import craft_tweet

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

# Grab credentials from environment variables so they can be provided in
# the .env file during local development.
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

POSTED_CACHE = "posted.json"
TOPICAL_TAGS = ["#Inflation", "#BorderCrisis", "#Election2024", "#Debt", "#Energy"]

def authenticate_twitter():
    """Create a Tweepy Client using OAuth1 user context."""
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True,
    )


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

def post_latest_tweets(api, count=1):
    """Fetch headlines and post ``count`` tweets chosen at random."""
    headlines = fetch_headlines()

    if not headlines:
        logger.info("No headlines returned")
        return

    cache = load_posted_cache()
    available = [h for h in headlines if not any(
        d["headline"] == h.get("title") for d in cache
    )]

    if not available:
        logger.info("No new headlines available after filtering cache")
        return

    for _ in range(min(count, len(available))):
        choice = random.choice(available)
        available.remove(choice)

        print_article(choice)

        headline = choice.get("title") if isinstance(choice, dict) else choice

        topical_tag = random.choice(TOPICAL_TAGS)
        tweet = craft_tweet(headline, topical_tag)
        logger.info("Tweet: %s", tweet)
        try:
            resp = api.create_tweet(text=tweet)
            tweet_id = resp.data.get("id") if hasattr(resp, "data") else None
            if tweet_id:
                logger.info("Posted tweet ID: %s", tweet_id)
            else:
                logger.info("Posted successfully")

            if random.random() < 0.2:
                follow_up = craft_tweet(headline, topical_tag)
                api.create_tweet(text=follow_up, in_reply_to_tweet_id=tweet_id)
                logger.info("Posted thread follow-up")

            cache.append({"headline": headline, "timestamp": datetime.now(UTC).isoformat()})
            save_posted_cache(cache)
        except Exception as e:
            logger.error("Error posting: %s", e)

if __name__ == "__main__":
    api = authenticate_twitter()
    post_latest_tweets(api)