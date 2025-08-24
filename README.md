# Patriot Lens Bot

A small Twitter/X bot that runs on a Raspberry Pi. It now supports an automatic
headline pipeline that fetches the latest news, generates branded image cards
and posts them on a schedule. Designed for the free tier: only write endpoints
are used.

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

## Scheduled headline posts

The legacy scheduler now combines the headline fetcher, composer and image card
generator. By default it posts a tweet with text and an image card at
08:00, 12:00, 18:00, 20:00 and 22:00 Eastern.

Set `AUTO_CARD_ENABLED=0` in your environment to fall back to text-only posts.

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
