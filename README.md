# Patriot Lens Bot

A Twitter/X automation bot designed for Raspberry Pi (or any Linux system).
Fetches US political headlines, crafts engagement-optimised copy via OpenAI,
and posts on a daily schedule — strictly within Twitter's **free tier**
(only `POST /2/tweets` is used; zero read endpoints).

---

## Quick start

```bash
git clone <INSERT_GITHUB_REPO_URL>
cd patriot-lens-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

Smoke-test without posting anything real:

```bash
DRY_RUN=1 python bot_auto.py
```

---

## Posting schedule

The scheduler posts five times per day at **peak engagement windows** for
political/news content (Eastern time):

| Time (ET) | Format          | Why                        |
|-----------|-----------------|----------------------------|
| 7:00 AM   | single          | Morning commute scroll     |
| 11:30 AM  | question_cta    | Late morning engagement    |
| 1:00 PM   | single          | Lunch break browsing       |
| 5:30 PM   | question_cta    | End-of-workday wind-down   |
| 9:00 PM   | numbered_thread | Prime evening prime time   |

All slots carry up to **10 minutes of random jitter** so posts never land at
the exact same second every day.

### Customising the schedule

Override with the `POSTING_TIMES` env var (comma-separated `HH:MM` in Eastern):

```bash
POSTING_TIMES=06:30,12:00,20:00 python scheduler.py
```

Format rotation is automatic regardless of how many slots you configure:
- **Last slot** → `numbered_thread`
- **Odd-indexed slots** → `question_cta`
- **Even-indexed slots** → `single`

---

## Tweet formats

| Format            | Description                                                          |
|-------------------|----------------------------------------------------------------------|
| `single`          | One standalone tweet; bold statement or `BREAKING:` prefix when the headline contains urgency words |
| `question_cta`    | Tweet ending with "Agree or disagree?" or "What do you think?" to drive replies |
| `numbered_thread` | 2-tweet thread — tweet 1 is a punchy hook, tweet 2 adds 3-4 sentences of context |

---

## Running the scheduler

```bash
python scheduler.py
```

For a single on-demand post:

```bash
python -c "from bot_auto import post_scheduled_tweet; post_scheduled_tweet()"
# or with a specific format:
python -c "from bot_auto import post_scheduled_tweet; post_scheduled_tweet('question_cta')"
```

Or use the helper class:

```bash
python src/on_demand.py
```

---

## Queue-based posting

`queue.csv` lets you pre-schedule one-off posts.  Columns:

| Column        | Description                                               |
|---------------|-----------------------------------------------------------|
| `datetime_utc`| ISO timestamp in UTC                                      |
| `type`        | `single`, `thread`, or `quote`                            |
| `content`     | See examples below                                        |

Examples:

| type   | content                                                            |
|--------|--------------------------------------------------------------------|
| single | `Hello world -> media_cards/example.jpg\|ALT:Example alt text`    |
| thread | `threads/demo_thread.txt`                                          |
| quote  | `https://twitter.com/jack/status/20\|Interesting perspective`      |

Run the queue processor:

```bash
python -m src.post_queue
```

---

## Composing tweets manually

```python
from composer import craft_tweet, craft_thread_pair, TweetConfig

cfg = TweetConfig(max_hashtags=2, allow_hashtags=True)

# Single tweet
print(craft_tweet("Senate passes $2T spending bill", tweet_format="single", config=cfg))

# Question CTA
print(craft_tweet("Gas prices hit 5-year high", tweet_format="question_cta", config=cfg))

# 2-tweet thread
hook, context = craft_thread_pair("Fed raises rates again", config=cfg)
print(hook)
print(context)
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in your values.

| Variable                     | Required | Default                  | Description                                                    |
|------------------------------|----------|--------------------------|----------------------------------------------------------------|
| `TW_CONSUMER_KEY`            | Yes      | —                        | Twitter/X API consumer key                                     |
| `TW_CONSUMER_SECRET`         | Yes      | —                        | Twitter/X API consumer secret                                  |
| `TW_ACCESS_TOKEN`            | Yes      | —                        | Twitter/X access token                                         |
| `TW_ACCESS_SECRET`           | Yes      | —                        | Twitter/X access token secret                                  |
| `OPENAI_API_KEY`             | Yes      | —                        | OpenAI API key for tweet generation                            |
| `NEWS_API_KEY`               | Yes      | —                        | NewsAPI key                                                    |
| `POSTING_TIMES`              | No       | `07:00,11:30,13:00,17:30,21:00` | Comma-separated HH:MM posting times (Eastern)         |
| `LOG_LEVEL`                  | No       | `INFO`                   | `DEBUG` / `INFO` / `WARNING` / `ERROR`                         |
| `MAX_RETRY_ATTEMPTS`         | No       | `3`                      | Twitter API retry attempts (delays: 2s, 4s, 8s)               |
| `DRY_RUN`                    | No       | —                        | Set to `1` to log without posting                              |
| `OPENAI_TWEET_MODEL`         | No       | `gpt-5-mini`             | Primary OpenAI model for tweet generation                      |
| `OPENAI_TWEET_MODEL_FALLBACKS`| No      | `gpt-4o,gpt-4.1-mini`   | Comma-separated fallback models                                |

---

## Logging

Structured JSON logs are written to `logs/bot.log` (rotating, max 1 MB, 3 backups)
and human-readable lines to stderr.

Each post attempt records:

```json
{
  "timestamp": "2026-03-29T21:00:12.345678",
  "level": "INFO",
  "logger": "bot_auto",
  "message": "Posted tweet",
  "article_title": "Senate passes ...",
  "tweet_chars": 214,
  "format_type": "single",
  "dry_run": false
}
```

---

## Resilience

- **Exponential backoff retry**: every Twitter API call is retried up to
  `MAX_RETRY_ATTEMPTS` times with 2 s / 4 s / 8 s delays before giving up.
- **failed_queue.csv**: tweets that exhaust all retries are written here for
  manual review and reposting.
- **Deduplication**: `posted_ids.json` (capped at 500 entries) prevents the
  same article URL from being tweeted twice.

---

## Article scoring

Articles are ranked by engagement potential before selection:

| Signal                             | Score delta |
|------------------------------------|-------------|
| Long summary (rich context)        | +0.02 per char |
| Title length > 70 chars            | +0.4        |
| Title contains a number            | +0.5        |
| Urgency word in title (breaking, confirmed, alert, …) | +1.5 |
| Published within the last 2 hours  | +1.0        |
| Hedging language (may, could, might, …) | -0.5 each |

The top 3 scoring articles form a pool; one is chosen at random to add variety
across repeated runs at similar scores.

---

## Cron on Raspberry Pi

```cron
*/5 * * * * cd /home/pi/patriot-lens-bot && /usr/bin/python3 -m src.post_queue >> /dev/null 2>&1
```

Or run the scheduler as a background service:

```bash
nohup python scheduler.py &
```

---

## Free tier compliance

Only `POST /2/tweets` (v2 API) is called.  The following endpoints are
**never used** anywhere in this codebase:

- No timeline reads
- No search endpoints
- No trend lookups
- No user lookups
- No v1.1 endpoints

If you re-enable media posting, include `alt_text` for image attachments.
