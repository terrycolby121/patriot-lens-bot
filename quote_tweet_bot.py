import os
import re
import logging
import random
import time
from typing import List, Tuple

import tweepy
from tweepy import OAuth1UserHandler
from composer import infer_tag


try:
    from openai import OpenAI
    _use_new_client = True
except ImportError:
    try:
        import openai
        _use_new_client = False
    except ImportError as exc:  # pragma: no cover - helpful runtime check
        raise RuntimeError(
            "openai package is required. Install dependencies from requirements.txt"
        ) from exc

from dotenv import load_dotenv

load_dotenv()

# Load credentials from environment variables
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if _use_new_client:
    ai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    openai.api_key = OPENAI_API_KEY
    ai_client = openai

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Common high-engagement hashtags for conservative audiences
HIGH_VALUE_TAGS = ["#tcot", "#AmericaFirst", "#RedWave2026", "#SaveAmerica"]

# Keywords that signal a topic is politically charged or socially controversial
CONTROVERSIAL_KEYWORDS = [
    "politic",
    "election",
    "government",
    "policy",
    "president",
    "trump",
    "biden",
    "abortion",
    "immigration",
    "climate",
    "war",
    "protest",
    "rights",
    "supreme court",
    "scandal",
    "ban",
]

# WOEID 1 == Worldwide trending topics
TREND_WOEID = 1


# Major news accounts to monitor for high-engagement tweets. Each of these
# typically has well over one million followers.
NEWS_ACCOUNTS = [
    "AP",
    "Reuters",
    "FoxNews",
    "cnn",
    "nytimes",
    "washingtonpost",
    "BBCWorld",
]



def authenticate_twitter() -> tweepy.Client:
    """Authenticate with Twitter and return a Tweepy Client."""
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        bearer_token=TWITTER_BEARER_TOKEN,
        wait_on_rate_limit=True,
    )


def extract_tweet_id(url: str) -> str:
    """Return the tweet ID parsed from ``url``."""
    logger.info("Parsing tweet ID from %s", url)
    match = re.search(r"/status/(\d+)", url)
    if not match:
        raise ValueError("Invalid Tweet URL")
    return match.group(1)


def fetch_tweet_text(tweet_id: str) -> str:
    """Return the text of the tweet with ``tweet_id``."""
    client = authenticate_twitter()
    try:
        resp = client.get_tweet(tweet_id, tweet_fields=["text"])
        if resp and resp.data:
            return resp.data.get("text", "") or ""
    except Exception as exc:
        logger.error("Error fetching original tweet text: %s", exc)
    return ""


def append_hashtags(quote: str, context: str) -> str:
    """Attach high-value and topical hashtags to ``quote``."""
    topical_tag = infer_tag(context)
    primary_tag = random.choice(HIGH_VALUE_TAGS)
    hashtags = f"{primary_tag} {topical_tag}"
    avail_len = 280 - len(hashtags) - 1  # space before hashtags
    quote = quote[:avail_len].strip()
    return f"{quote} {hashtags}".strip()


def get_trending_topics(limit: int = 10) -> List[str]:
    """Return a list of currently trending topic names."""
    api = get_v1_api()
    try:
        trends = api.get_place_trends(TREND_WOEID)
        trend_list = trends[0]["trends"] if trends else []
    except Exception as exc:
        # Many accounts (including those with only Essential access) cannot
        # call the trends endpoint.  In that case we simply return an empty
        # list so the caller can fall back to another strategy instead of
        # raising an exception here.
        logger.warning("Trending topics unavailable: %s", exc)
        return []
    names = [t["name"] for t in trend_list[:limit]]
    return names


def find_high_engagement_tweet() -> Tuple[str, str]:
    """Return the tweet ID and text of the most engaged recent post."""
    client = authenticate_twitter()
    best_tweet = None
    best_score = -1
    for handle in NEWS_ACCOUNTS:
        try:
            user_resp = client.get_user(
                username=handle, user_fields=["public_metrics"]
            )
            user = user_resp.data
            if not user:
                continue
            if user.public_metrics.get("followers_count", 0) < 1_000_000:
                continue
            tweets_resp = client.get_users_tweets(
                user.id,
                max_results=5,
                tweet_fields=["public_metrics", "text"],
            )
            if not tweets_resp or not tweets_resp.data:
                continue
            for tweet in tweets_resp.data:
                metrics = tweet.public_metrics or {}
                score = (
                    metrics.get("like_count", 0)
                    + metrics.get("retweet_count", 0)
                    + metrics.get("reply_count", 0)
                    + metrics.get("quote_count", 0)
                )
                if score > best_score:
                    best_score = score
                    best_tweet = tweet
        except Exception as exc:
            logger.error("Error scanning %s: %s", handle, exc)
    if not best_tweet:
        raise RuntimeError("No suitable tweet found")
    return str(best_tweet.id), best_tweet.text


def find_controversial_trending_tweet() -> Tuple[str, str]:
    """Return tweet ID and text for an engaging tweet on a trending topic."""
    client = authenticate_twitter()
    topics = get_trending_topics()
    if not topics:
        raise RuntimeError("Trending topics unavailable")
    best_tweet = None
    best_score = -1
    for topic in topics:
        if not any(k in topic.lower() for k in CONTROVERSIAL_KEYWORDS):
            continue
        try:
            resp = client.search_recent_tweets(
                query=f"{topic} -is:retweet",
                max_results=10,
                tweet_fields=["public_metrics", "text"],
            )
        except Exception as exc:
            logger.error("Search failed for %s: %s", topic, exc)
            continue
        if not resp or not resp.data:
            continue
        for tweet in resp.data:
            metrics = tweet.public_metrics or {}
            score = (
                metrics.get("like_count", 0)
                + metrics.get("retweet_count", 0)
                + metrics.get("reply_count", 0)
                + metrics.get("quote_count", 0)
            )
            if score > best_score:
                best_score = score
                best_tweet = tweet
    if not best_tweet:
        raise RuntimeError("No controversial trending tweet found")
    return str(best_tweet.id), best_tweet.text


def sanitize_quote(text: str) -> str:
    """Clean up AI-sounding phrasing and disallowed punctuation."""
    text = text.replace("—", "-")
    patterns = [
        r"(?i)as an ai[^.?!]*[.?!]?",
        r"(?i)i(?: am|'m) an ai[^.?!]*[.?!]?",
        r"(?i)as a language model[^.?!]*[.?!]?",
    ]
    for pat in patterns:
        text = re.sub(pat, "", text)
    return text.strip()

def generate_quote(original_text: str, brand_voice: str) -> str:
    """Generate a concise, on-brand quote tweet summarising ``original_text``."""
    system_prompt = (
        f"You are {brand_voice}, a serious, unapologetically edgy conservative "
        "commentator on Twitter. Your mission is to expose liberal bias and "
        "defend American values in one punchy tweet. Style: confident, "
        "declarative language. Respond with a single short statement and no "
        "hashtags. Keep under 240 characters so hashtags can be appended. "
        "Use natural language, avoid generic filler or disclaimers, and do not "
        "use the em dash."
    )
    user_prompt = (
        "Original tweet: "
        f"\n{original_text}\n\n"
        "Write a quote tweet. First, briefly summarise the key point of the "
        "original in your own words. Then add a sharp, witty opinion that fits "
        "the persona. Avoid repeating the tweet verbatim, avoid hashtags, and "
        "stay conversational."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        if _use_new_client:
            resp = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=80,
                temperature=0.7,
            )
            quote = resp.choices[0].message.content.strip()
            return sanitize_quote(quote)

        resp = ai_client.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=80,
            temperature=0.7,
        )
        quote = resp["choices"][0]["message"]["content"].strip()
        return sanitize_quote(quote)
    except Exception as exc:
        logger.error("OpenAI API error: %s", exc)
        raise


def quote_high_engagement_tweet() -> str:
    """Find a popular news tweet and post a quote tweet with commentary."""
    tweet_id, text = find_high_engagement_tweet()
    quote = generate_quote(text, brand_voice="Patriot Lens")
    final = append_hashtags(quote, text)
    return post_quote_tweet(final, tweet_id)


def quote_trending_tweet() -> str:
    """Quote tweet a controversial trending topic.

    If trending data is not available (e.g. the account lacks access to the
    trends endpoint) we gracefully fall back to quoting a high-engagement news
    tweet instead of raising an error.
    """
    try:
        tweet_id, text = find_controversial_trending_tweet()
        quote = generate_quote(text, brand_voice="Patriot Lens")
        final = append_hashtags(quote, text)
        return post_quote_tweet(final, tweet_id)
    except Exception as exc:
        logger.warning("Falling back to high-engagement tweet: %s", exc)
        return quote_high_engagement_tweet()



def get_v1_api() -> tweepy.API:
    auth = OAuth1UserHandler(
        TWITTER_API_KEY,
        TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN,
        TWITTER_ACCESS_TOKEN_SECRET,
    )
    return tweepy.API(auth, wait_on_rate_limit=True)

def post_quote_tweet(quote: str, original_tweet_id: str) -> str:
    """Post ``quote`` quoting ``original_tweet_id`` without media."""
    client_v2 = authenticate_twitter()
    try:
        resp = client_v2.create_tweet(text=quote, quote_tweet_id=original_tweet_id)
    except Exception as exc:
        logger.error("Error posting tweet (v2): %s", exc)
        raise

    tweet_id = resp.data.get("id")
    if not tweet_id:
        raise RuntimeError("Failed to retrieve new tweet ID")
    return f"https://twitter.com/user/status/{tweet_id}"


def monitor_trending_topics(interval: int = 900):
    """Continuously monitor trending topics and post quote tweets."""
    while True:
        try:
            quote_trending_tweet()
        except Exception as exc:
            logger.error("Monitor loop error: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Patriot Lens quote tweet bot")
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Continuously monitor trending topics and quote tweet",
    )
    args = parser.parse_args()

    if args.monitor:
        monitor_trending_topics()
    else:
        try:
            url = quote_trending_tweet()
            print(f"Quote tweet posted: {url}")
        except Exception as exc:
            logger.error("Failed to post quote tweet: %s", exc)

