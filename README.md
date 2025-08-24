# Patriot Lens Bot

A small Twitter/X bot that runs on a Raspberry Pi. It generates branded image cards and posts tweets from a simple CSV queue. Designed for the free tier: only write endpoints are used.

## Quick start

```bash
git clone <INSERT_GITHUB_REPO_URL>
cd patriot-lens-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
```

Generate a demo image card:

```bash
python -m src.make_card
```

Run the queue once (dry run by default if no real keys are set):

```bash
DRY_RUN=1 python -m src.post_queue
```

## `make_card.py`

```python
from src.make_card import make_card
make_card(
    headline="Example Headline",
    bullets=["One", "Two", "Three"],
    source="example.com",
    out_path="media_cards/example.jpg",
)
```

## Composing tweets

Use `composer.py` to craft on-brand copy from a headline and bullets, then
generate a matching card and post it in one step:

```python
from src.post_thread import post_composed_single

post_composed_single(
    headline="Demo headline",
    bullets=["First point", "Second point", "Third point"],
    source="example.com",
    out_path="media_cards/demo.jpg",
)
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

Only the following endpoints are used:

- `POST /2/tweets`
- `POST /1.1/media/upload`
- `POST /1.1/media/metadata/create`

Do **not** automate restricted/read endpoints such as timelines, search, or trends.

## Accessibility

Always provide ALT text for images. The queue format includes `ALT:` for single tweets with media.
