"""
Global token-bucket rate limiter shared across all scraping workers.

Ensures the aggregate request rate to GSA Advantage stays within a safe
threshold regardless of how many parallel workers are active.

Workers claim time slots under the lock but sleep OUTSIDE it, so multiple
workers can sleep toward their assigned slots in parallel.
"""
import threading
import time


class TokenBucketRateLimiter:
    def __init__(self, max_per_minute: int):
        self._interval = 60.0 / max_per_minute
        self._lock = threading.Lock()
        self._next_time = 0.0

    def acquire(self):
        """Claim the next available slot, then sleep until it arrives."""
        with self._lock:
            now = time.monotonic()
            # Claim a slot: either the next scheduled one or right now
            if self._next_time <= now:
                self._next_time = now
            target = self._next_time
            # Advance the slot for the next caller
            self._next_time += self._interval

        # Sleep OUTSIDE the lock — other workers can claim slots concurrently
        sleep_time = target - time.monotonic()
        if sleep_time > 0:
            time.sleep(sleep_time)
