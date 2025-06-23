import os
import re
import logging
import requests

import tweepy

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


def post_quote_with_image(quote: str, image_path: str) -> str:
    """Post ``quote`` with the image at ``image_path``. Returns the tweet URL."""
    api = authenticate_twitter()

    try:
        media = api.media_upload(filename=image_path)
    except Exception as exc:
        logger.error("Error uploading media: %s", exc)
        raise

    try:
        resp = api.create_tweet(text=quote, media_ids=[media.media_id])
    except Exception as exc:
        logger.error("Error posting tweet: %s", exc)
        raise

    tweet_id = resp.data.get("id") if hasattr(resp, "data") else None
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

