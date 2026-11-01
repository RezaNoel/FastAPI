"""Small sliding-window limiter.

The window lives in process memory. It is the right size for one app instance
and for the test suite. A multi-instance deployment should swap this class for
a shared store; the middleware only depends on `allow`.
"""

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int | None = None) -> tuple[bool, int]:
        cap = self.limit if limit is None else limit
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= cap:
            return False, 0
        bucket.append(now)
        return True, cap - len(bucket)

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter(120)
