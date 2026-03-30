"""Content type and format router.

Decides what to post next based on:
  - Time of day (peak vs off-peak windows)
  - Today's content-type distribution (ratio enforcement)
  - Anti-repeat rule (no back-to-back same type)
  - Thread cap (max 2 threads/day)
  - Remaining budget (downgrade thread if budget too low)

Peak windows (Eastern):
  Weekday : 8-10 AM, 12-1 PM, 5-7 PM
  Weekend : 9-11 AM, 1-3 PM, 7-9 PM
"""
from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

# Target ratio for each content type across a full day
CONTENT_RATIOS: dict[str, float] = {
    "hot_take":       0.30,
    "question_poll":  0.25,
    "thread":         0.25,
    "engagement_bait": 0.20,
}

# Thread body tweet count range (CTA is always appended, so total = length + 1)
THREAD_LENGTH_RANGE: tuple[int, int] = (3, 5)

# Max threads per 24-hour window
MAX_THREADS_PER_DAY = 2

# Peak windows: list of (start_hour_inclusive, end_hour_exclusive) in Eastern
_PEAK_WEEKDAY = [(8, 10), (12, 13), (17, 19)]
_PEAK_WEEKEND = [(9, 11), (13, 15), (19, 21)]

# Content preferred during each period
_PEAK_PREFERRED    = ["thread", "hot_take"]
_OFFPEAK_PREFERRED = ["question_poll", "engagement_bait"]

_EASTERN = pytz.timezone("America/New_York")


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _is_peak(dt: Optional[datetime] = None) -> bool:
    now_et = (dt or datetime.now()).astimezone(_EASTERN)
    hour = now_et.hour
    is_weekend = now_et.weekday() >= 5
    windows = _PEAK_WEEKEND if is_weekend else _PEAK_WEEKDAY
    return any(start <= hour < end for start, end in windows)


# ---------------------------------------------------------------------------
# DB-backed state queries
# ---------------------------------------------------------------------------

def _today_type_counts() -> dict[str, int]:
    try:
        from src.analytics import get_today_type_counts
        return get_today_type_counts()
    except Exception:
        logger.debug("Could not read type counts from DB", exc_info=True)
        return {}


def _last_content_type() -> Optional[str]:
    try:
        from src.analytics import get_last_post
        row = get_last_post()
        return row["content_type"] if row else None
    except Exception:
        return None


def _today_thread_count() -> int:
    try:
        from src.analytics import get_today_thread_count
        return get_today_thread_count()
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def decide_content_type(budget_remaining: int) -> tuple[str, int]:
    """Return (content_type, thread_length) for the next post.

    thread_length is the number of *body* tweets (CTA not counted).
    For non-thread types thread_length is always 1.
    """
    peak = _is_peak()
    counts = _today_type_counts()
    total_today = sum(counts.values())
    last_type = _last_content_type()
    threads_today = _today_thread_count()

    # Build weighted candidate pool
    candidates: list[str] = []
    preferred = _PEAK_PREFERRED if peak else _OFFPEAK_PREFERRED
    fallback  = _OFFPEAK_PREFERRED if peak else _PEAK_PREFERRED

    for ctype in preferred + fallback:
        if ctype not in candidates:
            candidates.append(ctype)

    # Ratio correction: double-weight anything that's under its target
    if total_today > 0:
        for ctype, target in CONTENT_RATIOS.items():
            actual = counts.get(ctype, 0) / total_today
            if actual < target - 0.10 and ctype in candidates:
                candidates.append(ctype)  # extra weight

    # Remove thread if we've hit the daily cap
    if threads_today >= MAX_THREADS_PER_DAY:
        candidates = [c for c in candidates if c != "thread"]

    # Remove thread if budget can't cover even the minimum thread
    min_thread_posts = THREAD_LENGTH_RANGE[0] + 1  # body + CTA
    if budget_remaining < min_thread_posts:
        candidates = [c for c in candidates if c != "thread"]

    # Anti-repeat: avoid same type as last post (if alternatives exist)
    if last_type and last_type in candidates and len(set(candidates)) > 1:
        candidates = [c for c in candidates if c != last_type]

    if not candidates:
        candidates = ["hot_take"]  # ultimate fallback

    content_type = random.choice(candidates)

    # Determine thread length
    if content_type == "thread":
        max_body = min(THREAD_LENGTH_RANGE[1], budget_remaining - 1)
        min_body = THREAD_LENGTH_RANGE[0]
        if max_body < min_body:
            # Not enough budget — downgrade silently
            logger.info(
                "Budget too low for thread (%d remaining); downgrading to hot_take",
                budget_remaining,
            )
            content_type = "hot_take"
            thread_length = 1
        else:
            thread_length = random.randint(min_body, max_body)
    else:
        thread_length = 1

    logger.info(
        "Content router: type=%s thread_length=%d peak=%s budget_remaining=%d",
        content_type, thread_length, peak, budget_remaining,
    )
    return content_type, thread_length
