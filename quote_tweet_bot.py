import os
import re
import logging
import random

try:
    import tweepy
    from tweepy import OAuth1UserHandler
except ImportError as exc:  # pragma: no cover - helpful runtime check
    raise RuntimeError(
        "tweepy package is required. Install dependencies from requirements.txt"
    ) from exc
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


def find_high_engagement_tweet() -> tuple[str, str]:
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


def generate_quote(brand_voice: str) -> str:
    """Generate a concise, on-brand quote tweet."""
    system_prompt = (
        f"You are {brand_voice}, a serious, unapologetically edgy "
        "conservative commentator on Twitter. Your mission is to expose "
        "liberal bias and defend American values in one punchy tweet. Style: "
        "confident, declarative language. Respond with a single short "
        "statement and no hashtags."
        "Keep the entire response under 240 characters so additional hashtags "
        "can be appended later. Deliver only your sharp insight—no echoes of "
        "the original text."
    )
    messages = [{"role": "system", "content": system_prompt}]

    try:
        if _use_new_client:
            resp = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=60,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()

        resp = ai_client.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=60,
            temperature=0.7,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("OpenAI API error: %s", exc)
        raise


def quote_high_engagement_tweet() -> str:
    """Find a popular news tweet and post a quote tweet with commentary."""
    tweet_id, text = find_high_engagement_tweet()
    quote = generate_quote(brand_voice="Patriot Lens")
    final = append_hashtags(quote, text)
    return post_quote_with_image(final, "breaking_news.jpg", tweet_id)



def get_v1_api() -> tweepy.API:
    auth = OAuth1UserHandler(
        TWITTER_API_KEY,
        TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN,
        TWITTER_ACCESS_TOKEN_SECRET,
    )
    return tweepy.API(auth, wait_on_rate_limit=True)

def post_quote_with_image(
    quote: str, image_path: str, original_tweet_id: str
) -> str:
    """Post ``quote`` with ``image_path`` quoting ``original_tweet_id``."""
    # use v1.1 API for media upload
    api_v1 = get_v1_api()
    try:
        media = api_v1.media_upload(filename=image_path)
    except Exception as exc:
        logger.error("Error uploading media (v1): %s", exc)
        raise

    # use v2 Client for posting the tweet
    client_v2 = authenticate_twitter()
    try:
        resp = client_v2.create_tweet(
            text=quote,
            media_ids=[media.media_id],
            quote_tweet_id=original_tweet_id,
        )
    except Exception as exc:
        logger.error("Error posting tweet (v2): %s", exc)
        raise

    tweet_id = resp.data.get("id")
    if not tweet_id:
        raise RuntimeError("Failed to retrieve new tweet ID")
    return f"https://twitter.com/user/status/{tweet_id}"


if __name__ == "__main__":
    url = input("Please paste the URL of the Tweet to quote-tweet: ")
    try:
        tweet_id = extract_tweet_id(url)
        original_text = fetch_tweet_text(tweet_id)
        generated_quote = generate_quote(brand_voice="Patriot Lens")
        final_quote = append_hashtags(generated_quote, original_text)
        tweet_url = post_quote_with_image(
            final_quote, "breaking_news.jpg", tweet_id
        )
        print(f"Quote tweet posted: {tweet_url}")
    except Exception as exc:
        logger.error("Failed to post quote tweet: %s", exc)

