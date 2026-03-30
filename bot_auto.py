"""Automated headline-tweet pipeline.

Called by scheduler.py for every time-slot post.  Each call:
  1. Checks budget (daily / monthly hard caps).
  2. Decides content type via content_router (hot_take, question_poll, thread, engagement_bait).
  3. Picks a hook pattern (anti-repeat).
  4. Fetches + filters + scores the latest political headlines.
  5. Crafts copy and posts via the retry-wrapped Twitter client.
  6. Logs to SQLite analytics and saves daily checklist.
  7. Records the posted URL to prevent repeat posting.

Zero Twitter read endpoints are used.  Only POST /2/tweets.
"""
from __future__ import annotations

import logging
import os
import random
import re
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.log_setup import setup_logging

setup_logging()
load_dotenv()

from composer import TweetConfig, craft_tweet, craft_full_thread   # noqa: E402
from news_fetcher import fetch_top_articles                        # noqa: E402
from src.analytics import log_post, get_daily_count, get_monthly_count, save_daily_checklist  # noqa: E402
from src.budget_tracker import can_post, remaining_today           # noqa: E402
from src.content_router import decide_content_type                 # noqa: E402
from src.hooks import get_last_hook_pattern, pick_hook_pattern     # noqa: E402
from src.post_thread import post_single_with_retry                 # noqa: E402
from src.post_tracker import was_posted, mark_posted               # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring signals
# ---------------------------------------------------------------------------

_URGENCY_WORDS = frozenset(
    {"breaking", "just in", "confirmed", "alert", "massive", "unprecedented"}
)
_HEDGE_WORDS = frozenset({"may", "could", "might", "report says"})

_BEST_POOL_SIZE = 3   # tighter selection = higher average quality

# Tier 1: unambiguously US-political — pass immediately
_STRONG_US_POLITICAL = frozenset({
    "trump", "biden", "harris", "pelosi", "schumer", "mcconnell",
    "congress", "senate", "white house", "supreme court", "pentagon",
    "republican", "democrat", "gop", "maga", "america first",
    "executive order", "veto", "filibuster", "impeach", "electoral",
    "second amendment", "tariff", "doge", "fbi", "doj", "cia", "nsa",
    "border patrol", "ice agent", "daca", "obamacare",
})

# Tier 2: generic political terms — only pass when paired with a US location signal
_GENERAL_POLITICAL = frozenset({
    "protest", "rally", "election", "vote", "legislation", "government",
    "policy", "border", "immigration", "military", "spending", "budget",
    "tax", "inflation", "economy", "debt", "deficit", "gun control",
    "trade", "china", "iran", "ukraine", "israel", "nato",
    "poll", "approval", "resign", "indictment", "federal",
})

# US location signals used to validate tier-2 matches
_US_LOCATION_RE = re.compile(
    r"\bamerican[s]?\b|\bunited states\b|\bu\.s\.\b"
    r"|\bthe us\b|\bacross the us\b|\bin the us\b"
    r"|\bwashington\b|\bwhite house\b",
    re.IGNORECASE,
)


def _is_political(article: dict) -> bool:
    """Return True only for US-relevant political articles."""
    text = ((article.get("title") or "") + " " + (article.get("summary") or "")).lower()
    # Tier 1: strong US-specific keyword → immediate pass
    if any(kw in text for kw in _STRONG_US_POLITICAL):
        return True
    # Tier 2: generic political word + explicit US location reference → pass
    if any(kw in text for kw in _GENERAL_POLITICAL):
        return bool(_US_LOCATION_RE.search(text))
    return False


def _score_article(article: dict) -> float:
    """Score an article for engagement potential."""
    title = (article.get("title") or "").lower()
    summary = article.get("summary") or ""
    score = 0.0

    # Base signals
    score += len(summary) * 0.02
    if len(title) > 70:
        score += 0.4
    if any(ch.isdigit() for ch in title):
        score += 0.5

    # Urgency boost
    for word in _URGENCY_WORDS:
        if word in title:
            score += 1.5
            break

    # Recency boost: published within the last 2 hours
    published_at = article.get("published_at")
    if published_at:
        try:
            pub_time = datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            )
            if pub_time.tzinfo is None:
                pub_time = pub_time.replace(tzinfo=timezone.utc)
            age_hours = (
                datetime.now(timezone.utc) - pub_time
            ).total_seconds() / 3600
            if age_hours <= 2:
                score += 1.0
        except Exception:
            pass

    # Hedging language penalty
    for word in _HEDGE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", title):
            score -= 0.5

    return score


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _pick_article(limit: int = 10) -> dict | None:
    """Fetch, filter, score, and return the best unseen article, or None."""
    arts = fetch_top_articles(limit=limit)
    if not arts:
        logger.warning("No articles fetched")
        return None

    ranked: list[tuple[float, dict]] = []
    for article in arts:
        title = article.get("title") or ""
        if not title:
            continue
        if not _is_political(article):
            logger.info("Skipping off-topic: %s", title)
            continue
        url = article.get("url") or ""
        if url and was_posted(url):
            logger.info("Skipping duplicate: %s", title)
            continue
        ranked.append((_score_article(article), article))

    if not ranked:
        logger.warning("No new articles after deduplication")
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_pool = [a for _, a in ranked[:_BEST_POOL_SIZE]]
    return random.choice(best_pool)


def post_scheduled_tweet() -> None:
    """Fetch, score, compose, and post one tweet.

    Content type is determined by content_router based on time-of-day,
    daily ratio targets, anti-repeat rules, and remaining budget.
    """
    dry_run = os.getenv("DRY_RUN") == "1"

    # ---- Budget check -------------------------------------------------------
    budget_left = remaining_today()
    ok, reason = can_post(units=1)
    if not ok:
        logger.warning("Skipping slot: %s", reason)
        return

    # ---- Decide content type ------------------------------------------------
    content_type, thread_length = decide_content_type(budget_remaining=budget_left)

    # Thread needs at least (thread_length + 1) budget units
    if content_type == "thread":
        needed = thread_length + 1
        ok, reason = can_post(units=needed)
        if not ok:
            logger.warning("Downgrading thread to hot_take: %s", reason)
            content_type = "hot_take"
            thread_length = 1

    # ---- Hook selection -----------------------------------------------------
    last_hook = get_last_hook_pattern()
    hook_pattern, hook_opener = pick_hook_pattern(exclude=last_hook)

    logger.info(
        "Starting scheduled post: type=%s thread_len=%d hook=%s dry_run=%s",
        content_type, thread_length, hook_pattern, dry_run,
    )

    # ---- Article selection --------------------------------------------------
    chosen = _pick_article()
    if not chosen:
        logger.warning("No suitable article found; skipping slot")
        return

    title    = chosen["title"]
    url      = chosen.get("url") or ""
    summary  = chosen.get("summary") or ""
    cfg = TweetConfig()

    logger.info("Selected article: %s", title)

    # ---- Compose and post ---------------------------------------------------
    try:
        if content_type == "thread":
            tweets = craft_full_thread(
                headline=title,
                summary=summary,
                thread_length=thread_length,
                config=cfg,
                hook_pattern=hook_pattern,
                hook_opener=hook_opener,
            )
            thread_id = str(uuid.uuid4())
            prev_tweet_id: str | None = None
            for pos, tweet_text in enumerate(tweets, start=1):
                tweet_id = post_single_with_retry(
                    text=tweet_text,
                    in_reply_to_tweet_id=prev_tweet_id,
                )
                log_post(
                    content_type="thread",
                    tweet_text=tweet_text,
                    hook_pattern=hook_pattern if pos == 1 else None,
                    thread_id=thread_id,
                    thread_position=pos,
                    article_title=title,
                    dry_run=dry_run,
                )
                prev_tweet_id = tweet_id if (tweet_id and tweet_id != "0") else None
            logger.info("Posted %d-tweet thread for: %s", len(tweets), title)

        else:
            # Map content type to tweet_format for craft_tweet
            fmt_map = {
                "hot_take":        "hot_take",
                "question_poll":   "question_poll",
                "engagement_bait": "engagement_bait",
            }
            tweet_format = fmt_map.get(content_type, "single")
            text = craft_tweet(
                headline=title,
                summary=summary,
                tweet_format=tweet_format,
                config=cfg,
                hook_opener=hook_opener if content_type == "hot_take" else "",
            )
            post_single_with_retry(text=text)
            log_post(
                content_type=content_type,
                tweet_text=text,
                hook_pattern=hook_pattern,
                article_title=title,
                dry_run=dry_run,
            )
            logger.info("Posted %s (%d chars): %s", content_type, len(text), title)

    except Exception:
        logger.exception("post_scheduled_tweet failed for article: %s", title)
        return

    # ---- Post-success bookkeeping -------------------------------------------
    if url:
        mark_posted(url)

    try:
        save_daily_checklist(get_daily_count(), get_monthly_count())
    except Exception:
        logger.debug("Could not save daily checklist", exc_info=True)


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    post_scheduled_tweet()
