import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
print("NEWS_API_KEY loaded?", bool(NEWS_API_KEY))
BASE_URL = "https://newsapi.org/v2/top-headlines"

def fetch_headlines(country="us", category="politics", page_size=5):
    params = {
        "apiKey": NEWS_API_KEY,
        "country": country,
        "category": category,
        "pageSize": page_size,
        "from": (datetime.now() - timedelta(hours=2)).isoformat()
    }
    print("Fetching from", BASE_URL)
    print("Params:", params)
    resp = requests.get(BASE_URL, params=params)
    print("Status:", resp.status_code)
    resp.raise_for_status()
    articles = [
        {
            "title": a.get("title"),
            "summary": a.get("description", "")
        }
        for a in resp.json()["articles"]
    ]
    print("Fetched", len(articles), "headlines")
    return articles