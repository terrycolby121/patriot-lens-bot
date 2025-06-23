from apscheduler.schedulers.blocking import BlockingScheduler
from bot import authenticate_twitter, post_latest_tweets
import pytz

# Small jitter so posts don't occur at the exact same minute every day
RANDOM_JITTER_SECONDS = 10 * 60  # up to 10 minutes

def schedule_jobs():
    api = authenticate_twitter()
    eastern = pytz.timezone("America/New_York")
    sched = BlockingScheduler(timezone=eastern)

    # Post at 08:00, 12:00 and 18:00 Eastern time each day
    for hour in (8, 12, 18):
        sched.add_job(
            post_latest_tweets,
            trigger="cron",
            hour=hour,
            minute=0,
            args=[api, 1],
            jitter=RANDOM_JITTER_SECONDS,
        )

    sched.start()

if __name__ == "__main__":
    schedule_jobs()