import time
import threading
import logging

logger = logging.getLogger("socialpulse.rate_limiter")

class RateLimiter:
    """
    Thread-safe sliding-window rate limiter to cap Gemini API calls
    strictly under free-tier limits (default 10 requests per minute).
    """
    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.timestamps: list[float] = []
        self.lock = threading.Lock()

    def acquire(self):
        """Block until a request slot is available in the sliding window."""
        with self.lock:
            while True:
                now = time.time()
                # Remove timestamps older than the sliding window
                self.timestamps = [t for t in self.timestamps if now - t < self.window_seconds]

                if len(self.timestamps) < self.max_requests:
                    self.timestamps.append(now)
                    return

                # Wait until the oldest timestamp falls outside the window
                sleep_time = max(0.1, self.window_seconds - (now - self.timestamps[0]) + 0.1)
                logger.info(f"[RateLimiter] Throttling for {sleep_time:.2f}s (capacity {self.max_requests}/{self.window_seconds}s reached)...")
                time.sleep(sleep_time)

# Global singleton for Gemini API calls (strictly <= 5 RPM for gemini-3.6-flash free tier)
gemini_rate_limiter = RateLimiter(max_requests=5, window_seconds=62.0)
