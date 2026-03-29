"""APScheduler daemon for Patriot Lens Bot.

Default posting schedule (Eastern):
  07:00  single          — morning commute
  11:30  question_cta    — late morning
  13:00  single          — lunch
  17:30  question_cta    — end of workday
  21:00  numbered_thread — prime evening

Override posting times with the POSTING_TIMES env var (comma-separated HH:MM,
e.g. "07:00,11:30,13:00,17:30,21:00").  Format rotation adapts automatically:
the last slot is always numbered_thread; even-indexed slots are single;
odd-indexed slots are question_cta.

Only POST /2/tweets is used.  No Twitter read endpoints.
"""
from __future__ import annotations

import logging
import os

import pytz
from apscheduler.events import EVENT_SCHEDULER_STARTED
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from src.log_setup import setup_logging

setup_logging()
load_dotenv()

from bot_auto import post_scheduled_tweet  # noqa: E402

logger = logging.getLogger(__name__)

# Jitter keeps posts from landing at the exact same second every day,
# reducing the automation signal to Twitter's systems.
_JITTER_SECONDS = 10 * 60  # up to 10 minutes

# Default time slots and their tweet formats
_DEFAULT_SLOTS: list[tuple[str, str]] = [
    ("07:00", "single"),
    ("11:30", "question_cta"),
    ("13:00", "single"),
    ("17:30", "question_cta"),
    ("21:00", "numbered_thread"),
]


def _parse_posting_times(raw: str) -> list[tuple[str, str]]:
    """Parse POSTING_TIMES env var into [(HH:MM, format), ...].

    Format rotation:
      - Last slot  -> numbered_thread
      - Odd index  -> question_cta
      - Even index -> single
    """
    times = [t.strip() for t in raw.split(",") if t.strip()]
    if not times:
        return _DEFAULT_SLOTS

    result: list[tuple[str, str]] = []
    last_idx = len(times) - 1
    for i, t in enumerate(times):
        if i == last_idx:
            fmt = "numbered_thread"
        elif i % 2 == 1:
            fmt = "question_cta"
        else:
            fmt = "single"
        result.append((t, fmt))
    return result


def _resolve_slots() -> list[tuple[str, str]]:
    raw = os.getenv("POSTING_TIMES", "").strip()
    return _parse_posting_times(raw) if raw else _DEFAULT_SLOTS


def schedule_jobs() -> None:
    eastern = pytz.timezone("America/New_York")
    sched = BlockingScheduler(timezone=eastern)

    def _log_next_runs(event: object) -> None:  # noqa: ARG001
        for job in sched.get_jobs():
            logger.info("Job %s next run at %s", job.id, job.next_run_time)

    sched.add_listener(_log_next_runs, EVENT_SCHEDULER_STARTED)

    slots = _resolve_slots()
    logger.info("Scheduling %d daily posting slots (Eastern):", len(slots))
    for slot_time, slot_format in slots:
        try:
            hour_str, minute_str = slot_time.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except (ValueError, AttributeError):
            logger.error("Invalid time in POSTING_TIMES: %r — skipping", slot_time)
            continue

        job_id = f"tweet_{slot_time.replace(':', '')}_{slot_format}"
        # Wrap in a closure to capture the current format value
        def _make_job(fmt: str = slot_format):
            def _job() -> None:
                post_scheduled_tweet(tweet_format=fmt)
            return _job

        sched.add_job(
            _make_job(),
            trigger="cron",
            hour=hour,
            minute=minute,
            jitter=_JITTER_SECONDS,
            id=job_id,
        )
        logger.info("  %s Eastern — format=%s (id=%s)", slot_time, slot_format, job_id)

    sched.start()


if __name__ == "__main__":
    schedule_jobs()
