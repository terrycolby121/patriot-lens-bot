import os
import re
import logging
import requests

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


def get_tweet_text(url: str) -> str:
    """Fetch the text of the tweet identified by ``url``."""
    logger.info("Fetching tweet text from %s", url)
    match = re.search(r"/status/(\d+)", url)
    if not match:
        raise ValueError("Invalid Tweet URL")
    tweet_id = match.group(1)

    api = authenticate_twitter()
    try:
        resp = api.get_tweet(tweet_id, tweet_fields=["text"])
    except Exception as exc:
        logger.error("Error fetching tweet: %s", exc)
        raise

    if not hasattr(resp, "data") or not resp.data:
        raise ValueError("Tweet not found")
    return resp.data.get("text", "")


def generate_quote(text: str, brand_voice: str) -> str:
    """Generate a concise quote tweet responding to ``text``."""
    system_prompt = (
        f"You are the social media voice of {brand_voice}: quick, factual, bold. "
        f"Quote-tweet this breaking update: {text}"
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

def post_quote_with_image(quote: str, image_path: str) -> str:
    """Post ``quote`` with the image at ``image_path``. Returns the tweet URL."""
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
        resp = client_v2.create_tweet(text=quote, media_ids=[media.media_id])
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
        original_text = get_tweet_text(url)
        generated_quote = generate_quote(original_text, brand_voice="Patriot Lens")
        tweet_url = post_quote_with_image(generated_quote, "breaking_news.jpg")
        print(f"Quote tweet posted: {tweet_url}")
    except Exception as exc:
        logger.error("Failed to post quote tweet: %s", exc)

