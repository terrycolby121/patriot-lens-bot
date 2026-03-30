"""Daily and monthly post budget enforcement.

Hard limits (free-tier API):
  DAILY_POST_LIMIT   = 17  (override via env var)
  MONTHLY_POST_LIMIT = 500 (override via env var)

In DRY_RUN mode every check passes so tests never block.
"""
from __future__ import annotations

import logging
import os

from src.analytics import (
    get_daily_count,
    get_monthly_count,
    DAILY_LIMIT as _DEFAULT_DAILY,
    MONTHLY_LIMIT as _DEFAULT_MONTHLY,
)

logger = logging.getLogger(__name__)

DAILY_LIMIT: int = int(os.getenv("DAILY_POST_LIMIT", str(_DEFAULT_DAILY)))
MONTHLY_LIMIT: int = int(os.getenv("MONTHLY_POST_LIMIT", str(_DEFAULT_MONTHLY)))

_DAILY_WARN_AT: int = DAILY_LIMIT - 4    # warn when 4 posts remain
_MONTHLY_WARN_AT: int = MONTHLY_LIMIT - 50


def remaining_today() -> int:
    return max(0, DAILY_LIMIT - get_daily_count())


def remaining_month() -> int:
    return max(0, MONTHLY_LIMIT - get_monthly_count())


def can_post(units: int = 1) -> tuple[bool, str]:
    """Return (True, "") when posting *units* tweets is within budget.

    Returns (False, reason) when the budget would be exceeded.
    Always returns True in DRY_RUN mode so smoke tests never abort.
    """
    if os.getenv("DRY_RUN") == "1":
        return True, ""

    daily = get_daily_count()
    monthly = get_monthly_count()

    if daily + units > DAILY_LIMIT:
        reason = f"daily limit reached ({daily}/{DAILY_LIMIT})"
        logger.warning("Budget block: %s", reason)
        return False, reason

    if monthly + units > MONTHLY_LIMIT:
        reason = f"monthly limit reached ({monthly}/{MONTHLY_LIMIT})"
        logger.warning("Budget block: %s", reason)
        return False, reason

    # Warnings (log only — don't block)
    if daily + units >= _DAILY_WARN_AT:
        logger.warning(
            "Approaching daily limit: %d/%d used (%d remaining)",
            daily + units, DAILY_LIMIT, DAILY_LIMIT - daily - units,
        )
    if monthly + units >= _MONTHLY_WARN_AT:
        logger.warning(
            "Approaching monthly limit: %d/%d used (%d remaining)",
            monthly + units, MONTHLY_LIMIT, MONTHLY_LIMIT - monthly - units,
        )

    return True, ""
