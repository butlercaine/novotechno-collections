"""
Token bucket rate limiter for controlling API requests.
Implements 20 requests per cycle and 100 per day limits.
"""

import time
import threading
from typing import Optional
from collections import deque
from dataclasses import dataclass
import logging


logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    max_per_cycle: int = 20
    cycle_seconds: int = 60
    max_per_day: int = 100
    day_seconds: int = 86400  # 24 hours


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter with daily and per-cycle limits.
    Thread-safe implementation.
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limiter.
        
        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()
        
        # Lock for thread safety
        self._lock = threading.Lock()
        
        # Daily token bucket
        self._daily_tokens = self.config.max_per_day
        self._daily_last_refill = time.time()
        
        # Cycle token bucket (deque for sliding window)
        self._cycle_queue = deque()
        self._cycle_window_start = time.time()
        
        logger.info(
            f"Rate limiter initialized: {self.config.max_per_cycle}/cycle, "
            f"{self.config.max_per_day}/day"
        )
    
    def _refill_daily_tokens(self):
        """Refill daily token bucket (called once per day)."""
        now = time.time()
        if now - self._daily_last_refill >= self.config.day_seconds:
            self._daily_tokens = self.config.max_per_day
            self._daily_last_refill = now
            logger.debug("Daily token bucket refilled")
    
    def _cleanup_cycle_queue(self):
        """Remove expired entries from cycle queue."""
        now = time.time()
        cutoff_time = now - self.config.cycle_seconds
        
        # Remove expired entries
        while self._cycle_queue and self._cycle_queue[0] < cutoff_time:
            self._cycle_queue.popleft()
        
        # Reset window start if queue is empty
        if not self._cycle_queue:
            self._cycle_window_start = now
    
    def _can_consume_cycle_token(self) -> bool:
        """Check if cycle token can be consumed."""
        self._cleanup_cycle_queue()
        return len(self._cycle_queue) < self.config.max_per_cycle
    
    def _consume_cycle_token(self):
        """Consume a cycle token."""
        now = time.time()
        if not self._cycle_queue:
            self._cycle_window_start = now
        self._cycle_queue.append(now)
    
    def acquire(self, block: bool = True) -> bool:
        """
        Attempt to acquire a token for making a request.
        
        Args:
            block: If True, wait until token available
            
        Returns:
            True if token acquired, False otherwise
        """
        with self._lock:
            self._refill_daily_tokens()
            
            # Check both limits
            can_consume = (
                self._daily_tokens > 0 and 
                self._can_consume_cycle_token()
            )
            
            if can_consume:
                self._daily_tokens -= 1
                self._consume_cycle_token()
                logger.debug(
                    f"Token acquired. Daily: {self._daily_tokens}, "
                    f"Cycle: {len(self._cycle_queue)}"
                )
                return True
            
            if not block:
                logger.debug("Token acquisition failed (non-blocking)")
                return False
        
        # If blocking, we need to release lock and wait
        if block:
            # Calculate wait time (retry with backoff)
            wait_time = 1
            with self._lock:
                if not self._can_consume_cycle_token():
                    # Wait until next cycle window
                    now = time.time()
                    next_window = self._cycle_window_start + self.config.cycle_seconds
                    wait_time = max(wait_time, next_window - now)
                elif self._daily_tokens <= 0:
                    # Wait until tomorrow
                    now = time.time()
                    tomorrow = self._daily_last_refill + self.config.day_seconds
                    wait_time = max(wait_time, tomorrow - now)
            
            logger.debug(f"Blocking for {wait_time:.1f} seconds")
            time.sleep(wait_time)
            return self.acquire(block=True)
        
        return False
    
    def try_acquire(self) -> bool:
        """Non-blocking attempt to acquire token."""
        return self.acquire(block=False)
    
    def get_status(self) -> dict:
        """Get current rate limit status."""
        with self._lock:
            self._cleanup_cycle_queue()
            self._refill_daily_tokens()
            return {
                "daily_remaining": self._daily_tokens,
                "daily_limit": self.config.max_per_day,
                "cycle_remaining": self.config.max_per_cycle - len(self._cycle_queue),
                "cycle_limit": self.config.max_per_cycle,
                "cycle_window_age": time.time() - self._cycle_window_start,
                "cycle_queue_size": len(self._cycle_queue)
            }
    
    def wait_for_token(self, timeout: Optional[float] = None) -> bool:
        """
        Wait until a token becomes available.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if token available, False if timeout
        """
        start_time = time.time()
        
        while True:
            if self.try_acquire():
                return True
            
            if timeout and (time.time() - start_time) > timeout:
                return False
            
            # Wait a bit before retrying
            time.sleep(0.1)
    
    def execute_with_rate_limit(self, func, *args, **kwargs):
        """
        Execute function with automatic rate limiting.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        self.acquire(block=True)
        return func(*args, **kwargs)


class ExponentialBackoff:
    """
    Exponential backoff for handling 429/503 responses.
    Thread-safe implementation.
    """
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 300.0):
        """
        Initialize backoff.
        
        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._attempts = 0
        self._lock = threading.Lock()
        self._last_reset = time.time()
    
    def reset(self):
        """Reset attempt counter."""
        with self._lock:
            self._attempts = 0
            self._last_reset = time.time()
    
    def get_delay(self) -> float:
        """Get current backoff delay."""
        with self._lock:
            # Reset if it's been a while since last attempt
            if time.time() - self._last_reset > 60:
                self._attempts = 0
            
            delay = min(
                self.base_delay * (2 ** self._attempts),
                self.max_delay
            )
            self._attempts += 1
            self._last_reset = time.time()
            
            logger.debug(f"Backoff delay: {delay:.2f}s (attempt {self._attempts})")
            return delay
    
    def sleep(self):
        """Sleep for current backoff duration."""
        delay = self.get_delay()
        time.sleep(delay)