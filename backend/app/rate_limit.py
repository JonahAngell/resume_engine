"""Per-user limits on AI calls.

State lives in this process: the app runs as a single worker (see Dockerfile), so a
restart resets the counters and nothing is shared between processes.
"""

import os
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from .identity import CurrentUser, resolve_current_user

MINUTE = 60.0
DAY = 86400.0


def _limit(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "") or default))
    except ValueError:
        return default


class AiRateLimiter:
    def __init__(self) -> None:
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._calls.clear()

    def check(self, user_key: str, now: float | None = None) -> None:
        """Record one AI call for `user_key`, or raise 429 when a limit is reached."""
        per_minute = _limit("AI_RATE_PER_MINUTE", 20)
        per_day = _limit("AI_DAILY_LIMIT", 300)
        now = time.monotonic() if now is None else now
        calls = self._calls[user_key]
        while calls and now - calls[0] >= DAY:
            calls.popleft()
        recent = sum(1 for stamp in calls if now - stamp < MINUTE)
        if per_day and len(calls) >= per_day:
            retry = int(DAY - (now - calls[0])) + 1
            raise HTTPException(429, "Daily AI limit reached. Try again tomorrow.", headers={"Retry-After": str(retry)})
        if per_minute and recent >= per_minute:
            oldest = next(stamp for stamp in calls if now - stamp < MINUTE)
            retry = int(MINUTE - (now - oldest)) + 1
            raise HTTPException(429, "Too many AI requests. Wait a moment and try again.", headers={"Retry-After": str(retry)})
        calls.append(now)


limiter = AiRateLimiter()


async def ai_rate_limit(identity: CurrentUser = Depends(resolve_current_user)) -> None:
    limiter.check(identity.external_id)
