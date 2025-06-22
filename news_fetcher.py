import requests
from datetime import datetime, timedelta
import os

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BASE_URL = "https://newsapi.org/v2/top-headlines"

def fetch_headlines(country="us", category="politics", page_size=5):
    params = {
        "apiKey": NEWS_API_KEY,
        "country": country,
        "category": category,
        "pageSize": page_size,
        "from": (datetime.now() - timedelta(hours=2)).isoformat()
    }
    resp = requests.get(BASE_URL, params=params)
    resp.raise_for_status()
    return [a["title"] for a in resp.json()["articles"]]
