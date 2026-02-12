from __future__ import annotations
from pathlib import Path
from typing import List
import os, re, logging
from dotenv import load_dotenv

from src import make_card
from src import post_thread
import news_fetcher  # legacy headline fetcher
import composer

logger = logging.getLogger(__name__)

def summarize_to_bullets(summary: str, max_bullets: int = 3) -> List[str]:
    """Heuristic bulletizer that works offline.

    Split ``summary`` into sentences and keep up to ``max_bullets`` short lines.
    Each bullet is trimmed to ~100 chars.
    """
    if not summary:
        return []
    parts = re.split(r"(?<=[\.!?])\s+", summary.strip())
    bullets: List[str] = []
    for s in parts:
        s = s.strip()
        if not s:
            continue
        s = s.replace("\n", " ").strip()
        if len(s) > 100:
            s = s[:97].rstrip() + "…"
        s = s.rstrip(".!?")
        bullets.append(s)
        if len(bullets) >= max_bullets:
            break
    return bullets

def generate_card(headline: str, bullets: List[str], source_host: str, out_dir: Path) -> Path:
    """Render a branded image card and return the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", headline.lower())[:60]
    out_path = out_dir / f"{safe_name}.jpg"
    make_card.make_card(headline=headline, bullets=bullets, source=source_host, out_path=str(out_path))
    return out_path

def craft_alt_text(headline: str, bullets: List[str], source_host: str) -> str:
    """Create concise ALT text for the generated card."""
    bullets_txt = "; ".join(bullets[:3]) if bullets else "No bullets"
    alt = f"News card. Headline: {headline}. Bullets: {bullets_txt}. Source: {source_host}."
    return alt[:900]

def post_headline_with_card() -> None:
    """Fetch a headline, compose tweet text, render a card and post it."""
    load_dotenv()
    try:
        articles = news_fetcher.fetch_top_articles(limit=10)
    except Exception:
        logger.exception("Failed to fetch articles")
        return
    if not articles:
        logger.warning("No articles fetched; skipping.")
        return
    ranked = []
    for article in articles:
        headline = article.get("title") or ""
        summary = article.get("summary") or ""
        if not headline:
            continue
        score = len(summary) * 0.02
        if re.search(r"\d", headline):
            score += 0.6
        if len(headline) > 65:
            score += 0.4
        if len(headline.split()) >= 8:
            score += 0.3
        ranked.append((score, article))

    if not ranked:
        logger.warning("No valid articles after filtering; skipping.")
        return

    ranked.sort(key=lambda item: item[0], reverse=True)
    top_band = ranked[: min(4, len(ranked))]
    art = top_band[int.from_bytes(os.urandom(2), "big") % len(top_band)][1]
    headline = art.get("title") or ""
    url = art.get("url") or ""
    summary = art.get("summary") or ""
    source_host = (
        (art.get("source") or art.get("source_name") or "")
        .replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        or "news"
    )
    if not headline:
        logger.warning("Missing headline; skipping.")
        return
    logger.info("Fetched article: %s (%s)", headline, source_host)
    try:
        tweet_text = composer.craft_tweet(headline=headline, summary=summary, url=url)
    except Exception as e:  # pragma: no cover - network dependent
        logger.exception("composer.craft_tweet failed; falling back to headline only: %s", e)
        tweet_text = headline if len(headline) < 260 else (headline[:257] + "…")
    bullets = summarize_to_bullets(summary, max_bullets=3)
    logger.info("Generated %d bullet(s)", len(bullets))
    try:
        card_path = generate_card(headline=headline, bullets=bullets, source_host=source_host, out_dir=Path("media_cards"))
    except Exception:
        logger.exception("Card generation failed")
        return
    logger.info("Saved card to %s", card_path)
    alt_text = craft_alt_text(headline, bullets, source_host)
    try:
        post_thread.post_single(text=tweet_text, media_path=str(card_path), alt_text=alt_text)
        logger.info("Tweet posted%s", " [DRY RUN]" if os.getenv("DRY_RUN") == "1" else "")
    except Exception:
        logger.exception("Failed to post tweet")
