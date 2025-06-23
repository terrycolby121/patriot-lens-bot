from apscheduler.events import EVENT_SCHEDULER_STARTED
from apscheduler.schedulers.blocking import BlockingScheduler
from bot import authenticate_twitter, post_latest_tweets
import logging
import pytz

# Small jitter so posts don't occur at the exact same minute every day
RANDOM_JITTER_SECONDS = 10 * 60  # up to 10 minutes

logger = logging.getLogger(__name__)

def schedule_jobs():
    api = authenticate_twitter()
    eastern = pytz.timezone("America/New_York")
    sched = BlockingScheduler(timezone=eastern)

    def log_next_runs(event):
        for job in sched.get_jobs():
            logger.info("Job %s next run at %s", job.id, job.next_run_time)

    sched.add_listener(log_next_runs, EVENT_SCHEDULER_STARTED)

    # Post at 08:00, 12:00 and 18:00 Eastern time each day
    for hour in (8, 12, 18):
        sched.add_job(
            post_latest_tweets,
            trigger="cron",
            hour=hour,
            minute=0,
            args=[api, 1],
            jitter=RANDOM_JITTER_SECONDS,
            id=f"tweet_{hour}",
        )

    sched.start()

if __name__ == "__main__":
    schedule_jobs()
