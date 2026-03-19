from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str, limit: int) -> RateLimitResult:
        now = monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            queue = self._hits.setdefault(key, deque())
            while queue and queue[0] <= cutoff:
                queue.popleft()

            if len(queue) >= limit:
                retry_after = max(1, int(self.window_seconds - (now - queue[0])))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

            queue.append(now)
            return RateLimitResult(allowed=True)
