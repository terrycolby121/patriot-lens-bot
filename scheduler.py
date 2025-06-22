from apscheduler.schedulers.blocking import BlockingScheduler
from bot import authenticate_twitter, post_latest_tweets

def schedule_jobs():
    api = authenticate_twitter()
    sched = BlockingScheduler(timezone="UTC")

    # Example: Post 3 tweets every weekday at 12:00 UTC (8 AM ET)
    sched.add_job(
        post_latest_tweets,
        trigger="cron",
        day_of_week="mon-fri",
        hour=12,
        minute=0,
        args=[api, 3]
    )

    # Example: Single tweet at 19:00 UTC (3 PM ET) with count=1
    sched.add_job(
        post_latest_tweets,
        trigger="cron",
        day_of_week="mon-fri",
        hour=19,
        minute=0,
        args=[api, 1]
    )

    sched.start()

if __name__ == "__main__":
    schedule_jobs()
