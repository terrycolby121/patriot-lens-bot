import requests
from datetime import datetime, timedelta
import os

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BASE_URL = "https://newsapi.org/v2/everything"

def fetch_headlines(query="politics", page_size=5):
    params = {
        "apiKey": NEWS_API_KEY,
        "q": query,
        "pageSize": page_size,
        "sortBy": "publishedAt",
        "from": (datetime.now() - timedelta(hours=2)).isoformat(),
        "language": "en",
    }
    resp = requests.get(BASE_URL, params=params)
    resp.raise_for_status()
    return [a["title"] for a in resp.json()["articles"]]
