"""
Global token-bucket rate limiter shared across all scraping workers.

Ensures the aggregate request rate to GSA Advantage stays within a safe
threshold regardless of how many parallel workers are active.
"""
import threading
import time


class TokenBucketRateLimiter:
    def __init__(self, max_per_minute: int):
        self._interval = 60.0 / max_per_minute
        self._lock = threading.Lock()
        self._last_time = 0.0

    def acquire(self):
        """Block until a token is available."""
        with self._lock:
            now = time.monotonic()
            wait = self._last_time + self._interval - now
            if wait > 0:
                time.sleep(wait)
            self._last_time = time.monotonic()
