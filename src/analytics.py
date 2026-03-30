"""SQLite-backed post log, daily checklist, and weekly review template.

All analytics are local — no read endpoints used. Provides the offline
visibility layer since we can't read Twitter data via the free-tier API.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _REPO_ROOT / "bot.db"

DAILY_LIMIT = 17
MONTHLY_LIMIT = 500


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@contextmanager
def _db() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the posts table if it doesn't exist."""
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                posted_at        TEXT    NOT NULL,
                content_type     TEXT    NOT NULL,
                hook_pattern     TEXT,
                tweet_text       TEXT    NOT NULL,
                char_count       INTEGER,
                thread_id        TEXT,
                thread_position  INTEGER,
                article_title    TEXT,
                dry_run          INTEGER DEFAULT 0
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_posted_at ON posts (posted_at)"
        )


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def log_post(
    content_type: str,
    tweet_text: str,
    hook_pattern: Optional[str] = None,
    thread_id: Optional[str] = None,
    thread_position: Optional[int] = None,
    article_title: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """Insert one post record. Returns the new row id."""
    init_db()
    with _db() as conn:
        cur = conn.execute(
            """INSERT INTO posts
               (posted_at, content_type, hook_pattern, tweet_text, char_count,
                thread_id, thread_position, article_title, dry_run)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                content_type,
                hook_pattern,
                tweet_text,
                len(tweet_text),
                thread_id,
                thread_position,
                article_title,
                1 if dry_run else 0,
            ),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_daily_count(include_dry_run: bool = False) -> int:
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    dry_clause = "" if include_dry_run else "AND dry_run = 0"
    with _db() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM posts WHERE posted_at > ? {dry_clause}",
            (cutoff,),
        ).fetchone()
    return row[0]


def get_monthly_count(include_dry_run: bool = False) -> int:
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    dry_clause = "" if include_dry_run else "AND dry_run = 0"
    with _db() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM posts WHERE posted_at > ? {dry_clause}",
            (cutoff,),
        ).fetchone()
    return row[0]


def get_today_type_counts(include_dry_run: bool = False) -> dict[str, int]:
    """Return {content_type: count} for the last 24 hours."""
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    dry_clause = "" if include_dry_run else "AND dry_run = 0"
    with _db() as conn:
        rows = conn.execute(
            f"""SELECT content_type, COUNT(*) as cnt FROM posts
                WHERE posted_at > ? {dry_clause}
                GROUP BY content_type""",
            (cutoff,),
        ).fetchall()
    return {r["content_type"]: r["cnt"] for r in rows}


def get_last_post() -> Optional[sqlite3.Row]:
    """Return the most recent post row, or None."""
    init_db()
    with _db() as conn:
        return conn.execute(
            "SELECT * FROM posts ORDER BY posted_at DESC LIMIT 1"
        ).fetchone()


def get_today_thread_count(include_dry_run: bool = False) -> int:
    """Number of distinct threads started in the last 24 hours."""
    init_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    dry_clause = "" if include_dry_run else "AND dry_run = 0"
    with _db() as conn:
        row = conn.execute(
            f"""SELECT COUNT(DISTINCT thread_id) FROM posts
                WHERE posted_at > ? AND thread_id IS NOT NULL {dry_clause}""",
            (cutoff,),
        ).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------

def generate_daily_checklist(daily_count: int, monthly_count: int) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    remaining_day = max(0, DAILY_LIMIT - daily_count)
    remaining_month = max(0, MONTHLY_LIMIT - monthly_count)
    return f"""DAILY ENGAGEMENT CHECKLIST — {today}
====================================================
[ ] Check replies on today's posts — reply to top 5
[ ] Like replies from repeat engagers
[ ] Find 3 high-visibility tweets in your niche and reply manually
[ ] Follow 5-10 accounts that engaged with us today
[ ] Pin best-performing tweet of the week (check X Analytics)

BUDGET STATUS
  Today  : {daily_count:>3}/{DAILY_LIMIT}  ({remaining_day} remaining)
  Month  : {monthly_count:>3}/{MONTHLY_LIMIT} ({remaining_month} remaining)
====================================================
"""


def save_daily_checklist(daily_count: int, monthly_count: int) -> Path:
    """Write the checklist to checklist_YYYY-MM-DD.txt. Returns the path."""
    today = datetime.now().strftime("%Y-%m-%d")
    path = _REPO_ROOT / f"checklist_{today}.txt"
    path.write_text(generate_daily_checklist(daily_count, monthly_count), encoding="utf-8")
    logger.debug("Daily checklist saved: %s", path)
    return path


# ---------------------------------------------------------------------------
# Weekly review template (printed to console)
# ---------------------------------------------------------------------------

WEEKLY_REVIEW_TEMPLATE = """
====================================================
WEEKLY PERFORMANCE REVIEW — fill in from X Analytics
====================================================
Period: [start date] to [end date]

TOP POSTS (from X Analytics > Top Tweets)
1. [tweet text] — [impressions] impressions, [engagements] engagements
2. [tweet text] — [impressions] impressions, [engagements] engagements
3. [tweet text] — [impressions] impressions, [engagements] engagements

METRICS SUMMARY
  New followers this week : ___
  Profile visits          : ___
  Total impressions       : ___
  Avg engagement rate     : ___%

CONTENT TYPE BREAKDOWN (fill from X Analytics > Content)
  Hot takes   : ___ posts, avg ___ impressions
  Questions   : ___ posts, avg ___ impressions
  Threads     : ___ posts, avg ___ impressions
  Engagement  : ___ posts, avg ___ impressions

WHAT WORKED    : [describe top-performing hook pattern or topic]
WHAT DIDN'T    : [describe lowest performers]
ADJUST NEXT WK : [e.g. more threads, fewer questions, different timing]
====================================================
"""


def print_weekly_review_template() -> None:
    print(WEEKLY_REVIEW_TEMPLATE)
