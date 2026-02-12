# Patriot Lens Bot

A small Twitter/X bot that runs on a Raspberry Pi. It supports an automatic
headline pipeline that fetches the latest news and posts text-only tweets on a
schedule. Designed for the free tier: only write endpoints are used.

## Quick start

```bash
git clone <INSERT_GITHUB_REPO_URL>
cd patriot-lens-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
```

Run the queue once (dry run by default if no real keys are set):

```bash
DRY_RUN=1 python -m src.post_queue
```

## Scheduled headline posts

The scheduler combines the headline fetcher and composer. By default it posts
text-only tweets at
08:00, 12:00, 18:00, 20:00 and 22:00 Eastern.

You can trigger a single run manually:

```bash
python -c "from src.pipeline_auto_card import post_headline_with_card as p; p()"
```


Or use a small helper class:

```python
from src.on_demand import OnDemandTweeter

OnDemandTweeter().post()
```

Make sure `NEWS_API_KEY` and the Twitter keys are configured in `.env`. Use
`DRY_RUN=1` to log actions without posting.

## Composing tweets

Use `composer.py` to craft on-brand copy from a headline and bullets:

```python
from composer import craft_tweet

text = craft_tweet(
    headline="Demo headline",
    summary="First point. Second point. Third point.",
)
print(text)
```

Set `OPENAI_API_KEY` in your `.env` for the composer to work.

## Queue format

`queue.csv` columns:

- `datetime_utc` – ISO timestamp in UTC
- `type` – `single`, `thread`, or `quote`
- `content` – depends on type

Examples:

| type   | content example |
|--------|-----------------|
| single | `Hello world -> media_cards/example.jpg|ALT:Example alt text` |
| thread | `threads/demo_thread.txt` |
| quote  | `https://twitter.com/jack/status/20|Interesting perspective` |

## Cron on Raspberry Pi

Add a cron entry:

```
*/5 * * * * cd /home/pi/patriot-lens-bot && /usr/bin/python3 -m src.post_queue >> logs.txt 2>&1
```

## Free tier notes

The following endpoint is used for text-only posting:

- `POST /2/tweets`

Do **not** automate restricted/read endpoints such as timelines, search, or trends.

## Accessibility

If you later re-enable media posting, include ALT text for image attachments.
