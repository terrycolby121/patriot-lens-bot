from __future__ import annotations

"""On-demand headline tweeting using the scheduler's pipeline."""

import logging

from dotenv import load_dotenv

from bot_auto import post_scheduled_tweet

logger = logging.getLogger(__name__)


class OnDemandTweeter:
    """Trigger the scheduled headline pipeline manually."""

    def __init__(self) -> None:
        """Load environment variables for consistency."""
        load_dotenv()

    def post(self) -> None:
        """Create a tweet immediately using the scheduler logic."""
        logger.info("Posting headline on demand")
        post_scheduled_tweet()


if __name__ == "__main__":  # pragma: no cover - manual convenience
    OnDemandTweeter().post()
