"""Breaking-take CLI for Patriot Lens Bot.

Manually fire a hot_take post outside the scheduled slots:

  python -m src.breaking_take
  python -m src.breaking_take --topic "border crisis"
  python -m src.breaking_take --dry-run

Pulls from NewsAPI, filters for US politics, picks the best unseen article,
generates a hook-injected hot_take, posts it, and logs to analytics.
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys

from dotenv import load_dotenv

# Setup must happen before other local imports
_repo_root = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root))

from src.log_setup import setup_logging  # noqa: E402

setup_logging()
load_dotenv()

from composer import TweetConfig, craft_tweet                          # noqa: E402
from news_fetcher import fetch_top_articles                            # noqa: E402
from src.analytics import log_post, get_daily_count, get_monthly_count, save_daily_checklist  # noqa: E402
from src.budget_tracker import can_post                                # noqa: E402
from src.hooks import get_last_hook_pattern, pick_hook_pattern         # noqa: E402
from src.post_thread import post_single_with_retry                     # noqa: E402
from src.post_tracker import was_posted, mark_posted                   # noqa: E402

# Reuse bot_auto's political filter and scorer
from bot_auto import _is_political, _score_article, _BEST_POOL_SIZE    # noqa: E402

logger = logging.getLogger(__name__)


def run(topic: str | None = None, dry_run: bool = False) -> None:
    """Fetch, compose, and post one breaking hot_take.

    Args:
        topic:   Optional keyword to bias NewsAPI query (e.g. "border crisis").
        dry_run: If True, compose but don't actually post.
    """
    if dry_run:
        os.environ["DRY_RUN"] = "1"

    # ---- Budget check -------------------------------------------------------
    ok, reason = can_post(units=1)
    if not ok:
        logger.error("Budget block: %s", reason)
        print(f"[breaking_take] Blocked: {reason}")
        return

    # ---- Article fetch ------------------------------------------------------
    arts = fetch_top_articles(limit=15, q=topic)
    if not arts:
        logger.error("No articles returned from NewsAPI")
        print("[breaking_take] No articles available.")
        return

    ranked: list[tuple[float, dict]] = []
    for article in arts:
        title = article.get("title") or ""
        if not title:
            continue
        if not _is_political(article):
            continue
        url = article.get("url") or ""
        if url and was_posted(url):
            continue
        ranked.append((_score_article(article), article))

    if not ranked:
        logger.error("No suitable unseen political articles found")
        print("[breaking_take] No new political articles available.")
        return

    ranked.sort(key=lambda x: x[0], reverse=True)
    best_pool = [a for _, a in ranked[:_BEST_POOL_SIZE]]
    chosen = random.choice(best_pool)

    title    = chosen["title"]
    url      = chosen.get("url") or ""
    summary  = chosen.get("summary") or ""

    # ---- Hook selection -----------------------------------------------------
    last_hook = get_last_hook_pattern()
    hook_pattern, hook_opener = pick_hook_pattern(exclude=last_hook)

    # ---- Compose ------------------------------------------------------------
    cfg = TweetConfig()
    text = craft_tweet(
        headline=title,
        summary=summary,
        config=cfg,
        tweet_format="hot_take",
        hook_opener=hook_opener,
    )

    print(f"\n[breaking_take] Article : {title}")
    print(f"[breaking_take] Hook    : {hook_pattern} — {hook_opener!r}")
    print(f"[breaking_take] Tweet   : {text}")
    print(f"[breaking_take] Chars   : {len(text)}")

    if dry_run:
        print("[breaking_take] DRY RUN — not posted.")
        return

    # ---- Post ---------------------------------------------------------------
    try:
        post_single_with_retry(text=text)
    except Exception as exc:
        logger.exception("Failed to post breaking take")
        print(f"[breaking_take] Error posting: {exc}")
        return

    # ---- Log ----------------------------------------------------------------
    log_post(
        content_type="hot_take",
        tweet_text=text,
        hook_pattern=hook_pattern,
        article_title=title,
        dry_run=False,
    )
    if url:
        mark_posted(url)
    try:
        save_daily_checklist(get_daily_count(), get_monthly_count())
    except Exception:
        pass

    print("[breaking_take] Posted successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fire a breaking hot_take post outside the scheduled slots."
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Optional keyword to bias NewsAPI query (e.g. 'border crisis')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compose tweet but do not post",
    )
    args = parser.parse_args()
    run(topic=args.topic, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
