import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BASE_URL = "https://newsapi.org/v2/top-headlines"

def fetch_headlines(country: str = "us", category: str = "politics",
                    page_size: int = 5, timeout: int = 5):
    """Fetch recent news headlines from the NewsAPI.

    Args:
        country: ISO 3166 country code to filter by.
        category: News category to query.
        page_size: Number of articles to return.
        timeout: Optional request timeout in seconds.

    Returns:
        A list of article titles.

    Raises:
        EnvironmentError: If ``NEWS_API_KEY`` is not set.
        ValueError: If the API response does not contain ``articles``.
        HTTPError: Propagated if the request fails.
    """

    if not NEWS_API_KEY:
        raise EnvironmentError("NEWS_API_KEY environment variable is not set")

    params = {
        "apiKey": NEWS_API_KEY,
        "country": country,
        "category": category,
        "pageSize": page_size,
        "from": (datetime.now() - timedelta(hours=2)).isoformat(),
    }

    resp = requests.get(BASE_URL, params=params, timeout=timeout)
    resp.raise_for_status()

    data = resp.json()
    if "articles" not in data:
        raise ValueError("Invalid response from NewsAPI: 'articles' missing")

    return [a["title"] for a in data.get("articles", [])]
