"""Utilities for posting tweets with matching sarcastic images."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from composer import TweetConfig, craft_tweet, _use_new_client, client as _oa_client
from .post_thread import post_single

IMAGE_MODEL = "gpt-image-1"  # default image model
IMAGE_SIZE = "1024x1024"


def _generate_image(prompt: str, out_path: str, model: str = IMAGE_MODEL, size: str = IMAGE_SIZE) -> str:
    """Generate an image via OpenAI and save to ``out_path``.

    Visuals dramatically boost engagement; matching tone keeps the feed cohesive.
    """
    if _use_new_client:
        resp = _oa_client.images.generate(model=model, prompt=prompt, size=size)
        b64 = resp.data[0].b64_json
    else:  # pragma: no cover - legacy client
        resp = _oa_client.Image.create(model=model, prompt=prompt, size=size)
        b64 = resp["data"][0]["b64_json"]

    Path(out_path).write_bytes(base64.b64decode(b64))
    return out_path


def post_tweet_with_image(headline: str, summary: str, config: TweetConfig) -> Optional[str]:
    """Create a tweet and matching sarcastic image, then post them together.

    Steps:
        1. Craft tweet text with GPT-4o for sharper hooks and voice consistency.
        2. Render a bold political-cartoon style image reinforcing the tweet's punchline.
        3. Upload the image via Twitter's media endpoint.
        4. Post the tweet with the image attached for 2–3× higher engagement.
    """
    # Step 1: craft tweet text
    text = craft_tweet(headline, summary, config=config)

    # Step 2: generate on-brand image
    prompt = (
        f"Sarcastic political cartoon style image matching this tweet: {text}. "
        "Bold, edgy, slightly humorous tone. Clear, eye-catching, suitable for social media."
    )
    img_path = _generate_image(prompt, "tweet_image.png")

    # Step 3 & 4: upload and post
    tweet_id = post_single(text=text, media_path=img_path, alt_text=text)
    return tweet_id
