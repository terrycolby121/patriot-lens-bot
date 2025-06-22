import os
from dotenv import load_dotenv

load_dotenv()

import tweepy
from news_fetcher import fetch_headlines
from composer import craft_tweet

TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

def authenticate_twitter():
    auth = tweepy.OAuth1UserHandler(
        TWITTER_API_KEY, TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
    )
    return tweepy.API(auth, wait_on_rate_limit=True)

def post_latest_tweets(api, count=3):
    headlines = fetch_headlines()
    for title in headlines[:count]:
        tweet = craft_tweet(title)
        try:
            api.update_status(tweet)
            print("Posted:", tweet)
        except Exception as e:
            print("Error posting:", e)

if __name__ == "__main__":
    api = authenticate_twitter()
    post_latest_tweets(api)