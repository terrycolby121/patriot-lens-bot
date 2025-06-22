import os
import random
import tweepy
from dotenv import load_dotenv
from news_fetcher import fetch_headlines, print_article
from composer import craft_tweet

load_dotenv()

# Grab credentials from environment variables so they can be provided in
# the .env file during local development.
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

def authenticate_twitter():
    """Create a Tweepy Client using OAuth1 user context."""
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True,
    )

def post_latest_tweets(api, count=1):
    """Fetch headlines and post ``count`` tweets chosen at random."""
    headlines = fetch_headlines()

    if not headlines:
        print("No headlines returned")
        return

    for _ in range(count):
        choice = random.choice(headlines)

        # Print the chosen article's information via news_fetcher helper
        print_article(choice)

        # Each item from fetch_headlines is a dict with a title key
        headline = choice.get("title") if isinstance(choice, dict) else choice

        tweet = craft_tweet(headline)
        print("Tweet:", tweet)
        try:
            api.create_tweet(text=tweet)
            print("Posted successfully")
        except Exception as e:
            print("Error posting:", e)

if __name__ == "__main__":
    api = authenticate_twitter()
    post_latest_tweets(api)