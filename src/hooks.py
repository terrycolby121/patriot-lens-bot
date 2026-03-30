"""Hook pattern library for engagement-optimised tweet openers.

Six named patterns rotate so the same opener never appears back-to-back.
The last-used pattern is read from the analytics DB to persist across
process restarts.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

HOOK_PATTERNS: dict[str, dict] = {
    "contrarian": {
        "openers": [
            "Unpopular opinion:",
            "Nobody wants to hear this but...",
            "Controversial take:",
            "Say it louder for the people in the back:",
        ],
        "description": "Lead with a contrarian position that challenges the mainstream narrative.",
    },
    "curiosity_gap": {
        "openers": [
            "Most people don't realize...",
            "The real reason...",
            "Here's what they're not telling you:",
            "Nobody's talking about this:",
        ],
        "description": "Create a gap between what readers think they know and the truth.",
    },
    "challenge": {
        "openers": [
            "If you still think",
            "Anyone still believing",
            "You haven't been paying attention if",
            "Wake up if you think",
        ],
        "description": "Directly challenge a belief or assumption the reader holds.",
    },
    "list_tease": {
        "openers": [
            "3 things nobody talks about:",
            "4 reasons this matters:",
            "5 facts they buried:",
            "3 things that changed how I see this:",
        ],
        "description": "Tease a numbered list delivered in the thread body.",
    },
    "debate_bait": {
        "openers": [
            "Hot take:",
            "Am I wrong or...",
            "Change my mind:",
            "Ratio me if I'm wrong:",
        ],
        "description": "Explicitly invite agreement or disagreement.",
    },
    "question_hook": {
        "openers": [
            "Why does nobody talk about",
            "Can someone explain why",
            "Why is it that",
            "How is it possible that",
        ],
        "description": "Open with a pointed question that implies a strong answer.",
    },
}


# ---------------------------------------------------------------------------
# State helpers (backed by analytics DB)
# ---------------------------------------------------------------------------

def get_last_hook_pattern() -> Optional[str]:
    """Return the hook_pattern used in the most recent post, or None."""
    try:
        from src.analytics import get_last_post
        row = get_last_post()
        if row:
            return row["hook_pattern"]
    except Exception:
        logger.debug("Could not read last hook pattern from DB", exc_info=True)
    return None


def pick_hook_pattern(exclude: Optional[str] = None) -> tuple[str, str]:
    """Choose a hook pattern (avoiding *exclude*) and return (pattern_name, opener_text)."""
    available = [k for k in HOOK_PATTERNS if k != exclude]
    if not available:
        available = list(HOOK_PATTERNS.keys())

    pattern = random.choice(available)
    opener = random.choice(HOOK_PATTERNS[pattern]["openers"])
    logger.debug("Hook selected: %s — %r", pattern, opener)
    return pattern, opener
