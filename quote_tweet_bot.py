import os
import re
import logging

import tweepy
from tweepy import OAuth1UserHandler

try:
    from openai import OpenAI
    _use_new_client = True
except ImportError:
    import openai
    _use_new_client = False

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


def generate_quote(brand_voice: str) -> str:
    """Generate a concise, on-brand quote tweet."""
    system_prompt = (
        f"You are the social media voice of {brand_voice}: quick, factual, bold. "
        "Craft a short reaction to quote-tweet a breaking update without repeating the original text."
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
        generated_quote = generate_quote(brand_voice="Patriot Lens")
        tweet_url = post_quote_with_image(
            generated_quote, "breaking_news.jpg", tweet_id
        )
        print(f"Quote tweet posted: {tweet_url}")
    except Exception as exc:
        logger.error("Failed to post quote tweet: %s", exc)

