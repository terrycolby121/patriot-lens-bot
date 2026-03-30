"""APScheduler daemon for Patriot Lens Bot.

17 daily posting slots (Eastern) — content_router decides format per slot:

  07:00  08:00  08:55  09:50  11:00  12:05  13:00  14:00  15:00
  16:00  17:05  18:00  18:55  19:55  20:50  21:45  22:40

Override posting times with the POSTING_TIMES env var (comma-separated HH:MM,
e.g. "07:00,09:00,12:00").  Content type is always determined by content_router
at post time — no per-slot format assignment.

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

# Jitter: 5–15 minutes in seconds (avoids automation fingerprint)
_JITTER_SECONDS = 10 * 60  # up to 10 min jitter around each slot

# 17 slots spread across the day (Eastern).
# Gaps are intentionally uneven to avoid a mechanical pattern.
_DEFAULT_SLOTS: list[str] = [
    "07:00",
    "08:00",
    "08:55",
    "09:50",
    "11:00",
    "12:05",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:05",
    "18:00",
    "18:55",
    "19:55",
    "20:50",
    "21:45",
    "22:40",
]


def _resolve_slots() -> list[str]:
    raw = os.getenv("POSTING_TIMES", "").strip()
    if raw:
        slots = [t.strip() for t in raw.split(",") if t.strip()]
        return slots if slots else _DEFAULT_SLOTS
    return _DEFAULT_SLOTS


def schedule_jobs() -> None:
    eastern = pytz.timezone("America/New_York")
    sched = BlockingScheduler(timezone=eastern)

    def _log_next_runs(event: object) -> None:  # noqa: ARG001
        for job in sched.get_jobs():
            logger.info("Job %s next run at %s", job.id, job.next_run_time)

    sched.add_listener(_log_next_runs, EVENT_SCHEDULER_STARTED)

    slots = _resolve_slots()
    logger.info("Scheduling %d daily posting slots (Eastern):", len(slots))
    for slot_time in slots:
        try:
            hour_str, minute_str = slot_time.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except (ValueError, AttributeError):
            logger.error("Invalid time in POSTING_TIMES: %r — skipping", slot_time)
            continue

        job_id = f"tweet_{slot_time.replace(':', '')}"

        sched.add_job(
            post_scheduled_tweet,
            trigger="cron",
            hour=hour,
            minute=minute,
            jitter=_JITTER_SECONDS,
            id=job_id,
        )
        logger.info("  %s Eastern (id=%s)", slot_time, job_id)

    sched.start()


if __name__ == "__main__":
    schedule_jobs()
